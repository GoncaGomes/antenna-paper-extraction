import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from agents.exceptions import ModelBehaviorError

from antenna_paper_extraction import cli


def _environment() -> dict[str, str]:
    return {
        "SKYNET_BASE_URL": "https://model.invalid/v1",
        "SKYNET_API_KEY": "test-key",
        "ARCHITECTURE_AGENT_MODEL": "test-model",
        "ARCHITECTURE_AGENT_TIMEOUT_SECONDS": "600",
    }


def _install_client(monkeypatch: pytest.MonkeyPatch):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False

    constructor = Mock(return_value=client)
    monkeypatch.setattr(cli, "AsyncOpenAI", constructor)

    return constructor, client


@pytest.mark.parametrize("name", list(_environment()))
def test_settings_reject_missing_variable(name: str) -> None:
    environment = _environment()
    del environment[name]

    with pytest.raises(ValueError, match=name):
        cli.load_architecture_agent_settings(environment)


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "-inf", "banana"])
def test_settings_reject_invalid_timeout(timeout: str) -> None:
    environment = _environment()
    environment["ARCHITECTURE_AGENT_TIMEOUT_SECONDS"] = timeout

    with pytest.raises(ValueError, match="positive finite number"):
        cli.load_architecture_agent_settings(environment)


def test_cli_loads_dotenv_and_closes_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    for name in _environment():
        monkeypatch.delenv(name, raising=False)

    (tmp_path / ".env").write_text(
        "\n".join(f"{name}={value}" for name, value in _environment().items()),
        encoding="utf-8",
    )

    # Existing environment variables take precedence over .env.
    monkeypatch.setenv("ARCHITECTURE_AGENT_MODEL", "system-model")

    constructor, client = _install_client(monkeypatch)

    run_dir = tmp_path / "run"
    report_path = run_dir / "architecture" / "architecture_evidence_report.md"
    extraction = AsyncMock(return_value=report_path)
    monkeypatch.setattr(cli, "run_architecture_agent", extraction)

    exit_code = cli.main(["extract-architecture", str(run_dir), "--max-assets", "3"])

    assert exit_code == 0

    constructor.assert_called_once_with(
        base_url="https://model.invalid/v1",
        api_key="test-key",
        timeout=600.0,
        max_retries=0,
    )
    extraction.assert_awaited_once_with(
        run_dir=run_dir,
        client=client,
        model_name="system-model",
        max_assets=3,
    )
    client.__aenter__.assert_awaited_once()
    client.__aexit__.assert_awaited_once_with(None, None, None)

    captured = capsys.readouterr()
    assert captured.out == f"Architecture report: {report_path.resolve()}\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "failure",
    [
        ModelBehaviorError("Synthetic length failure."),
        ValueError("Synthetic validation failure."),
        OSError("Synthetic persistence failure."),
    ],
)
def test_cli_reports_failure_and_closes_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
) -> None:
    monkeypatch.chdir(tmp_path)

    for name, value in _environment().items():
        monkeypatch.setenv(name, value)

    _, client = _install_client(monkeypatch)
    extraction = AsyncMock(side_effect=failure)
    monkeypatch.setattr(cli, "run_architecture_agent", extraction)

    exit_code = cli.main(["extract-architecture", str(tmp_path / "run")])

    assert exit_code == 1
    extraction.assert_awaited_once()
    client.__aexit__.assert_awaited_once()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(failure) in captured.err


def test_cli_rejects_missing_configuration_before_creating_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    for name, value in _environment().items():
        monkeypatch.setenv(name, value)

    monkeypatch.delenv("ARCHITECTURE_AGENT_MODEL")
    constructor, _ = _install_client(monkeypatch)

    exit_code = cli.main(["extract-architecture", str(tmp_path / "run")])

    assert exit_code == 1
    constructor.assert_not_called()
    assert "ARCHITECTURE_AGENT_MODEL" in capsys.readouterr().err


@pytest.mark.parametrize("max_assets", ["0", "-1", "banana"])
def test_cli_rejects_invalid_asset_limit(
    monkeypatch: pytest.MonkeyPatch,
    max_assets: str,
) -> None:
    constructor, _ = _install_client(monkeypatch)

    with pytest.raises(SystemExit) as caught:
        cli.main(["extract-architecture", "run", "--max-assets", max_assets])

    assert caught.value.code == 2
    constructor.assert_not_called()


def test_cli_does_not_hide_unexpected_type_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    for name, value in _environment().items():
        monkeypatch.setenv(name, value)

    _, client = _install_client(monkeypatch)
    monkeypatch.setattr(
        cli,
        "run_architecture_agent",
        AsyncMock(side_effect=TypeError("Synthetic programming error.")),
    )

    with pytest.raises(TypeError, match="programming error"):
        cli.main(["extract-architecture", str(tmp_path / "run")])

    client.__aexit__.assert_awaited_once()


def _mcp_environment(tmp_path: Path) -> dict[str, str]:
    server_cwd = tmp_path / "server with spaces"
    server_cwd.mkdir()
    executable = server_cwd / "server executable.exe"
    executable.touch()
    return {
        **_environment(),
        "VISUAL_INSPECTION_MODEL": "visual-model",
        "VISUAL_INSPECTION_TIMEOUT_SECONDS": "120",
        "MCP_PDF_SERVER_EXECUTABLE": str(executable),
        "MCP_PDF_SERVER_CWD": str(server_cwd),
    }


@pytest.mark.parametrize("options, budget", [([], 80), (["--max-turns", "7"], 7)])
def test_mcp_cli_forwards_settings_and_environment_precedence(
    tmp_path, monkeypatch, capsys, options, budget
):
    monkeypatch.chdir(tmp_path)
    environment = _mcp_environment(tmp_path)
    for name in environment:
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(f"{name}='{value}'" for name, value in environment.items()),
        encoding="utf-8",
    )
    monkeypatch.setenv("ARCHITECTURE_AGENT_MODEL", "process-model")
    monkeypatch.setenv("VISUAL_INSPECTION_TIMEOUT_SECONDS", "90")
    run_dir = tmp_path / "run"
    report = run_dir / "mcp/architecture/architecture_evidence_report.md"
    runtime = AsyncMock(return_value=report)
    monkeypatch.setattr(cli, "probe", runtime)
    previous_logging_disable = logging.root.manager.disable

    assert cli.main(["extract-architecture-mcp", str(run_dir), *options]) == 0
    runtime.assert_awaited_once_with(
        run_dir,
        Path(environment["MCP_PDF_SERVER_EXECUTABLE"]).resolve(),
        Path(environment["MCP_PDF_SERVER_CWD"]).resolve(),
        agent_model="process-model",
        agent_task="architecture",
        max_turns=budget,
        persist_architecture=True,
        base_url=environment["SKYNET_BASE_URL"],
        api_key=environment["SKYNET_API_KEY"],
        principal_timeout_seconds=600.0,
        visual_model="visual-model",
        visual_timeout_seconds=90.0,
        session_timeout_seconds=150.0,
    )
    assert environment["SKYNET_API_KEY"] not in repr(
        cli.load_mcp_architecture_settings(environment)
    )
    assert logging.root.manager.disable == previous_logging_disable
    output = capsys.readouterr()
    assert output.out == f"MCP architecture report: {report.resolve()}\n"
    assert output.err == ""


@pytest.mark.parametrize(
    "name, value",
    [
        ("ARCHITECTURE_AGENT_MODEL", None),
        ("VISUAL_INSPECTION_MODEL", " "),
        ("MCP_PDF_SERVER_CWD", None),
        ("ARCHITECTURE_AGENT_TIMEOUT_SECONDS", "nan"),
        ("VISUAL_INSPECTION_TIMEOUT_SECONDS", "0"),
        ("VISUAL_INSPECTION_TIMEOUT_SECONDS", "inf"),
        ("VISUAL_INSPECTION_TIMEOUT_SECONDS", "private-invalid-timeout"),
        ("MCP_PDF_SERVER_EXECUTABLE", "directory"),
        ("MCP_PDF_SERVER_CWD", "file"),
    ],
)
def test_mcp_cli_rejects_configuration_before_runtime(
    tmp_path, monkeypatch, capsys, name, value
):
    monkeypatch.chdir(tmp_path)
    environment = _mcp_environment(tmp_path)
    for key, configured in environment.items():
        monkeypatch.setenv(key, configured)
    if value is None:
        monkeypatch.delenv(name)
    else:
        replacement = (
            environment["MCP_PDF_SERVER_CWD"]
            if value == "directory"
            else environment["MCP_PDF_SERVER_EXECUTABLE"]
            if value == "file"
            else value
        )
        monkeypatch.setenv(name, replacement)
    runtime = AsyncMock()
    monkeypatch.setattr(cli, "probe", runtime)

    assert cli.main(["extract-architecture-mcp", str(tmp_path / "run")]) == 1
    runtime.assert_not_called()
    output = capsys.readouterr()
    assert name in output.err
    assert "private-invalid-timeout" not in output.err
    assert environment["SKYNET_API_KEY"] not in output.out + output.err
    assert not (tmp_path / "run/mcp").exists()


@pytest.mark.parametrize("budget", ["0", "-1", "banana"])
def test_mcp_cli_rejects_invalid_budget(monkeypatch, budget):
    runtime = AsyncMock()
    monkeypatch.setattr(cli, "probe", runtime)
    with pytest.raises(SystemExit) as caught:
        cli.main(["extract-architecture-mcp", "run", "--max-turns", budget])
    assert caught.value.code == 2
    runtime.assert_not_called()


@pytest.mark.parametrize(
    "failure, code, message",
    [
        (
            cli.ProbeError("Execution failure diagnostics could not be persisted."),
            1,
            "diagnostics could not be persisted",
        ),
        (RuntimeError("private third-party test-key"), 1, "check configuration"),
        (asyncio.CancelledError(), 130, "cancelled"),
        (KeyboardInterrupt(), 130, "cancelled"),
    ],
)
def test_mcp_cli_controlled_errors_and_logging_restoration(
    tmp_path, monkeypatch, capsys, failure, code, message
):
    monkeypatch.chdir(tmp_path)
    for name, value in _mcp_environment(tmp_path).items():
        monkeypatch.setenv(name, value)
    previous_logging_disable = logging.root.manager.disable

    async def fail(*args, **kwargs):
        assert logging.root.manager.disable == logging.CRITICAL
        logging.getLogger("synthetic-sdk").critical("private SDK test-key")
        raise failure

    monkeypatch.setattr(cli, "probe", fail)
    assert cli.main(["extract-architecture-mcp", str(tmp_path / "run")]) == code
    assert logging.root.manager.disable == previous_logging_disable
    output = capsys.readouterr()
    assert output.out == ""
    assert message in output.err
    assert "private" not in output.err and "test-key" not in output.err
