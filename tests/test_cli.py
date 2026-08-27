from pathlib import Path
from types import SimpleNamespace

import pytest

from antenna_paper_extraction import cli
from antenna_paper_extraction.runs import (
    create_run,
    load_run_status,
)


def test_init_run_help_uses_public_cli_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["init-run", "--help"])

    captured = capsys.readouterr()
    assert exception.value.code == 0
    assert "usage: antenna-extract init-run" in captured.out
    assert "--runs-root" in captured.out
    assert "--runs_root" not in captured.out
    assert captured.err == ""


def test_init_run_reports_created_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_pdf = tmp_path / "paper.pdf"
    runs_root = tmp_path / "custom-runs"
    run_dir = runs_root / "run_test"

    def fake_create_run(received_pdf: Path, received_runs_root: Path) -> Path:
        assert received_pdf == input_pdf
        assert received_runs_root == runs_root
        return run_dir

    monkeypatch.setattr(cli, "create_run", fake_create_run)

    exit_code = cli.main(
        [
            "init-run",
            str(input_pdf),
            "--runs-root",
            str(runs_root),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == f"Created run: {run_dir.resolve()}\n"
    assert captured.err == ""


def test_init_run_reports_expected_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_create_run(_input_pdf: Path, _runs_root: Path) -> Path:
        raise FileNotFoundError("input PDF does not exist: missing.pdf")

    monkeypatch.setattr(cli, "create_run", fake_create_run)

    exit_code = cli.main(["init-run", "missing.pdf"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "Failed to create run. input PDF does not exist: missing.pdf\n"
    )
    assert "Traceback" not in captured.err


def test_init_run_does_not_hide_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create_run(_input_pdf: Path, _runs_root: Path) -> Path:
        raise RuntimeError("simulated programming error")

    monkeypatch.setattr(cli, "create_run", fake_create_run)

    with pytest.raises(RuntimeError, match="simulated programming error"):
        cli.main(["init-run", "paper.pdf"])


def test_missing_input_pdf_uses_argparse_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["init-run"])

    captured = capsys.readouterr()

    assert exception.value.code == 2
    assert captured.out == ""
    assert "usage: antenna-extract init-run" in captured.err
    assert "input_pdf" in captured.err


def test_render_pages_help_uses_public_cli_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["render-pages", "--help"])

    captured = capsys.readouterr()

    assert exception.value.code == 0
    assert "usage: antenna-extract render-pages" in captured.out
    assert "run_dir" in captured.out
    assert "--dpi" in captured.out
    assert captured.err == ""


def test_render_pages_reports_rendered_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = tmp_path / "runs" / "run_test"

    def fake_render_pdf_pages(
        received_run_dir: Path,
        *,
        dpi: int,
    ) -> SimpleNamespace:
        assert received_run_dir == run_dir
        assert dpi == 144
        return SimpleNamespace(page_count=3)

    monkeypatch.setattr(
        cli,
        "render_pdf_pages",
        fake_render_pdf_pages,
    )

    exit_code = cli.main(
        [
            "render-pages",
            str(run_dir),
            "--dpi",
            "144",
        ]
    )

    captured = capsys.readouterr()
    pages_dir = (run_dir / "pages").resolve()

    assert exit_code == 0
    assert captured.out == f"Rendered 3 page(s): {pages_dir}\n"
    assert captured.err == ""


def test_render_pages_reports_expected_pdf_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_pdf = tmp_path / "invalid.pdf"
    input_pdf.write_bytes(b"not a PDF")

    run_dir = create_run(input_pdf, tmp_path / "runs")

    exit_code = cli.main(
        [
            "render-pages",
            str(run_dir),
        ]
    )

    captured = capsys.readouterr()
    status = load_run_status(run_dir)
    page_status = status.phases.page_rendering

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.startswith("Failed to render pages. ")
    assert "Traceback" not in captured.err

    assert page_status.state == "failed"
    assert page_status.error is not None
    assert page_status.error.type == "PdfiumError"
    assert not (run_dir / "pages.json").exists()


def test_render_pages_does_not_hide_unexpected_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "runs" / "run_test"

    def fake_render_pdf_pages(
        _run_dir: Path,
        *,
        dpi: int,
    ) -> SimpleNamespace:
        assert dpi == 200
        raise RuntimeError("simulated programming error")

    monkeypatch.setattr(
        cli,
        "render_pdf_pages",
        fake_render_pdf_pages,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated programming error",
    ):
        cli.main(["render-pages", str(run_dir)])
