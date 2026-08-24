from datetime import datetime
from pathlib import Path

import pytest

from antenna_paper_extraction import runs
from antenna_paper_extraction.persistence import read_json


PDF_CONTENT = b"%PDF-1.4\nminimal test content\n%%EOF\n"


def write_test_pdf(path: Path, content: bytes = PDF_CONTENT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


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
        "_generate_run_id",
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