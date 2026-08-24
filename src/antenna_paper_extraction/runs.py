from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

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


def create_run(input_pdf: Path, runs_root: Path = Path("runs")) -> Path:

    input_pdf = Path(input_pdf)
    runs_root = Path(runs_root)

    if not input_pdf.exists():
        raise FileNotFoundError(f"input PDF does not exist: {input_pdf}")
    if not input_pdf.is_file():
        raise ValueError(f"input PDF is not a file: {input_pdf}")

    created_at = datetime.now(PORTUGAL_TIMEZONE)
    run_id = _generate_run_id(created_at)

    run_dir = runs_root / run_id
    temporary_run_dir = runs_root / f".{run_id}.tmp"

    input_relative_path = Path("input") / input_pdf.name
    source_pdf = temporary_run_dir / input_relative_path
    manifest_path = temporary_run_dir / "manifest.json"

    runs_root.mkdir(parents=True, exist_ok=True)

    if run_dir.exists():
        raise FileExistsError(f"run directory already exists: {run_dir} ")

    if temporary_run_dir.exists():
        raise FileExistsError(
            f"temporary run directory already exists:   {temporary_run_dir}"
        )

    temporary_run_dir.mkdir()

    try:
        input_directory = temporary_run_dir / "input"
        input_directory.mkdir()

        shutil.copy2(input_pdf, source_pdf)
        input_sha256 = sha256_file(source_pdf)

        manifest = RunManifest(
            run_id=run_id,
            created_at=created_at,
            document_id=f"sha256:{input_sha256}",
            source_pdf=SourcePdfMetadata(
                original_filename=input_pdf.name,
                relative_path=input_relative_path.as_posix(),
                sha256=input_sha256,
                size_bytes=source_pdf.stat().st_size,
            ),
        )

        write_json(manifest_path, manifest.model_dump(mode="json"))
        temporary_run_dir.rename(run_dir)
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


def _generate_run_id(created_at: datetime) -> str:
    timestamp = created_at.strftime("%Y%m%dT%H%M%S%z")
    return f"run_{timestamp}_{uuid4().hex[:8]}"
