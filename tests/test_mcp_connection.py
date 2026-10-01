import asyncio
import importlib.util
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from mcp.shared.message import SessionMessage
from mcp.types import (
    CallToolResult,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    TextContent,
)
from pypdf import PdfWriter

from antenna_paper_extraction.persistence import write_json
from antenna_paper_extraction.runs import create_run, sha256_file

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_mcp_connection.py"
spec = importlib.util.spec_from_file_location("probe_mcp_connection", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def configured_run(tmp_path):
    pdf = tmp_path / "paper with spaces.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(pdf)
    run_dir = create_run(pdf, tmp_path / "runs with spaces")
    cwd = tmp_path / "external server with spaces"
    cwd.mkdir()
    executable = cwd / "server executable.exe"
    executable.touch()
    return run_dir, executable, cwd


def overview_result(digest):
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "paper": "paper with spaces.pdf",
                        "document_id": digest,
                        "pdf_pages": 1,
                        "outline": [],
                    }
                ),
            )
        ]
    )


@pytest.fixture
def fake_connection(monkeypatch, configured_run):
    run_dir, _, _ = configured_run
    digest = sha256_file(run_dir / "input" / "paper with spaces.pdf")

    class FakeConnection:
        def __init__(self):
            self.tools = sorted(probe.EXPECTED_TOOLS)
            self.result = overview_result(digest)
            self.calls = []
            self.entered = False
            self.closed = False

        async def __aenter__(self):
            self.entered = True
            return self

        async def __aexit__(self, *args):
            self.closed = True

        async def list_tools(self):
            return [SimpleNamespace(name=name) for name in self.tools]

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            if isinstance(self.result, BaseException):
                raise self.result
            return self.result

    connection = FakeConnection()

    def factory(**kwargs):
        connection.configuration = kwargs
        return connection

    monkeypatch.setattr(probe, "QuietStdioServer", factory)
    return connection


@pytest.mark.parametrize("prefix", ["", "sha256:"])
def test_matching_identity_and_only_overview(
    configured_run, fake_connection, monkeypatch, capsys, prefix
):
    import agents
    import openai

    def forbidden(*args, **kwargs):
        pytest.fail("The deterministic probe must not create agents/model clients.")

    monkeypatch.setattr(agents, "Agent", forbidden)
    monkeypatch.setattr(agents.Runner, "run", forbidden)
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    run_dir, executable, cwd = configured_run
    before = {
        name: (run_dir / name).read_bytes() for name in ("manifest.json", "status.json")
    }
    payload = json.loads(fake_connection.result.content[0].text)
    fake_connection.result = overview_result(prefix + payload["document_id"])

    asyncio.run(probe.probe(*configured_run))

    assert fake_connection.entered and fake_connection.closed
    assert fake_connection.calls == [("get_paper_overview", {})]
    assert not (run_dir / "pages").exists()
    assert not (run_dir / "mcp").exists()  # The probe itself creates no store.
    assert before == {name: (run_dir / name).read_bytes() for name in before}
    config = fake_connection.configuration
    assert config["params"]["command"] == str(executable.resolve())
    assert config["params"]["cwd"] == str(cwd.resolve())
    assert config["params"]["args"] == []
    assert config["client_session_timeout_seconds"] == 600
    assert config["max_retry_attempts"] == 0
    assert config["failure_error_function"] is None
    assert "Connection verified; model calls: 0." in capsys.readouterr().out


def test_child_environment_preserves_launch_paths_without_credentials(
    configured_run, monkeypatch
):
    run_dir, _, _ = configured_run
    for name in ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "WINDIR"):
        monkeypatch.setenv(name, f"C:\\path with spaces\\{name}")
    for name in (
        "SKYNET_API_KEY",
        "OPENAI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "SKYNET_BASE_URL",
        "VISUAL_INSPECTION_MODEL",
        "ARBITRARY_MODEL_TOKEN",
    ):
        monkeypatch.setenv(name, "secret-or-model-setting")
    before = dict(os.environ)
    pdf = run_dir / "input" / "paper with spaces.pdf"

    env = probe.child_environment(pdf, run_dir)

    assert env["PDF_INGESTION_PDF"] == str(pdf.resolve())
    assert env["PDF_INGESTION_RUN_DIR"] == str((run_dir / "mcp").resolve())
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    for name in ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "WINDIR"):
        assert env[name] == before[name]
    assert "secret-or-model-setting" not in env.values()
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    "change", ["pdf", "source_hash", "document_id", "escape", "absolute"]
)
def test_reject_invalid_pdf_identity_or_path_before_startup(
    configured_run, fake_connection, change, tmp_path
):
    run_dir, _, _ = configured_run
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if change == "pdf":
        (run_dir / manifest["source_pdf"]["relative_path"]).write_bytes(b"changed")
    elif change == "source_hash":
        manifest["source_pdf"]["sha256"] = "0" * 64
    elif change == "document_id":
        manifest["document_id"] = "sha256:" + "0" * 64
    elif change == "escape":
        manifest["source_pdf"]["relative_path"] = "../../outside.pdf"
    else:
        manifest["source_pdf"]["relative_path"] = str(tmp_path / "outside.pdf")
    write_json(path, manifest)

    with pytest.raises(probe.ProbeError):
        asyncio.run(probe.probe(*configured_run))
    assert not fake_connection.entered
    assert not hasattr(fake_connection, "configuration")


@pytest.mark.parametrize("change", ["missing", "identity", "pending"])
def test_require_initialized_run(configured_run, fake_connection, change):
    run_dir, _, _ = configured_run
    path = run_dir / "status.json"
    if change == "missing":
        path.unlink()
    else:
        status = json.loads(path.read_text(encoding="utf-8"))
        if change == "identity":
            status["run_id"] = "another-run"
        else:
            status["phases"]["source_preservation"] = {"state": "pending"}
        write_json(path, status)
    with pytest.raises(probe.ProbeError):
        asyncio.run(probe.probe(*configured_run))
    assert not fake_connection.entered


@pytest.mark.parametrize("target", ["input", "manifest.json", "mcp"])
def test_reject_symlink_escape(configured_run, fake_connection, tmp_path, target):
    run_dir, _, _ = configured_run
    path = run_dir / target
    outside = tmp_path / "outside"
    outside.mkdir()
    if target == "manifest.json":
        destination = outside / target
        destination.write_bytes(path.read_bytes())
        path.unlink()
    else:
        destination = outside
        if target == "input":
            pdf = path / "paper with spaces.pdf"
            pdf.rename(outside / pdf.name)
            path.rmdir()
    try:
        path.symlink_to(destination, target_is_directory=target != "manifest.json")
    except OSError:
        pytest.skip("This Windows environment does not permit symlink creation.")
    with pytest.raises(probe.ProbeError):
        asyncio.run(probe.probe(*configured_run))
    assert not fake_connection.entered


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate"])
def test_exact_tool_discovery(configured_run, fake_connection, change):
    if change == "missing":
        fake_connection.tools.pop()
    elif change == "extra":
        fake_connection.tools.append("unexpected_tool")
    else:
        fake_connection.tools.append(fake_connection.tools[0])
    with pytest.raises(probe.ProbeError, match="exactly the six"):
        asyncio.run(probe.probe(*configured_run))
    assert fake_connection.closed
    assert fake_connection.calls == []


@pytest.mark.parametrize(
    "response, diagnostic",
    [
        (overview_result("0" * 64), "does not match"),
        (CallToolResult(content=[], isError=True), "MCP error"),
        (CallToolResult(content=[]), "one JSON text"),
        (
            CallToolResult(content=[TextContent(type="text", text="{bad")]),
            "malformed JSON",
        ),
        (
            CallToolResult(content=[TextContent(type="text", text="{}")]),
            "missing or invalid",
        ),
        (
            CallToolResult(content=[TextContent(type="text", text="[]")]),
            "missing or invalid",
        ),
        (overview_result("invalid-fingerprint"), "missing or invalid"),
        (overview_result(123), "missing or invalid"),
    ],
)
def test_overview_failures_close_connection(
    configured_run, fake_connection, response, diagnostic
):
    fake_connection.result = response
    with pytest.raises(probe.ProbeError, match=diagnostic):
        asyncio.run(probe.probe(*configured_run))
    assert fake_connection.closed


def arguments(configured_run):
    run_dir, executable, cwd = configured_run
    return [
        "--run-dir",
        str(run_dir),
        "--mcp-executable",
        str(executable),
        "--mcp-cwd",
        str(cwd),
    ]


def test_exit_codes_and_sensitive_errors(configured_run, fake_connection, capsys):
    assert probe.main(arguments(configured_run)) == 0
    fake_connection.result = RuntimeError("credential=do-not-print-this")
    assert probe.main(arguments(configured_run)) == 1
    output = capsys.readouterr()
    assert "verification failed" in output.err
    assert "do-not-print-this" not in output.err + output.out
    assert fake_connection.closed


def test_cancellation_exit_code(configured_run, fake_connection, capsys):
    fake_connection.result = asyncio.CancelledError()
    assert probe.main(arguments(configured_run)) == 130
    assert fake_connection.closed
    output = capsys.readouterr()
    assert "cancelled" in output.err
    assert "Connection verified" not in output.out


@pytest.mark.parametrize(
    "outcome", ["success", "mismatch", "cancel", "startup_cancel", "startup_error"]
)
def test_installed_sdk_closes_scripted_transport(configured_run, monkeypatch, outcome):
    """Exercise SDK context cleanup through public in-memory transport streams."""
    run_dir, _, _ = configured_run
    digest = sha256_file(run_dir / "input" / "paper with spaces.pdf")
    state = {"closed": False, "calls": []}

    async def exercise():
        reached = asyncio.Event()

        @asynccontextmanager
        async def transport(params, errlog):
            assert errlog.name == os.devnull
            replies, reader = anyio.create_memory_object_stream(0)
            # Model a draining stdin pipe, including cancellation notifications.
            writer, requests = anyio.create_memory_object_stream(10)

            async def serve():
                async for packet in requests:
                    request = packet.message
                    if not isinstance(request, JSONRPCRequest):
                        continue
                    if request.method == "server/discover":
                        await replies.send(
                            SessionMessage(
                                JSONRPCError(
                                    jsonrpc="2.0",
                                    id=request.id,
                                    error={
                                        "code": -32601,
                                        "message": "Method not found",
                                    },
                                )
                            )
                        )
                        continue
                    elif request.method == "initialize":
                        if outcome == "startup_cancel":
                            reached.set()
                            await asyncio.Event().wait()
                        result = {
                            "protocolVersion": request.params["protocolVersion"],
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "scripted", "version": "1"},
                        }
                    elif request.method == "tools/list":
                        result = {
                            "tools": [
                                {"name": name, "inputSchema": {"type": "object"}}
                                for name in sorted(probe.EXPECTED_TOOLS)
                            ]
                        }
                    elif request.method == "tools/call":
                        state["calls"].append(request.params)
                        if outcome == "cancel":
                            reached.set()
                            await asyncio.Event().wait()
                        result = overview_result(
                            "0" * 64 if outcome == "mismatch" else digest
                        ).model_dump(mode="json", by_alias=True)
                    else:
                        pytest.fail(f"Unexpected method: {request.method}")
                    await replies.send(
                        SessionMessage(
                            JSONRPCResponse(jsonrpc="2.0", id=request.id, result=result)
                        )
                    )

            try:
                if outcome == "startup_error":
                    raise RuntimeError("sensitive startup error body")
                async with anyio.create_task_group() as group:
                    group.start_soon(serve)
                    try:
                        yield reader, writer
                    finally:
                        group.cancel_scope.cancel()
            finally:
                state["closed"] = True
                for stream in (replies, reader, writer, requests):
                    stream.close()

        monkeypatch.setattr(probe, "stdio_client", transport)
        if outcome in ("cancel", "startup_cancel"):
            task = asyncio.create_task(probe.probe(*configured_run))
            await asyncio.wait_for(reached.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
        elif outcome == "startup_error":
            with pytest.raises(probe.ProbeError, match="MCP startup failed"):
                await probe.probe(*configured_run)
        elif outcome == "mismatch":
            with pytest.raises(probe.ProbeError, match="does not match"):
                await probe.probe(*configured_run)
        else:
            await probe.probe(*configured_run)

    asyncio.run(exercise())
    assert state["closed"]
    if outcome in ("startup_cancel", "startup_error"):
        assert state["calls"] == []
    else:
        assert len(state["calls"]) == 1
        assert state["calls"][0]["name"] == "get_paper_overview"
        assert state["calls"][0]["arguments"] == {}
