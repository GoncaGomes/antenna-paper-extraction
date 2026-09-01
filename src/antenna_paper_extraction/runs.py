from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .persistence import write_json

PORTUGAL_TIMEZONE = ZoneInfo("Europe/Lisbon")


class SourcePdfMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    original_filename: str
    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    created_at: datetime
    document_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_pdf: SourcePdfMetadata


PhaseState = Literal["pending", "running", "succeeded", "failed"]


class PhaseFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: str
    message: str


class PhaseStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state: PhaseState
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: PhaseFailure | None = None

    @model_validator(mode="after")
    def validate_state_consistency(self) -> Self:
        if self.state == "pending":
            if (
                self.started_at is not None
                or self.finished_at is not None
                or self.error is not None
            ):
                raise ValueError(
                    "State 'pending' requires all other fields to be None."
                )

        elif self.state == "running" and (
            self.started_at is None
            or self.finished_at is not None
            or self.error is not None
        ):
            raise ValueError("State 'running' requires only 'started_at' to be set.")

        elif self.state == "succeeded" and (
            self.started_at is None
            or self.finished_at is None
            or self.error is not None
        ):
            raise ValueError(
                "State 'succeeded' requires 'started_at' and 'finished_at' to be set, and 'error' to be None."
            )

        elif self.state == "failed" and (
            self.started_at is None or self.finished_at is None or self.error is None
        ):
            raise ValueError("State 'failed' requires all fields to be set.")

        if self.started_at is not None and self.started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")

        if self.finished_at is not None and self.finished_at.utcoffset() is None:
            raise ValueError("finished_at must be timezone-aware")

        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at must not be earlier than started_at")

        return self


class RunPhases(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_preservation: PhaseStatus
    page_rendering: PhaseStatus
    document_conversion: PhaseStatus = Field(
        default_factory=lambda: PhaseStatus(state="pending")
    )


class RunStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    phases: RunPhases


def create_run(input_pdf: Path, runs_root: Path = Path("runs")) -> Path:
    input_pdf = Path(input_pdf)
    runs_root = Path(runs_root)

    if not input_pdf.exists():
        raise FileNotFoundError(f"input PDF does not exist: {input_pdf}")
    if not input_pdf.is_file():
        raise ValueError(f"input PDF is not a file: {input_pdf}")

    created_at = datetime.now(PORTUGAL_TIMEZONE)
    run_id = generate_run_id(created_at)

    run_dir = runs_root / run_id

    runs_root.mkdir(parents=True, exist_ok=True)

    if run_dir.exists():
        raise FileExistsError(f"run directory already exists: {run_dir} ")

    temp_dir_str = tempfile.mkdtemp(prefix=f"{run_id}_")
    temporary_run_dir = Path(temp_dir_str)

    try:
        input_directory = temporary_run_dir / "input"
        input_directory.mkdir()

        input_relative_path = Path("input") / input_pdf.name
        source_pdf = temporary_run_dir / input_relative_path
        manifest_path = temporary_run_dir / "manifest.json"
        status_path = temporary_run_dir / "status.json"

        source_started_at = datetime.now(PORTUGAL_TIMEZONE)

        shutil.copy2(input_pdf, source_pdf)
        input_sha256 = sha256_file(source_pdf)
        input_size_bytes = source_pdf.stat().st_size

        source_finished_at = datetime.now(PORTUGAL_TIMEZONE)

        manifest = RunManifest(
            run_id=run_id,
            created_at=created_at,
            document_id=f"sha256:{input_sha256}",
            source_pdf=SourcePdfMetadata(
                original_filename=input_pdf.name,
                relative_path=input_relative_path.as_posix(),
                sha256=input_sha256,
                size_bytes=input_size_bytes,
            ),
        )

        run_status = RunStatus(
            run_id=run_id,
            phases=RunPhases(
                source_preservation=PhaseStatus(
                    state="succeeded",
                    started_at=source_started_at,
                    finished_at=source_finished_at,
                ),
                page_rendering=PhaseStatus(state="pending"),
                document_conversion=PhaseStatus(state="pending"),
            ),
        )
        write_json(manifest_path, manifest.model_dump(mode="json"))
        write_json(status_path, run_status.model_dump(mode="json"))

        shutil.move(str(temporary_run_dir), str(run_dir))

    except Exception:
        shutil.rmtree(temporary_run_dir, ignore_errors=True)
        raise

    return run_dir


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_run_id(created_at: datetime) -> str:
    timestamp = created_at.strftime("%Y%m%dT%H%M%S%z")
    return f"run_{timestamp}_{uuid4().hex[:8]}"


def load_run_status(run_dir: Path) -> RunStatus:
    status_path = run_dir / "status.json"
    return RunStatus.model_validate_json(status_path.read_text(encoding="utf-8"))


def mark_page_rendering_running(run_dir: Path) -> RunStatus:
    run_dir = Path(run_dir)
    current_status = load_run_status(run_dir)

    if current_status.phases.source_preservation.state != "succeeded":
        raise ValueError(
            "source_preservation must be succeeded to mark page rendering as running"
        )
    current_page_status = current_status.phases.page_rendering
    if current_page_status.state != "pending":
        raise ValueError("page rendering can only start from the pending state")

    started_at = datetime.now(PORTUGAL_TIMEZONE)

    updated_status = RunStatus(
        schema_version=current_status.schema_version,
        run_id=current_status.run_id,
        phases=RunPhases(
            source_preservation=current_status.phases.source_preservation,
            page_rendering=PhaseStatus(state="running", started_at=started_at),
        ),
    )
    write_json(run_dir / "status.json", updated_status.model_dump(mode="json"))

    return updated_status


def mark_page_rendering_succeeded(run_dir: Path) -> RunStatus:
    run_dir = Path(run_dir)
    current_status = load_run_status(run_dir)
    current_page_status = current_status.phases.page_rendering

    if current_status.phases.source_preservation.state != "succeeded":
        raise ValueError(
            "source_preservation must be succeeded to mark page rendering as succeeded"
        )

    if current_page_status.state != "running":
        raise ValueError("page rendering can only succeed from the running state")

    finished_at = datetime.now(PORTUGAL_TIMEZONE)

    updated_status = RunStatus(
        schema_version=current_status.schema_version,
        run_id=current_status.run_id,
        phases=RunPhases(
            source_preservation=current_status.phases.source_preservation,
            page_rendering=PhaseStatus(
                state="succeeded",
                started_at=current_page_status.started_at,
                finished_at=finished_at,
            ),
        ),
    )
    write_json(run_dir / "status.json", updated_status.model_dump(mode="json"))

    return updated_status


def mark_page_rendering_failed(run_dir: Path, failure: PhaseFailure) -> RunStatus:
    run_dir = Path(run_dir)
    current_status = load_run_status(run_dir)
    current_page_status = current_status.phases.page_rendering

    if current_status.phases.page_rendering.state != "running":
        raise ValueError("page rendering can only fail from the running state")

    finished_at = datetime.now(PORTUGAL_TIMEZONE)

    updated_status = RunStatus(
        schema_version=current_status.schema_version,
        run_id=current_status.run_id,
        phases=RunPhases(
            source_preservation=current_status.phases.source_preservation,
            page_rendering=PhaseStatus(
                state="failed",
                started_at=current_page_status.started_at,
                finished_at=finished_at,
                error=failure,
            ),
        ),
    )
    write_json(run_dir / "status.json", updated_status.model_dump(mode="json"))

    return updated_status


def mark_document_conversion_running(run_dir: Path) -> RunStatus:
    run_dir = Path(run_dir)
    current_status = load_run_status(run_dir)

    if current_status.phases.page_rendering.state != "succeeded":
        raise ValueError("page rendering must succeed before document conversion")

    current_conversion_status = current_status.phases.document_conversion

    if current_conversion_status.state != "pending":
        raise ValueError("document conversion can only start from the pending state")

    started_at = datetime.now(PORTUGAL_TIMEZONE)

    updated_status = RunStatus(
        schema_version=current_status.schema_version,
        run_id=current_status.run_id,
        phases=RunPhases(
            source_preservation=current_status.phases.source_preservation,
            page_rendering=current_status.phases.page_rendering,
            document_conversion=PhaseStatus(state="running", started_at=started_at),
        ),
    )

    write_json(run_dir / "status.json", updated_status.model_dump(mode="json"))

    return updated_status


def mark_document_conversion_succeeded(run_dir: Path) -> RunStatus:
    run_dir = Path(run_dir)
    current_status = load_run_status(run_dir)
    current_conversion_status = current_status.phases.document_conversion

    if current_conversion_status.state != "running":
        raise ValueError("document conversion can only succeed from the running state")

    finished_at = datetime.now(PORTUGAL_TIMEZONE)

    updated_status = RunStatus(
        schema_version=current_status.schema_version,
        run_id=current_status.run_id,
        phases=RunPhases(
            source_preservation=current_status.phases.source_preservation,
            page_rendering=current_status.phases.page_rendering,
            document_conversion=PhaseStatus(
                state="succeeded",
                started_at=current_conversion_status.started_at,
                finished_at=finished_at,
            ),
        ),
    )
    write_json(run_dir / "status.json", updated_status.model_dump(mode="json"))

    return updated_status


def mark_document_conversion_failed(run_dir: Path, failure: PhaseFailure) -> RunStatus:
    run_dir = Path(run_dir)
    current_status = load_run_status(run_dir)
    current_conversion_status = current_status.phases.document_conversion

    if current_conversion_status.state != "running":
        raise ValueError("page rendering can only fail from the running state")

    finished_at = datetime.now(PORTUGAL_TIMEZONE)

    updated_status = RunStatus(
        schema_version=current_status.schema_version,
        run_id=current_status.run_id,
        phases=RunPhases(
            source_preservation=current_status.phases.source_preservation,
            page_rendering=current_status.phases.page_rendering,
            document_conversion=PhaseStatus(
                state="failed",
                started_at=current_conversion_status.started_at,
                finished_at=finished_at,
                error=failure,
            ),
        ),
    )
    write_json(run_dir / "status.json", updated_status.model_dump(mode="json"))

    return updated_status
