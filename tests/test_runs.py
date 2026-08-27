import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from antenna_paper_extraction import runs
from antenna_paper_extraction.persistence import read_json
from antenna_paper_extraction.runs import (
    PhaseFailure,
    PhaseStatus,
    RunPhases,
    RunStatus,
    load_run_status,
    mark_page_rendering_failed,
    mark_page_rendering_running,
    mark_page_rendering_succeeded,
)

PDF_CONTENT = b"%PDF-1.4\nminimal test content\n%%EOF\n"


def test_create_run_copies_pdf_and_writes_manifest(tmp_path: Path) -> None:
    input_pdf = tmp_path / "paper with spaces.pdf"
    runs_root = tmp_path / "runs"
    write_test_pdf(input_pdf)

    run_dir = runs.create_run(input_pdf, runs_root)

    copied_pdf = run_dir / "input" / input_pdf.name
    manifest = read_json(run_dir / "manifest.json")
    checksum = runs.sha256_file(copied_pdf)

    assert run_dir.parent == runs_root
    assert copied_pdf.read_bytes() == input_pdf.read_bytes()

    assert set(manifest) == {
        "schema_version",
        "run_id",
        "created_at",
        "document_id",
        "source_pdf",
    }
    assert manifest["schema_version"] == "1.0"
    assert manifest["run_id"] == run_dir.name
    assert manifest["document_id"] == f"sha256:{checksum}"

    created_at = datetime.fromisoformat(manifest["created_at"])
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() is not None

    source_pdf = manifest["source_pdf"]
    assert source_pdf["original_filename"] == input_pdf.name
    assert source_pdf["relative_path"] == f"input/{input_pdf.name}"
    assert source_pdf["sha256"] == checksum
    assert source_pdf["size_bytes"] == copied_pdf.stat().st_size
    assert {path.name for path in run_dir.iterdir()} == {
        "input",
        "manifest.json",
        "status.json",
    }

    status_path = run_dir / "status.json"
    assert status_path.is_file()
    status_data = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_data["schema_version"] == "1.0"
    assert status_data["run_id"] == manifest["run_id"]

    assert status_data["phases"]["source_preservation"]["state"] == "succeeded"
    assert status_data["phases"]["source_preservation"]["started_at"] is not None
    assert status_data["phases"]["source_preservation"]["finished_at"] is not None
    assert status_data["phases"]["source_preservation"]["error"] is None

    assert status_data["phases"]["page_rendering"] == {
        "state": "pending",
        "started_at": None,
        "finished_at": None,
        "error": None,
    }


def test_same_content_has_same_document_identity(tmp_path: Path) -> None:
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    runs_root = tmp_path / "runs"

    write_test_pdf(first_pdf)
    write_test_pdf(second_pdf)

    first_run = runs.create_run(first_pdf, runs_root)
    second_run = runs.create_run(second_pdf, runs_root)

    first_manifest = read_json(first_run / "manifest.json")
    second_manifest = read_json(second_run / "manifest.json")

    assert first_run != second_run
    assert first_manifest["document_id"] == second_manifest["document_id"]


def test_create_run_rejects_missing_input(tmp_path: Path) -> None:
    missing_pdf = tmp_path / "missing.pdf"
    runs_root = tmp_path / "runs"

    with pytest.raises(FileNotFoundError, match="does not exist"):
        runs.create_run(missing_pdf, runs_root)

    assert not runs_root.exists()


def test_create_run_rejects_directory_input(tmp_path: Path) -> None:
    input_directory = tmp_path / "not-a-pdf"
    input_directory.mkdir()
    runs_root = tmp_path / "runs"

    with pytest.raises(ValueError, match="is not a file"):
        runs.create_run(input_directory, runs_root)

    assert not runs_root.exists()


def test_create_run_does_not_overwrite_existing_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_pdf = tmp_path / "paper.pdf"
    runs_root = tmp_path / "runs"
    existing_run = runs_root / "run_existing"
    sentinel = existing_run / "keep.txt"

    write_test_pdf(input_pdf)
    existing_run.mkdir(parents=True)
    sentinel.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(
        runs,
        "generate_run_id",
        lambda *_args, **_kwargs: existing_run.name,
    )

    with pytest.raises(FileExistsError, match="already exists"):
        runs.create_run(input_pdf, runs_root)

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_create_run_removes_temporary_directory_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_pdf = tmp_path / "paper.pdf"
    runs_root = tmp_path / "runs"
    write_test_pdf(input_pdf)

    def fail_write_json(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(runs, "write_json", fail_write_json)

    with pytest.raises(OSError, match="simulated write failure"):
        runs.create_run(input_pdf, runs_root)

    assert runs_root.exists()
    assert list(runs_root.iterdir()) == []


def test_run_status_represents_current_run_phases() -> None:
    started_at = datetime(
        2026,
        8,
        26,
        16,
        0,
        tzinfo=ZoneInfo("Europe/Lisbon"),
    )
    finished_at = started_at + timedelta(seconds=1)

    run_id = "run_20260826T130522+0100_1eab0e6e"
    source_preservation = PhaseStatus(
        state="succeeded",
        started_at=started_at,
        finished_at=finished_at,
    )

    page_rendering = PhaseStatus(state="pending")
    phases = RunPhases(
        source_preservation=source_preservation,
        page_rendering=page_rendering,
    )
    status = RunStatus(
        run_id=run_id,
        phases=phases,
    )
    assert status.schema_version == "1.0"
    assert status.run_id == run_id
    assert status.phases.source_preservation.state == "succeeded"
    assert status.phases.page_rendering.state == "pending"


def test_phase_status_rejects_pending_with_timestamp() -> None:
    started_at = datetime(
        2026,
        8,
        26,
        16,
        0,
        tzinfo=ZoneInfo("Europe/Lisbon"),
    )

    with pytest.raises(ValidationError, match="pending"):
        PhaseStatus(
            state="pending",
            started_at=started_at,
        )


def test_load_run_status_validates_persisted_status(tmp_path: Path) -> None:
    input_pdf = tmp_path / "paper.pdf"
    runs_root = tmp_path / "runs"
    write_test_pdf(input_pdf)

    run_dir = runs.create_run(input_pdf, runs_root)
    status = load_run_status(run_dir)

    assert isinstance(status, RunStatus)
    assert status.run_id == run_dir.name
    assert status.phases.source_preservation.state == "succeeded"
    assert status.phases.page_rendering.state == "pending"


def test_mark_page_rendering_running_persists_transition(tmp_path: Path) -> None:
    input_pdf = tmp_path / "paper.pdf"
    write_test_pdf(input_pdf)

    run_dir = runs.create_run(input_pdf, tmp_path / "runs")
    initial_status = load_run_status(run_dir)

    updated_status = mark_page_rendering_running(run_dir)
    persisted_status = load_run_status(run_dir)

    assert updated_status == persisted_status
    assert updated_status.run_id == initial_status.run_id
    assert (
        updated_status.phases.source_preservation
        == initial_status.phases.source_preservation
    )

    page_status = updated_status.phases.page_rendering
    assert page_status.state == "running"
    assert page_status.started_at is not None
    assert page_status.started_at.utcoffset() is not None
    assert page_status.finished_at is None
    assert page_status.error is None


def test_mark_page_rendering_running_rejects_repeated_start(
    tmp_path: Path,
) -> None:
    input_pdf = tmp_path / "paper.pdf"
    write_test_pdf(input_pdf)

    run_dir = runs.create_run(input_pdf, tmp_path / "runs")
    mark_page_rendering_running(run_dir)

    with pytest.raises(ValueError, match="only start from the pending state"):
        mark_page_rendering_running(run_dir)


def test_mark_page_rendering_succeeded_persists_transition(
    tmp_path: Path,
) -> None:
    input_pdf = tmp_path / "paper.pdf"
    write_test_pdf(input_pdf)

    run_dir = runs.create_run(input_pdf, tmp_path / "runs")
    running_status = mark_page_rendering_running(run_dir)

    updated_status = mark_page_rendering_succeeded(run_dir)
    persisted_status = load_run_status(run_dir)

    assert updated_status == persisted_status
    assert (
        updated_status.phases.source_preservation
        == running_status.phases.source_preservation
    )

    previous_page_status = running_status.phases.page_rendering
    page_status = updated_status.phases.page_rendering

    assert page_status.state == "succeeded"
    assert page_status.started_at == previous_page_status.started_at
    assert page_status.finished_at is not None
    assert page_status.finished_at.utcoffset() is not None
    assert page_status.finished_at >= page_status.started_at
    assert page_status.error is None


def test_mark_page_rendering_succeeded_rejects_pending_state(
    tmp_path: Path,
) -> None:
    input_pdf = tmp_path / "paper.pdf"
    write_test_pdf(input_pdf)

    run_dir = runs.create_run(input_pdf, tmp_path / "runs")

    with pytest.raises(ValueError, match="only succeed from the running state"):
        mark_page_rendering_succeeded(run_dir)


def test_mark_page_rendering_failed_persists_failure(
    tmp_path: Path,
) -> None:
    input_pdf = tmp_path / "paper.pdf"
    write_test_pdf(input_pdf)

    run_dir = runs.create_run(input_pdf, tmp_path / "runs")
    running_status = mark_page_rendering_running(run_dir)

    failure = PhaseFailure(
        type="PdfiumError",
        message="simulated rendering failure",
    )

    updated_status = mark_page_rendering_failed(run_dir, failure)
    persisted_status = load_run_status(run_dir)

    assert updated_status == persisted_status
    assert (
        updated_status.phases.source_preservation
        == running_status.phases.source_preservation
    )

    previous_page_status = running_status.phases.page_rendering
    page_status = updated_status.phases.page_rendering

    assert page_status.state == "failed"
    assert page_status.started_at == previous_page_status.started_at
    assert page_status.finished_at is not None
    assert page_status.finished_at.utcoffset() is not None
    assert page_status.finished_at >= page_status.started_at
    assert page_status.error == failure
    status_data = read_json(run_dir / "status.json")

    assert status_data["phases"]["page_rendering"]["error"] == {
        "type": "PdfiumError",
        "message": "simulated rendering failure",
    }


def test_mark_page_rendering_failed_rejects_pending_state(
    tmp_path: Path,
) -> None:
    input_pdf = tmp_path / "paper.pdf"
    write_test_pdf(input_pdf)

    run_dir = runs.create_run(input_pdf, tmp_path / "runs")

    failure = PhaseFailure(
        type="PdfiumError",
        message="simulated rendering failure",
    )

    with pytest.raises(ValueError, match="only fail from the running state"):
        mark_page_rendering_failed(run_dir, failure)


def write_test_pdf(path: Path, content: bytes = PDF_CONTENT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
