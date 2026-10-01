import asyncio
import importlib.util
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
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

from antenna_paper_extraction import persistence
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

    class FakeConnection(probe.QuietStdioServer):
        def __init__(self):
            self.tools = sorted(probe.EXPECTED_TOOLS)
            self.result = overview_result(digest)
            self.calls = []
            self.metas = []
            self.entered = False
            self.closed = False

        async def __aenter__(self):
            self.entered = True
            return self

        async def __aexit__(self, *args):
            self.closed = True

        async def list_tools(self):
            return [SimpleNamespace(name=name) for name in self.tools]

        async def execute_tool(self, name, arguments, meta=None):
            saved = json.loads(self.trace.path.read_text(encoding="utf-8"))
            assert saved["calls"][-1]["state"] == "started"
            assert saved["calls"][-1]["tool_name"] == name
            self.calls.append((name, arguments))
            self.metas.append(meta)
            if isinstance(self.result, BaseException):
                raise self.result
            return self.result

    connection = FakeConnection()

    def factory(**kwargs):
        connection.configuration = kwargs
        connection.trace = kwargs["trace"]
        return connection

    async def base_call(server, tool_name, arguments, meta=None):
        return await server.execute_tool(tool_name, arguments, meta)

    monkeypatch.setattr(probe.MCPServerStdio, "call_tool", base_call)
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
    assert not (run_dir / "mcp" / "store").exists()
    assert len(list((run_dir / "mcp").iterdir())) == 1
    trace = read_trace(run_dir)
    assert trace["state"] == "succeeded"
    assert trace["run_id"] == json.loads(before["manifest.json"])["run_id"]
    assert trace["document_id"] == json.loads(before["manifest.json"])["document_id"]
    assert trace["calls"][0]["state"] == "returned"
    assert before == {name: (run_dir / name).read_bytes() for name in before}
    config = fake_connection.configuration
    assert config["params"]["command"] == str(executable.resolve())
    assert config["params"]["cwd"] == str(cwd.resolve())
    assert config["params"]["args"] == []
    assert config["client_session_timeout_seconds"] == 600
    assert config["max_retry_attempts"] == 0
    assert config["failure_error_function"] is None
    assert "Connection verified; model calls: 0." in capsys.readouterr().out


def read_trace(run_dir):
    paths = list((run_dir / "mcp").glob("probe_connection_*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text(encoding="utf-8"))


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
    assert not (run_dir / "mcp").exists()


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
    assert read_trace(configured_run[0])["state"] == "failed"


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
    trace = read_trace(configured_run[0])
    assert trace["state"] == "failed"
    assert trace["calls"][0]["state"] == (
        "mcp_error" if response.model_dump(by_alias=True)["isError"] else "returned"
    )
    assert trace["calls"][0]["response"] == response.model_dump(
        mode="json", by_alias=True
    )


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
    trace = read_trace(configured_run[0])
    assert trace["state"] == "cancelled"
    assert trace["calls"][0]["state"] == "cancelled"
    assert trace["calls"][0]["exception_type"] == "CancelledError"


def test_ordered_complete_responses_saved_before_return(
    configured_run, fake_connection
):
    run_dir, _, _ = configured_run
    manifest, _, _ = probe.verify_run(run_dir.resolve())
    fake_connection.trace = probe.ProbeTrace(run_dir, manifest)
    payload = json.loads(fake_connection.result.content[0].text)
    payload["outline"] = [{"title": "Geometry", "pages": [1]}]
    payload["evidence"] = "Ordinary evidence beyond identity fields."
    fake_connection.result = CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent={"extra": [1, {"value": "complete evidence"}]},
        _meta={"server_marker": "preserved"},
    )
    expected = fake_connection.result.model_dump(mode="json", by_alias=True)

    async def exercise():
        for index in range(2):
            result = await fake_connection.call_tool(
                "get_paper_overview", {"index": index}, meta={"test": index}
            )
            saved = read_trace(run_dir)
            assert len(saved["calls"]) == index + 1
            assert saved["calls"][-1]["response"] == expected
            assert result is fake_connection.result
            assert probe.decode_overview(result).document_id == payload["document_id"]

    asyncio.run(exercise())
    trace = read_trace(run_dir)
    first, second = trace["calls"]
    assert first["call_id"] != second["call_id"]
    assert fake_connection.metas == [{"test": 0}, {"test": 1}]
    assert [call["arguments"] for call in trace["calls"]] == [
        {"index": 0},
        {"index": 1},
    ]
    for call in trace["calls"]:
        assert call["trace_id"] == trace["trace_id"]
        assert call["call_id_source"] == "locally_generated"
        assert call["state"] == "returned"
        assert call["elapsed_seconds"] >= 0
        assert datetime.fromisoformat(call["started_at"]).utcoffset() is not None
        assert datetime.fromisoformat(call["finished_at"]) >= datetime.fromisoformat(
            call["started_at"]
        )
    assert datetime.fromisoformat(trace["started_at"]).utcoffset() is not None


def test_response_persisted_before_identity_validation(
    configured_run, fake_connection, monkeypatch
):
    decode = probe.decode_overview

    def checked_decode(result):
        saved = read_trace(configured_run[0])
        assert saved["state"] == "running"
        assert saved["calls"][0]["response"] == result.model_dump(
            mode="json", by_alias=True
        )
        assert saved["calls"][0]["state"] == "returned"
        return decode(result)

    monkeypatch.setattr(probe, "decode_overview", checked_decode)
    asyncio.run(probe.probe(*configured_run))


@pytest.mark.parametrize("failed_write", [1, 2, 3, 4])
def test_required_persistence_failure_stops_probe_and_keeps_last_trace(
    configured_run, fake_connection, monkeypatch, capsys, failed_write
):
    replace = persistence.os.replace
    writes = []
    previous = []
    decoded = []
    decode = probe.decode_overview

    def checked_decode(result):
        decoded.append(result)
        return decode(result)

    def failing_replace(source, destination):
        writes.append(destination)
        if len(writes) == failed_write:
            previous.append(destination.read_bytes() if destination.exists() else None)
            raise OSError("external sensitive persistence error")
        replace(source, destination)

    monkeypatch.setattr(persistence.os, "replace", failing_replace)
    monkeypatch.setattr(probe, "decode_overview", checked_decode)
    assert probe.main(arguments(configured_run)) == 1
    output = capsys.readouterr()
    assert "trace persistence failed" in output.err
    assert "external sensitive" not in output.out + output.err
    assert "Connection verified" not in output.out
    assert len(fake_connection.calls) == (1 if failed_write >= 3 else 0)
    assert len(decoded) == (1 if failed_write == 4 else 0)
    assert len(writes) == failed_write
    if failed_write == 1:
        assert not fake_connection.entered
        assert not writes[-1].exists()
    else:
        assert fake_connection.closed
        assert "Trace:" in output.out
        assert writes[-1].read_bytes() == previous[0]
        saved = read_trace(configured_run[0])
        assert saved["state"] == "running"
        if failed_write == 2:
            assert saved["calls"] == []
        else:
            assert saved["calls"][0]["state"] == (
                "started" if failed_write == 3 else "returned"
            )
    assert not list((configured_run[0] / "mcp").glob("*.tmp"))


@pytest.mark.parametrize(
    "outcome, failed_write",
    [
        ("transport", 3),
        ("transport", 4),
        ("cancel", 3),
        ("cancel", 4),
        ("validation", 4),
    ],
)
def test_diagnostic_write_failure_does_not_hide_original_outcome(
    configured_run, fake_connection, monkeypatch, capsys, outcome, failed_write
):
    if outcome == "transport":
        fake_connection.result = RuntimeError("sensitive transport message")
    elif outcome == "cancel":
        fake_connection.result = asyncio.CancelledError("sensitive cancellation")
    else:
        fake_connection.result = overview_result("0" * 64)
    replace = persistence.os.replace
    writes = []

    def failing_replace(source, destination):
        writes.append(destination)
        if len(writes) == failed_write:
            raise OSError("sensitive diagnostic write failure")
        replace(source, destination)

    monkeypatch.setattr(persistence.os, "replace", failing_replace)
    assert probe.main(arguments(configured_run)) == (130 if outcome == "cancel" else 1)
    assert fake_connection.closed
    output = capsys.readouterr()
    assert "sensitive" not in output.out + output.err
    assert "trace persistence failed" not in output.err
    assert (
        "does not match"
        if outcome == "validation"
        else "cancelled"
        if outcome == "cancel"
        else "MCP get_paper_overview failed"
    ) in output.err
    saved = read_trace(configured_run[0])
    assert saved["state"] == "running"
    assert saved["calls"][0]["state"] == (
        "started"
        if failed_write == 3
        else "returned"
        if outcome == "validation"
        else "cancelled"
        if outcome == "cancel"
        else "transport_error"
    )


def test_transport_error_records_exception_type_without_message(
    configured_run, fake_connection, capsys
):
    fake_connection.result = RuntimeError("raw credential-bearing exception message")
    assert probe.main(arguments(configured_run)) == 1
    trace = read_trace(configured_run[0])
    assert trace["state"] == "failed"
    call = trace["calls"][0]
    assert call["state"] == "transport_error"
    assert call["exception_type"] == "RuntimeError"
    assert call["elapsed_seconds"] >= 0
    assert "raw credential" not in json.dumps(trace)
    assert "Trace:" in capsys.readouterr().out
    assert fake_connection.closed


def test_success_requires_cleanup(configured_run, fake_connection, monkeypatch, capsys):
    async def failing_exit(self, *args):
        self.closed = True
        assert read_trace(configured_run[0])["state"] == "running"
        raise RuntimeError("sensitive cleanup message")

    monkeypatch.setattr(type(fake_connection), "__aexit__", failing_exit)
    assert probe.main(arguments(configured_run)) == 1
    trace = read_trace(configured_run[0])
    assert trace["state"] == "failed"
    assert trace["calls"][0]["state"] == "returned"
    assert "MCP cleanup failed" in trace["diagnostic"]
    assert "Connection verified" not in capsys.readouterr().out


def test_separate_probe_invocations_preserve_previous_trace(
    configured_run, fake_connection
):
    run_dir, _, _ = configured_run
    asyncio.run(probe.probe(*configured_run))
    first_path = next((run_dir / "mcp").glob("probe_connection_*.json"))
    first_bytes = first_path.read_bytes()
    asyncio.run(probe.probe(*configured_run))
    paths = list((run_dir / "mcp").glob("probe_connection_*.json"))
    assert len(paths) == 2
    assert first_path.read_bytes() == first_bytes
    traces = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert len({trace["trace_id"] for trace in traces}) == 2
    assert all(trace["state"] == "succeeded" for trace in traces)


def test_credentials_and_images_excluded_without_reducing_evidence(
    configured_run, fake_connection, monkeypatch
):
    run_dir, _, _ = configured_run
    for key, value in {
        "SKYNET_API_KEY": "synthetic-api-secret",
        "ARBITRARY_MODEL_TOKEN": "synthetic-token-secret",
        "SERVICE_PASSWORD": "synthetic-password-secret",
    }.items():
        monkeypatch.setenv(key, value)
    evidence = "Reported antenna dimensions: 12 x 24 mm."
    payload = {
        "content": [
            {"type": "text", "text": evidence + " synthetic-api-secret"},
            {
                "type": "image",
                "data": "synthetic-image-base64",
                "mimeType": "image/png",
            },
            {
                "type": "resource",
                "resource": {
                    "uri": "asset://figure/1",
                    "mimeType": "image/png",
                    "blob": "synthetic-embedded-image",
                },
            },
            {
                "type": "text",
                "text": 'Evidence <img src="data:image/png;base64,synthetic-uri-image"> remains.',
            },
        ],
        "structuredContent": {
            "evidence": evidence,
            "token": "Bearer synthetic-token-secret",
            "nested": [{"uri": "data:image/jpeg;base64,synthetic-nested-image"}],
        },
        "isError": False,
        "_meta": {"password": "synthetic-password-secret"},
    }
    fake_connection.result = CallToolResult.model_validate(payload)
    original = fake_connection.result.model_dump(mode="json", by_alias=True)
    manifest, _, _ = probe.verify_run(run_dir.resolve())
    fake_connection.trace = probe.ProbeTrace(run_dir, manifest)
    call_arguments = {
        "query": evidence,
        "authorization": "Bearer synthetic-api-secret",
        "image": "data:image/png;base64,synthetic-argument-image",
    }
    result = asyncio.run(fake_connection.call_tool("read_pages", call_arguments))
    trace = read_trace(run_dir)
    serialized = json.dumps(trace)
    for omitted in (
        "synthetic-api-secret",
        "synthetic-token-secret",
        "synthetic-password-secret",
        "synthetic-image-base64",
        "synthetic-embedded-image",
        "synthetic-uri-image",
        "synthetic-nested-image",
        "synthetic-argument-image",
    ):
        assert omitted not in serialized
    response = trace["calls"][0]["response"]
    assert response["structuredContent"]["evidence"] == evidence
    assert response["content"][0]["text"] == evidence + " [redacted credential]"
    assert response["content"][1]["data_omitted"] == "image payload"
    assert response["content"][1]["mimeType"] == "image/png"
    assert response["content"][2]["resource"]["blob_omitted"] == "image payload"
    assert response["content"][3]["text"] == (
        'Evidence <img src="[omitted image data URI]"> remains.'
    )
    assert response["isError"] is False
    assert "_meta" in response
    assert trace["calls"][0]["arguments"]["query"] == evidence
    assert result.model_dump(mode="json", by_alias=True) == original
    assert call_arguments["authorization"] == "Bearer synthetic-api-secret"
    assert "params" not in trace and "env" not in trace


@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "mismatch",
        "error",
        "malformed",
        "transport",
        "cancel",
        "startup_cancel",
        "startup_error",
    ],
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
                        assert read_trace(run_dir)["calls"][0]["state"] == "started"
                        state["calls"].append(request.params)
                        if outcome == "cancel":
                            reached.set()
                            await asyncio.Event().wait()
                        if outcome == "transport":
                            await replies.send(
                                SessionMessage(
                                    JSONRPCError(
                                        jsonrpc="2.0",
                                        id=request.id,
                                        error={
                                            "code": -32603,
                                            "message": "sensitive remote error",
                                        },
                                    )
                                )
                            )
                            continue
                        if outcome == "error":
                            response = CallToolResult(content=[], isError=True)
                        elif outcome == "malformed":
                            response = CallToolResult(
                                content=[TextContent(type="text", text="{bad")]
                            )
                        else:
                            response = overview_result(
                                "0" * 64 if outcome == "mismatch" else digest
                            )
                        result = response.model_dump(mode="json", by_alias=True)
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
        elif outcome in ("error", "malformed", "transport"):
            with pytest.raises(probe.ProbeError):
                await probe.probe(*configured_run)
        else:
            await probe.probe(*configured_run)

    asyncio.run(exercise())
    assert state["closed"]
    trace = read_trace(run_dir)
    assert trace["state"] == (
        "succeeded"
        if outcome == "success"
        else "cancelled"
        if "cancel" in outcome
        else "failed"
    )
    assert datetime.fromisoformat(trace["finished_at"]).utcoffset() is not None
    if outcome in ("startup_cancel", "startup_error"):
        assert state["calls"] == []
        assert trace["calls"] == []
    else:
        assert len(state["calls"]) == 1
        assert state["calls"][0]["name"] == "get_paper_overview"
        assert state["calls"][0]["arguments"] == {}
        call = trace["calls"][0]
        assert call["state"] == (
            "cancelled"
            if outcome == "cancel"
            else "mcp_error"
            if outcome == "error"
            else "transport_error"
            if outcome == "transport"
            else "returned"
        )
        assert "sensitive remote error" not in json.dumps(trace)


# These tests use the real Runner, Chat Completions conversion, and MCP client.
def read_agent_trace(run_dir):
    paths = list((run_dir / "mcp").glob("probe_agent_*.json"))
    if len(paths) > 1:
        paths = [
            p
            for p in paths
            if json.loads(p.read_text(encoding="utf-8"))["state"] == "running"
        ]
    assert len(paths) == 1
    return json.loads(paths[0].read_text(encoding="utf-8"))


def completion(*tool_calls, text=None, finish=None, choices=True):
    from openai.types.chat import ChatCompletion

    return ChatCompletion.model_validate(
        {
            "id": "provider-response",
            "object": "chat.completion",
            "created": 1,
            "model": "explicit-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish or ("tool_calls" if tool_calls else "stop"),
                    "message": {
                        "role": "assistant",
                        "content": text,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(args),
                                },
                            }
                            for call_id, name, args in tool_calls
                        ]
                        or None,
                    },
                }
            ]
            if choices
            else [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "provider_extra": {"preserved": True},
        }
    )


@pytest.fixture
def agent_script(configured_run, monkeypatch, tmp_path):
    from openai import AsyncOpenAI
    from openai.resources.chat.completions import AsyncCompletions

    run_dir, _, _ = configured_run
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKYNET_BASE_URL", "https://model.invalid/v1")
    monkeypatch.setenv("SKYNET_API_KEY", "synthetic-agent-secret")
    for key in ("VISUAL_INSPECTION_MODEL", "VISUAL_INSPECTION_TIMEOUT_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    state = SimpleNamespace(
        responses=[],
        requests=[],
        calls=[],
        closed=False,
        model_closed=False,
        active=0,
        max_active=0,
        tool_result=None,
        tool_results=[],
        before_model=None,
        model_entered=None,
        tool_entered=None,
    )

    async def create(resource, **kwargs):
        assert resource._client.max_retries == 0
        assert resource._client.timeout == 600
        saved = read_agent_trace(run_dir)
        assert saved["model_requests"][-1]["state"] == "started"
        messages = saved["model_requests"][-1]["request"]["messages"]
        assert len(messages) == len(kwargs["messages"])
        assert messages[0] == kwargs["messages"][0]
        state.requests.append(kwargs)
        if state.before_model is not None:
            state.before_model(saved)
        if state.model_entered is not None:
            state.model_entered.set()
            await asyncio.Event().wait()
        assert state.responses, "Unexpected model request or retry"
        result = state.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    close = AsyncOpenAI.close
    call_tool = probe.QuietStdioServer.call_tool

    async def measured_call(server, tool_name, arguments, meta=None):
        state.active += 1
        state.max_active = max(state.max_active, state.active)
        try:
            # Measure outstanding SDK invocations, even if transport handles serially.
            await asyncio.sleep(0.01)
            return await call_tool(server, tool_name, arguments, meta=meta)
        finally:
            state.active -= 1

    async def recorded_close(client):
        state.model_closed = True
        await close(client)

    @asynccontextmanager
    async def transport(params, errlog):
        state.environment = params.env
        replies, reader = anyio.create_memory_object_stream(0)
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
                                error={"code": -32601, "message": "Method not found"},
                            )
                        )
                    )
                    continue
                if request.method == "initialize":
                    result = {
                        "protocolVersion": request.params["protocolVersion"],
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "scripted", "version": "1"},
                    }
                elif request.method == "tools/list":
                    result = {
                        "tools": [
                            {
                                "name": name,
                                "description": f"Evidence tool {name}",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                            for name in sorted(probe.EXPECTED_TOOLS)
                        ]
                    }
                elif request.method == "tools/call":
                    saved = (
                        read_agent_trace(run_dir)
                        if list((run_dir / "mcp").glob("probe_agent_*.json"))
                        else read_trace(run_dir)
                    )
                    assert saved["calls"][-1]["state"] == "started"
                    if state.calls:
                        # The response must be durable before execution, including extras.
                        raw = saved["model_requests"][-1]["response"]
                        assert raw["provider_extra"] == {"preserved": True}
                        assert saved["calls"][-1]["sdk_tool_call_id"] in [
                            t["id"] for t in raw["choices"][0]["message"]["tool_calls"]
                        ]
                    state.calls.append(request.params)
                    if len(state.calls) == 1:
                        digest = sha256_file(
                            run_dir / "input" / "paper with spaces.pdf"
                        )
                        response = overview_result(digest)
                    else:
                        if state.tool_entered is not None:
                            state.tool_entered.set()
                            await asyncio.Event().wait()
                        if isinstance(state.tool_result, BaseException):
                            await replies.send(
                                SessionMessage(
                                    JSONRPCError(
                                        jsonrpc="2.0",
                                        id=request.id,
                                        error={
                                            "code": -32603,
                                            "message": "sensitive transport failure",
                                        },
                                    )
                                )
                            )
                            continue
                        response = (
                            state.tool_results.pop(0)
                            if state.tool_results
                            else state.tool_result
                        ) or CallToolResult(
                            content=[
                                TextContent(
                                    type="text", text="Page 1: patch length L=12 mm."
                                )
                            ]
                        )
                    result = response.model_dump(mode="json", by_alias=True)
                else:
                    pytest.fail(f"Unexpected MCP method: {request.method}")
                await replies.send(
                    SessionMessage(
                        JSONRPCResponse(
                            jsonrpc="2.0",
                            id=request.id,
                            result=result,
                        )
                    )
                )

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(serve)
                try:
                    yield reader, writer
                finally:
                    group.cancel_scope.cancel()
        finally:
            paths = list((run_dir / "mcp").glob("probe_agent_*.json"))
            if len(paths) == 1:
                assert read_agent_trace(run_dir)["state"] == "running"
            state.closed = True
            for stream in (replies, reader, writer, requests):
                stream.close()

    monkeypatch.setattr(AsyncCompletions, "create", create)
    monkeypatch.setattr(AsyncOpenAI, "close", recorded_close)
    monkeypatch.setattr(probe.QuietStdioServer, "call_tool", measured_call)
    monkeypatch.setattr(probe, "stdio_client", transport)
    return state


def agent_arguments(configured_run, turns=8):
    return arguments(configured_run) + [
        "--agent-model",
        "explicit-model",
        "--max-turns",
        str(turns),
    ]


def test_agent_multiple_rounds_and_sequential_tools(configured_run, agent_script):
    run_dir, _, _ = configured_run
    before = {
        name: (run_dir / name).read_bytes() for name in ("manifest.json", "status.json")
    }
    agent_script.responses = [
        completion(
            ("sdk-search", "search_paper", {"query": "geometry"}),
            ("sdk-pages", "read_pages", {"pages": [1]}),
        ),
        completion(
            ("sdk-asset", "get_asset", {"asset_id": "page:1", "question": "Read L."})
        ),
        completion(text="Page 1: patch length L=12 mm; width is uncertain."),
    ]
    assert probe.main(agent_arguments(configured_run)) == 0
    saved = read_agent_trace(run_dir)
    assert saved["state"] == "succeeded"
    assert saved["termination_reason"] == "final_answer"
    assert saved["counts"] == {
        "model_requests": 3,
        "model_responses": 3,
        "mcp_calls": 4,
    }
    assert saved["usage"]["total_tokens"] == 45
    assert saved["final_text"].startswith("Page 1:")
    assert agent_script.closed and agent_script.model_closed
    assert agent_script.max_active == 1
    assert [c["name"] for c in agent_script.calls] == [
        "get_paper_overview",
        "search_paper",
        "read_pages",
        "get_asset",
    ]
    assert [c["sdk_tool_call_id"] for c in saved["calls"]] == [
        None,
        "sdk-search",
        "sdk-pages",
        "sdk-asset",
    ]
    for i, r in enumerate(saved["model_requests"], 1):
        assert r["order"] == i
        assert r["elapsed_seconds"] >= 0
        assert datetime.fromisoformat(r["started_at"]).utcoffset() is not None
        assert r["request"]["parallel_tool_calls"] is False
        assert {
            t["function"]["name"] for t in r["request"]["tools"]
        } == probe.EXPECTED_TOOLS
        assert r["request"]["messages"][0]["content"] == saved["instructions"]
        assert r["request"]["messages"] == agent_script.requests[i - 1]["messages"]
    assert (
        saved["calls"][1]["model_request_id"]
        == saved["model_requests"][0]["request_id"]
    )
    assert (
        saved["calls"][2]["model_request_id"]
        == saved["model_requests"][0]["request_id"]
    )
    assert (
        saved["calls"][3]["model_request_id"]
        == saved["model_requests"][1]["request_id"]
    )
    assert [e["type"] for e in saved["events"]] == [
        "mcp_call",
        "mcp_response",
        "model_request",
        "model_response",
        "mcp_call",
        "mcp_response",
        "mcp_call",
        "mcp_response",
        "model_request",
        "model_response",
        "mcp_call",
        "mcp_response",
        "model_request",
        "model_response",
    ]
    assert [e["order"] for e in saved["events"]] == list(range(1, 15))
    assert before == {name: (run_dir / name).read_bytes() for name in before}
    assert not (run_dir / "pages").exists()
    assert not (run_dir / "document_conversion").exists()
    assert "VISUAL_INSPECTION_MODEL" not in agent_script.environment
    assert agent_script.environment["SKYNET_API_KEY"] == "synthetic-agent-secret"


@pytest.mark.parametrize(
    "failure",
    [
        "max_turns",
        "model",
        "transport",
        "truncated",
        "empty",
        "no_choices",
        "invalid_arguments",
    ],
)
def test_agent_failure_records_and_cleanup(
    configured_run, agent_script, failure, capsys
):
    first = completion(("sdk-first", "read_section", {"section": "Design"}))
    if failure == "max_turns":
        agent_script.responses = [first]
        turns = 1
    elif failure == "model":
        agent_script.responses = [first, RuntimeError("sensitive model failure")]
        turns = 8
    elif failure == "transport":
        agent_script.responses = [first]
        agent_script.tool_result = RuntimeError("sensitive tool failure")
        turns = 8
    elif failure == "truncated":
        agent_script.responses = [
            completion(("sdk-no-run", "get_asset", {}), finish="length")
        ]
        turns = 8
    elif failure == "invalid_arguments":
        first.choices[0].message.tool_calls[0].function.arguments = "{invalid"
        agent_script.responses = [first]
        turns = 8
    else:
        agent_script.responses = [completion(text="", choices=failure != "no_choices")]
        turns = 8
    assert probe.main(agent_arguments(configured_run, turns)) == 1
    saved = read_agent_trace(configured_run[0])
    assert saved["state"] == "failed"
    assert saved["termination_reason"] == (
        "max_turns"
        if failure == "max_turns"
        else "tool_failure"
        if failure == "transport"
        else "model_failure"
    )
    assert saved["final_text"] is None
    assert agent_script.closed and agent_script.model_closed
    if failure in ("truncated", "empty", "no_choices", "invalid_arguments"):
        assert len(agent_script.calls) == 1
        assert saved["model_requests"][0]["response"]
    if failure == "truncated":
        assert (
            saved["model_requests"][0]["response"]["choices"][0]["finish_reason"]
            == "length"
        )
    if failure == "model":
        assert len(agent_script.requests) == 2
        assert saved["model_requests"][-1]["state"] == "model_error"
        assert saved["counts"]["model_responses"] == 1
    if failure == "transport":
        assert saved["calls"][-1]["state"] == "transport_error"
        assert len(agent_script.requests) == 1
    output = capsys.readouterr()
    assert "sensitive" not in output.out + output.err + json.dumps(saved)


@pytest.mark.parametrize("phase", ["model", "tool"])
def test_agent_cancellation_records_and_cleanup(configured_run, agent_script, phase):
    async def exercise():
        reached = asyncio.Event()
        if phase == "model":
            agent_script.model_entered = reached
        else:
            agent_script.tool_entered = reached
            agent_script.responses = [
                completion(("sdk-cancel", "get_asset", {"asset_id": "page:1"}))
            ]
        task = asyncio.create_task(
            probe.probe(*configured_run, agent_model="explicit-model")
        )
        await asyncio.wait_for(reached.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)

    asyncio.run(exercise())
    saved = read_agent_trace(configured_run[0])
    assert saved["state"] == "cancelled"
    assert saved["termination_reason"] == "cancellation"
    assert agent_script.closed and agent_script.model_closed
    if phase == "model":
        assert saved["model_requests"][-1]["state"] == "cancelled"
        assert "response" not in saved["model_requests"][-1]
    else:
        assert saved["calls"][-1]["state"] == "cancelled"


@pytest.mark.parametrize("failed_write", [4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
def test_agent_write_failure_stops_runner(
    configured_run, agent_script, monkeypatch, failed_write, capsys
):
    # Writes: init, preflight call/result, request/response, tool call/result,
    # next request/response, final text, overall finish.
    agent_script.responses = [
        completion(("sdk-first", "read_pages", {}), ("sdk-second", "search_paper", {})),
        completion(text="Insufficient evidence."),
    ]
    replace = persistence.os.replace
    writes = []

    def failing_replace(source, destination):
        writes.append(destination)
        if len(writes) == failed_write:
            raise OSError("sensitive persistence failure")
        replace(source, destination)

    monkeypatch.setattr(persistence.os, "replace", failing_replace)
    assert probe.main(agent_arguments(configured_run)) == 1
    saved = read_agent_trace(configured_run[0])
    assert saved["state"] == "running"
    assert agent_script.closed and agent_script.model_closed
    assert len(agent_script.requests) == (
        0 if failed_write == 4 else 1 if failed_write <= 10 else 2
    )
    assert len(agent_script.calls) == (
        1 if failed_write <= 6 else 2 if failed_write <= 8 else 3
    )
    assert len(writes) == failed_write
    output = capsys.readouterr()
    assert "trace persistence failed" in output.err
    assert "sensitive" not in output.out + output.err


def test_agent_redaction_and_visual_settings_from_dotenv(
    configured_run, agent_script, monkeypatch, tmp_path
):
    from mcp.types import ImageContent

    monkeypatch.delenv("SKYNET_API_KEY")
    (tmp_path / ".env").write_text(
        "SKYNET_API_KEY=dotenv-secret\nSKYNET_BASE_URL=https://file.invalid\n"
        "VISUAL_INSPECTION_MODEL=explicit-visual\nVISUAL_INSPECTION_TIMEOUT_SECONDS=600\n",
        encoding="utf-8",
    )
    agent_script.tool_result = CallToolResult(
        content=[
            TextContent(type="text", text="L=12 mm dotenv-secret"),
            ImageContent(type="image", data="aW1hZ2U=", mimeType="image/png"),
        ]
    )
    agent_script.responses = [
        completion(
            (
                "sdk-image",
                "get_asset",
                {"asset_id": "page:1", "question": "Read L dotenv-secret"},
            )
        ),
        completion(
            text="L=12 mm, page:1. dotenv-secret data:image/png;base64,aW1hZ2U="
        ),
    ]
    assert probe.main(agent_arguments(configured_run)) == 0
    saved = read_agent_trace(configured_run[0])
    serialized = json.dumps(saved)
    assert "dotenv-secret" not in serialized
    assert "aW1hZ2U=" not in serialized
    assert "extra_headers" not in serialized
    assert (
        saved["calls"][1]["response"]["content"][1]["data_omitted"] == "image payload"
    )
    assert saved["configuration"]["visual_model"] == "explicit-visual"
    assert agent_script.environment["SKYNET_BASE_URL"] == "https://model.invalid/v1"
    assert agent_script.environment["SKYNET_API_KEY"] == "dotenv-secret"
    assert agent_script.environment["VISUAL_INSPECTION_MODEL"] == "explicit-visual"
    assert agent_script.environment["VISUAL_INSPECTION_TIMEOUT_SECONDS"] == "600"


def test_connection_does_not_load_dotenv(configured_run, fake_connection, monkeypatch):
    monkeypatch.setattr(
        probe, "load_dotenv", lambda **kwargs: pytest.fail("Connection loaded .env")
    )
    assert probe.main(arguments(configured_run)) == 0


def test_agent_missing_visual_configuration_is_preserved(configured_run, agent_script):
    agent_script.tool_result = CallToolResult(
        content=[
            TextContent(type="text", text="Visual model configuration is missing.")
        ],
        isError=True,
        structuredContent={"visual_status": "configuration_missing"},
    )
    final = completion(
        text="The requested inspection failed; geometry details remain uncertain."
    )
    final.usage = None
    agent_script.responses = [
        completion(
            (
                "sdk-visual",
                "get_asset",
                {"asset_id": "page:1", "question": "Read dimensions."},
            )
        ),
        final,
    ]
    assert probe.main(agent_arguments(configured_run)) == 0
    saved = read_agent_trace(configured_run[0])
    assert saved["state"] == "succeeded"
    assert saved["calls"][-1]["state"] == "mcp_error"
    assert (
        saved["calls"][-1]["response"]["structuredContent"]["visual_status"]
        == "configuration_missing"
    )
    assert saved["usage"]["responses_with_usage"] == 1
    assert len(agent_script.calls) == 2  # No automatic inspection retry.
    assert "VISUAL_INSPECTION_MODEL" not in agent_script.environment
    assert "visual_requests" not in saved["counts"]


@pytest.mark.parametrize("name", ["SKYNET_BASE_URL", "SKYNET_API_KEY"])
def test_agent_missing_endpoint_settings_before_trace(
    configured_run, agent_script, monkeypatch, name
):
    monkeypatch.delenv(name)
    assert probe.main(agent_arguments(configured_run)) == 1
    assert not (configured_run[0] / "mcp").exists()
    assert not agent_script.requests and not agent_script.calls


@pytest.mark.parametrize(
    "option,value",
    [
        ("--agent-model", " "),
        ("--max-turns", "0"),
        ("--max-turns", "-1"),
        ("--max-turns", "1.5"),
    ],
)
def test_agent_invalid_cli_options(configured_run, option, value):
    with pytest.raises(SystemExit) as error:
        probe.main(arguments(configured_run) + [option, value])
    assert error.value.code == 2
    assert not (configured_run[0] / "mcp").exists()


def test_agent_separate_invocations_preserve_traces(configured_run, agent_script):
    run_dir, _, _ = configured_run
    assert probe.main(arguments(configured_run)) == 0
    connection = next((run_dir / "mcp").glob("probe_connection_*.json"))
    connection_bytes = connection.read_bytes()
    agent_script.calls.clear()
    agent_script.responses = [completion(text="Insufficient evidence.")]
    assert probe.main(agent_arguments(configured_run)) == 0
    first = next((run_dir / "mcp").glob("probe_agent_*.json"))
    first_bytes = first.read_bytes()
    # The transport fixture's round counter starts again for preflight.
    agent_script.calls.clear()
    agent_script.responses = [completion(text="Insufficient evidence.")]
    assert probe.main(agent_arguments(configured_run)) == 0
    assert len(list((run_dir / "mcp").glob("probe_agent_*.json"))) == 2
    assert first.read_bytes() == first_bytes
    assert connection.read_bytes() == connection_bytes


@pytest.fixture
def visual_case(configured_run):
    """The external server's text-block contract and referenced diagnostic only."""
    run_dir = configured_run[0]
    digest = sha256_file(run_dir / "input" / "paper with spaces.pdf")

    def build(status="success", inspection_id="a" * 32, *, received=None):
        if received is None:
            received = status in {
                "success",
                "truncated",
                "refused",
                "empty",
                "invalid_response",
            }
        visual = {
            "status": status,
            "source_page_ids": ["page:1", "page:2"],
            "rendered_pages": [1],
            "visual_coverage": "partial",
            "limitations": [
                "Only the first-page region is available for this multipage asset."
            ],
            "render": {"available": True, "clipped": False},
        }
        if inspection_id is not None:
            visual["inspection_id"] = inspection_id
        if status == "success":
            visual["answer"] = "L=12 mm is visible on the patch."
        else:
            visual["reason"] = "Synthetic public limitation."
        payload = {
            "id": "segment:2/figure:1",
            "document_id": digest,
            "kind": "figure",
            "first_page": 1,
            "last_page": 2,
            "content": "Deterministic paper evidence.",
            "visual": visual,
        }
        record = {
            "inspection_id": inspection_id,
            "question": "Read dimensions.",
            "prompt": {
                "system": "PRIVATE-DIAGNOSTIC-PROMPT",
                "question": "Read dimensions.",
                "context": {k: v for k, v in payload.items() if k != "visual"},
            },
            "image_reference": "images/synthetic.png",
            "settings": None
            if status == "configuration_error"
            else {"model": "synthetic-visual", "max_retries": 0},
            "response": completion(text="PRIVATE-VISUAL-RESPONSE").model_dump(
                mode="json"
            )
            if received
            else None,
            "outcome": {"status": status},
            "duration_seconds": 0.25,
            "error_type": None,
            "http_status": None,
        }
        if received:
            record["usage"] = {
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "total_tokens": 10,
            }
        return payload, record

    return build


def asset_result(payload):
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))])


def diagnostic_path(configured_run, record):
    return configured_run[0] / "mcp" / "inspections" / f"{record['inspection_id']}.json"


def run_visual_agent(
    configured_run, agent_script, result, *, question="Read dimensions."
):
    arguments = {"asset_id": "segment:2/figure:1"}
    if question is not None:
        arguments["question"] = question
    agent_script.tool_result = result
    agent_script.responses = [
        completion(("sdk-visual", "get_asset", arguments)),
        completion(text="Evidence and remaining limitations."),
    ]
    assert probe.main(agent_arguments(configured_run)) == 0
    return read_agent_trace(configured_run[0])


@pytest.mark.parametrize("question", [None, "", "  "])
def test_visual_question_free_has_no_diagnostic_lookup(
    configured_run, agent_script, visual_case, monkeypatch, question
):
    payload, _ = visual_case("not_requested", None)
    payload["visual"].update(rendered_pages=[], visual_coverage="none")
    monkeypatch.setattr(
        probe.ProbeTrace,
        "inspection_diagnostic",
        lambda *args: pytest.fail("Unexpected lookup"),
    )
    saved = run_visual_agent(
        configured_run, agent_script, asset_result(payload), question=question
    )
    summary = saved["calls"][-1]["visual"]
    assert summary["asset_id"] == payload["id"]
    assert summary["inspection_requested"] is False
    assert summary["diagnostic"] == {"lookup": "not_applicable", "reference": None}
    assert summary["model_calls"] == 0
    assert saved["visual_accounting"]["inspections_requested"] == 0
    assert saved["visual_accounting"]["confirmed_model_calls"] == 0
    assert saved["visual_accounting"]["unknown_model_calls"] == 0


@pytest.mark.parametrize(
    "status,has_id,expected,success",
    [
        ("success", True, 1, 1),
        ("unavailable", False, 0, 0),
        ("configuration_error", True, 0, 0),
        ("render_error", False, 0, 0),
        ("image_persistence_error", False, 0, 0),
        ("truncated", True, 1, 0),
        ("refused", True, 1, 0),
        ("empty", True, 1, 0),
        ("invalid_response", True, 1, 0),
        ("timeout", True, None, 0),
        ("model_error", True, None, 0),
        ("persistence_error", False, None, 0),
    ],
)
def test_visual_execution_counts_and_provenance(
    configured_run, agent_script, visual_case, status, has_id, expected, success
):
    payload, record = visual_case(status, "a" * 32 if has_id else None)
    if expected == 0 and status != "configuration_error":
        payload["visual"].update(rendered_pages=[], visual_coverage="none")
    if has_id:
        path = diagnostic_path(configured_run, record)
        write_json(path, record)
        before = path.read_bytes()
    result = asset_result(payload)
    saved = run_visual_agent(configured_run, agent_script, result)
    call = saved["calls"][-1]
    summary = call["visual"]
    assert call["sdk_tool_call_id"] == "sdk-visual"
    assert call["response"] == result.model_dump(mode="json", by_alias=True)
    assert call["state"] == "returned"
    assert summary["provenance"] == "available"
    assert summary["inspection_requested"] is True
    assert summary["status"] == status
    for field in (
        "source_page_ids",
        "rendered_pages",
        "visual_coverage",
        "limitations",
    ):
        assert summary[field] == payload["visual"][field]
    assert summary["model_calls"] == expected
    assert summary["successful_observations"] == success
    diagnostic = summary["diagnostic"]
    if has_id:
        assert diagnostic["lookup"] == "available"
        assert diagnostic["reference"] == "mcp/inspections/" + "a" * 32 + ".json"
        assert diagnostic["outcome"] == status
        assert diagnostic["duration_seconds"] == 0.25
        assert (
            diagnostic["model"] == record["settings"]["model"]
            if record["settings"]
            else diagnostic["model"] is None
        )
        assert path.read_bytes() == before
    else:
        assert diagnostic == {"lookup": "not_applicable", "reference": None}
    accounting = saved["visual_accounting"]
    assert accounting["inspections_requested"] == 1
    assert accounting["confirmed_model_calls"] == int(expected == 1)
    assert accounting["unknown_model_calls"] == int(expected is None)
    assert accounting["successful_observations"] == success
    assert accounting["usage"] == (
        {"inspections_with_usage": 1, **record["usage"]} if expected == 1 else None
    )
    assert saved["counts"] == {
        "model_requests": 2,
        "model_responses": 2,
        "mcp_calls": 2,
    }
    assert saved["usage"] == {
        "responses_with_usage": 2,
        "prompt_tokens": 20,
        "completion_tokens": 10,
        "total_tokens": 30,
    }
    serialized = json.dumps(saved)
    assert "PRIVATE-DIAGNOSTIC-PROMPT" not in serialized
    assert "PRIVATE-VISUAL-RESPONSE" not in serialized


@pytest.mark.parametrize("received", [False, True])
def test_visual_model_error_needs_received_completion_not_settings(
    configured_run, agent_script, visual_case, received
):
    payload, record = visual_case("model_error", received=received)
    write_json(diagnostic_path(configured_run, record), record)
    saved = run_visual_agent(configured_run, agent_script, asset_result(payload))
    assert saved["calls"][-1]["visual"]["model_calls"] == (1 if received else None)
    assert saved["visual_accounting"]["unknown_model_calls"] == int(not received)
    assert saved["visual_accounting"]["successful_observations"] == 0


@pytest.mark.parametrize(
    "fault,lookup",
    [
        ("missing", "missing"),
        ("malformed", "invalid"),
        ("shape", "invalid"),
        ("unreadable", "unreadable"),
        ("encoding", "unreadable"),
        ("inspection", "mismatched"),
        ("document", "mismatched"),
        ("asset", "mismatched"),
        ("question", "mismatched"),
        ("outcome", "mismatched"),
    ],
)
def test_visual_broken_diagnostic_is_explicit(
    configured_run, agent_script, visual_case, monkeypatch, fault, lookup
):
    payload, record = visual_case("timeout")
    path = diagnostic_path(configured_run, record)
    if fault == "inspection":
        record["inspection_id"] = "b" * 32
    elif fault == "document":
        record["prompt"]["context"]["document_id"] = "f" * 64
    elif fault == "asset":
        record["prompt"]["context"]["id"] = "page:1"
    elif fault == "question":
        record["question"] = "Another question."
    elif fault == "outcome":
        record["outcome"]["status"] = "success"
    elif fault == "shape":
        record = {"inspection_id": "a" * 32}
    if fault != "missing":
        write_json(path, record)
    if fault == "malformed":
        path.write_text("{broken", encoding="utf-8")
    if fault == "encoding":
        path.write_bytes(b"\xff")
    read = Path.read_text
    looked_up = []

    def guarded_read(file, *args, **kwargs):
        if file.parent.name == "inspections":
            looked_up.append(file)
            assert file == path
            if fault == "unreadable":
                raise PermissionError("synthetic-agent-secret")
        return read(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    saved = run_visual_agent(configured_run, agent_script, asset_result(payload))
    summary = saved["calls"][-1]["visual"]
    assert looked_up == [path]
    assert summary["diagnostic"]["lookup"] == lookup
    assert summary["diagnostic"]["reference"] == "mcp/inspections/" + "a" * 32 + ".json"
    assert summary["diagnostic"]["limitation"]
    assert "model" not in summary["diagnostic"]
    assert saved["visual_accounting"]["unknown_model_calls"] == 1
    assert "synthetic-agent-secret" not in json.dumps(saved)


@pytest.mark.parametrize(
    "inspection_id",
    [
        "../outside",
        "..\\outside",
        "A" * 32,
        "a" * 31,
        "C:\\outside",
        "/outside",
        "a" * 32 + ".json",
    ],
)
def test_visual_invalid_inspection_id_never_reads(
    configured_run, agent_script, visual_case, monkeypatch, inspection_id
):
    payload, _ = visual_case("timeout", inspection_id)
    read = Path.read_text

    def guarded_read(file, *args, **kwargs):
        assert file.parent.name != "inspections"
        return read(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    saved = run_visual_agent(configured_run, agent_script, asset_result(payload))
    assert saved["calls"][-1]["visual"]["diagnostic"]["lookup"] == "invalid"
    assert saved["calls"][-1]["visual"]["diagnostic"]["reference"] is None


@pytest.mark.parametrize("target", ["file", "directory"])
def test_visual_diagnostic_symlink_escape(
    configured_run, agent_script, visual_case, tmp_path, monkeypatch, target
):
    payload, record = visual_case("timeout")
    path = diagnostic_path(configured_run, record)
    outside = tmp_path / "outside"
    write_json(outside / path.name, record)
    path.parent.parent.mkdir(exist_ok=True)
    try:
        if target == "directory":
            path.parent.symlink_to(outside, target_is_directory=True)
        else:
            path.parent.mkdir()
            path.symlink_to(outside / path.name)
    except OSError:
        pytest.skip("Windows does not grant symlink creation")
    read = Path.read_text

    def guarded_read(file, *args, **kwargs):
        assert file != path
        return read(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    saved = run_visual_agent(configured_run, agent_script, asset_result(payload))
    assert saved["calls"][-1]["visual"]["diagnostic"]["lookup"] == "invalid"


@pytest.mark.parametrize(
    "fault,provenance",
    [
        ("json", "malformed_response"),
        ("blocks", "malformed_response"),
        ("missing", "missing_visual"),
        ("fields", "invalid_fields"),
        ("document", "mismatched_identity"),
        ("asset", "mismatched_identity"),
    ],
)
def test_visual_response_decoding_preserves_raw(
    configured_run, agent_script, visual_case, fault, provenance
):
    payload, _ = visual_case()
    if fault == "missing":
        del payload["visual"]
    elif fault == "fields":
        payload["visual"]["rendered_pages"] = ["1"]
    elif fault == "document":
        payload["document_id"] = "f" * 64
    elif fault == "asset":
        payload["id"] = "page:1"
    result = asset_result(payload)
    if fault == "json":
        result.content[0].text = "{broken"
    elif fault == "blocks":
        result.content.append(TextContent(type="text", text="Extra block."))
    saved = run_visual_agent(configured_run, agent_script, result)
    assert saved["calls"][-1]["response"] == result.model_dump(
        mode="json", by_alias=True
    )
    assert saved["calls"][-1]["visual"]["provenance"] == provenance
    assert saved["visual_accounting"]["unknown_model_calls"] == 1


@pytest.mark.parametrize("reuse", ["distinct", "duplicate", "inconsistent"])
def test_visual_reused_image_and_inspection_ids(
    configured_run, agent_script, visual_case, reuse
):
    first, record = visual_case()
    write_json(diagnostic_path(configured_run, record), record)
    second, record = visual_case(
        inspection_id="b" * 32 if reuse == "distinct" else "a" * 32
    )
    if reuse == "distinct":
        write_json(diagnostic_path(configured_run, record), record)
    if reuse == "inconsistent":
        second["visual"]["visual_coverage"] = "single_page"
    arguments = {"asset_id": first["id"], "question": "Read dimensions."}
    agent_script.tool_results = [asset_result(first), asset_result(second)]
    agent_script.responses = [
        completion(
            ("sdk-first", "get_asset", arguments),
            ("sdk-second", "get_asset", arguments),
        ),
        completion(text="Evidence with source references."),
    ]
    assert probe.main(agent_arguments(configured_run)) == 0
    saved = read_agent_trace(configured_run[0])
    counts = saved["visual_accounting"]
    assert counts["inspections_requested"] == 2
    assert (
        counts["confirmed_model_calls"]
        == {"distinct": 2, "duplicate": 1, "inconsistent": 0}[reuse]
    )
    assert counts["unknown_model_calls"] == int(reuse == "inconsistent")
    assert counts["successful_observations"] == counts["confirmed_model_calls"]
    assert counts["reused_inspection_ids"] == int(reuse != "distinct")
    assert counts["inconsistent_inspection_ids"] == int(reuse == "inconsistent")
    if reuse != "distinct":
        for call in saved["calls"][1:]:
            assert call["inspection_reuse"] == {
                "outcome": reuse,
                "first_call_id": saved["calls"][1]["call_id"],
            }
    if reuse == "distinct":
        assert counts["usage"]["total_tokens"] == 20
    elif reuse == "duplicate":
        assert counts["usage"]["total_tokens"] == 10
    else:
        assert counts["usage"] is None


def test_visual_raw_then_enriched_durable_before_sdk(
    configured_run, agent_script, visual_case, monkeypatch
):
    payload, record = visual_case()
    write_json(diagnostic_path(configured_run, record), record)
    result = asset_result(payload)
    summarize = probe.ProbeTrace.visual_summary
    interpreted = []

    def checked_summary(trace, response, arguments):
        saved = read_agent_trace(configured_run[0])
        assert saved["calls"][-1]["response"] == result.model_dump(
            mode="json", by_alias=True
        )
        assert "visual" not in saved["calls"][-1]
        interpreted.append(True)
        return summarize(trace, response, arguments)

    def before_model(saved):
        if len(saved["model_requests"]) == 2:
            assert saved["calls"][-1]["visual"]["diagnostic"]["lookup"] == "available"
            assert saved["visual_accounting"]["confirmed_model_calls"] == 1

    monkeypatch.setattr(probe.ProbeTrace, "visual_summary", checked_summary)
    agent_script.before_model = before_model
    saved = run_visual_agent(configured_run, agent_script, result)
    assert interpreted == [True]
    assert len(saved["model_requests"]) == 2
    assert len(saved["calls"]) == 2


@pytest.mark.parametrize("failed_write", [7, 8])
def test_visual_required_write_failure_stops_sdk(
    configured_run, agent_script, visual_case, monkeypatch, failed_write
):
    payload, record = visual_case()
    write_json(diagnostic_path(configured_run, record), record)
    agent_script.tool_result = asset_result(payload)
    agent_script.responses = [
        completion(
            (
                "sdk-visual",
                "get_asset",
                {"asset_id": payload["id"], "question": "Read dimensions."},
            )
        ),
        completion(text="Must never be requested."),
    ]
    replace = persistence.os.replace
    writes = []

    def failing_replace(source, destination):
        writes.append(destination)
        if len(writes) == failed_write:
            raise OSError("synthetic-agent-secret")
        replace(source, destination)

    monkeypatch.setattr(persistence.os, "replace", failing_replace)
    assert probe.main(agent_arguments(configured_run)) == 1
    saved = read_agent_trace(configured_run[0])
    assert len(agent_script.requests) == 1
    assert len(agent_script.calls) == 2
    assert len(writes) == failed_write
    assert "visual" not in saved["calls"][-1]
    assert ("response" in saved["calls"][-1]) == (failed_write == 8)
    assert agent_script.closed and agent_script.model_closed


def test_visual_summary_excludes_private_payload_and_keeps_partial_usage(
    configured_run, agent_script, visual_case
):
    payload, record = visual_case()
    payload["visual"]["reason"] = (
        "synthetic-agent-secret data:image/png;base64,PRIVATE-IMAGE"
    )
    record["prompt"]["context"]["image"] = "PRIVATE-IMAGE-BYTES"
    record["response"]["image"] = "PRIVATE-IMAGE-BYTES"
    record["settings"]["api_key"] = "synthetic-agent-secret"
    record["usage"] = {
        "prompt_tokens": 7,
        "completion_tokens": None,
        "extra": "PRIVATE-USAGE",
    }
    path = diagnostic_path(configured_run, record)
    write_json(path, record)
    before = path.read_bytes()
    saved = run_visual_agent(configured_run, agent_script, asset_result(payload))
    serialized = json.dumps(saved)
    for private in (
        "synthetic-agent-secret",
        "PRIVATE-IMAGE",
        "PRIVATE-USAGE",
        "PRIVATE-DIAGNOSTIC-PROMPT",
        "PRIVATE-VISUAL-RESPONSE",
    ):
        assert private not in serialized
    assert saved["visual_accounting"]["usage"] == {
        "inspections_with_usage": 1,
        "prompt_tokens": 7,
    }
    assert saved["calls"][-1]["visual"]["diagnostic"]["usage"] == {"prompt_tokens": 7}
    assert path.read_bytes() == before
