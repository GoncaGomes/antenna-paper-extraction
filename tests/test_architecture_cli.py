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
