from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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


def _document_extractor_environment() -> dict[str, str]:
    return {
        "SKYNET_BASE_URL": "https://skynet.example.test/v1",
        "SKYNET_API_KEY": "test-api-key",
        "DOCUMENT_EXTRACTOR_MODEL": "nuextract3",
        "DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS": "600",
    }


@pytest.mark.parametrize(
    "missing_name",
    [
        "SKYNET_BASE_URL",
        "SKYNET_API_KEY",
        "DOCUMENT_EXTRACTOR_MODEL",
        "DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS",
    ],
)
def test_load_document_extractor_settings_rejects_missing_variable(
    missing_name: str,
) -> None:
    environ = _document_extractor_environment()
    del environ[missing_name]

    with pytest.raises(
        ValueError,
        match=rf"Missing required environment variable: {missing_name}",
    ):
        cli.load_document_extractor_settings(environ)


@pytest.mark.parametrize(
    "timeout_value",
    [
        "banana",
        "0",
        "-1",
    ],
)
def test_load_document_extractor_settings_rejects_invalid_timeout(
    timeout_value: str,
) -> None:
    environ = _document_extractor_environment()
    environ["DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS"] = timeout_value

    with pytest.raises(
        ValueError,
        match="DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS must be a positive number",
    ):
        cli.load_document_extractor_settings(environ)


def test_convert_document_help_uses_public_cli_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["convert-document", "--help"])

    assert exception.value.code == 0

    captured = capsys.readouterr()

    assert "convert-document" in captured.out
    assert "run_dir" in captured.out


def test_convert_document_loads_dotenv_and_calls_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SKYNET_BASE_URL=https://dotenv.example.test/v1\n"
        "SKYNET_API_KEY=dotenv-test-key\n"
        "DOCUMENT_EXTRACTOR_MODEL=nuextract3-from-dotenv\n"
        "DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS=600\n",
        encoding="utf-8",
    )

    for name in _document_extractor_environment():
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv(
        "DOCUMENT_EXTRACTOR_MODEL",
        "nuextract3-from-system",
    )
    monkeypatch.chdir(tmp_path)

    sdk_client = object()
    openai_constructor = Mock(return_value=sdk_client)
    monkeypatch.setattr(cli, "OpenAI", openai_constructor)

    run_dir = tmp_path / "runs" / "run_test"
    document_path = run_dir / "document.md"

    conversion = Mock(return_value=document_path)
    monkeypatch.setattr(
        cli,
        "convert_document_to_markdown",
        conversion,
    )

    exit_code = cli.main(
        [
            "convert-document",
            str(run_dir),
        ]
    )

    assert exit_code == 0

    openai_constructor.assert_called_once_with(
        base_url="https://dotenv.example.test/v1",
        api_key="dotenv-test-key",
        timeout=600.0,
        max_retries=0,
    )

    conversion.assert_called_once()

    conversion_arguments = conversion.call_args.kwargs

    assert conversion_arguments["run_dir"] == run_dir
    assert conversion_arguments["model"] == "nuextract3-from-system"

    wrapped_client = conversion_arguments["client"]

    assert isinstance(
        wrapped_client,
        cli.OpenAICompatibleClient,
    )
    assert wrapped_client.sdk_client is sdk_client

    captured = capsys.readouterr()

    assert captured.out == (f"Converted document: {document_path.resolve()}\n")
    assert captured.err == ""
    assert "dotenv-test-key" not in captured.out


def test_convert_document_reports_missing_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    for name in _document_extractor_environment():
        monkeypatch.delenv(name, raising=False)

    openai_constructor = Mock()
    monkeypatch.setattr(cli, "OpenAI", openai_constructor)

    exit_code = cli.main(
        [
            "convert-document",
            str(tmp_path / "run_test"),
        ]
    )

    assert exit_code == 1

    openai_constructor.assert_not_called()

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        "Failed to convert document. "
        "Missing required environment variable: SKYNET_BASE_URL\n"
    )


def test_convert_document_reports_expected_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    for name, value in _document_extractor_environment().items():
        monkeypatch.setenv(name, value)

    sdk_client = object()
    monkeypatch.setattr(
        cli,
        "OpenAI",
        Mock(return_value=sdk_client),
    )

    conversion = Mock(side_effect=ValueError("simulated conversion failure"))
    monkeypatch.setattr(
        cli,
        "convert_document_to_markdown",
        conversion,
    )

    exit_code = cli.main(
        [
            "convert-document",
            str(tmp_path / "run_test"),
        ]
    )

    assert exit_code == 1
    assert conversion.call_count == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        "Failed to convert document. simulated conversion failure\n"
    )


def test_convert_document_does_not_hide_unexpected_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    for name, value in _document_extractor_environment().items():
        monkeypatch.setenv(name, value)

    sdk_client = object()
    monkeypatch.setattr(
        cli,
        "OpenAI",
        Mock(return_value=sdk_client),
    )

    conversion = Mock(side_effect=RuntimeError("unexpected conversion failure"))
    monkeypatch.setattr(
        cli,
        "convert_document_to_markdown",
        conversion,
    )

    with pytest.raises(
        RuntimeError,
        match="unexpected conversion failure",
    ):
        cli.main(
            [
                "convert-document",
                str(tmp_path / "run_test"),
            ]
        )


def _document_extractor_environment() -> dict[str, str]:
    return {
        "SKYNET_BASE_URL": "https://skynet.example.test/v1",
        "SKYNET_API_KEY": "test-api-key",
        "DOCUMENT_EXTRACTOR_MODEL": "nuextract3",
        "DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS": "600",
    }
