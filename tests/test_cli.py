from pathlib import Path

import pytest

from antenna_paper_extraction import cli


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
