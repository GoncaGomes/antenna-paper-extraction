"""Shared MCP connection and evidence-agent execution for one preserved run."""

import asyncio
import copy
import json
import os
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO
from uuid import uuid4

from agents.exceptions import MaxTurnsExceeded, ModelBehaviorError
from agents.mcp import MCPServerStdio
from mcp import stdio_client
from mcp.client.stdio import get_default_environment
from mcp.types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antenna_paper_extraction.architecture_report import (
    MCP_ARCHITECTURE_INSTRUCTIONS,
    MCP_ARCHITECTURE_TASK,
)
from antenna_paper_extraction.mcp_agent import (
    EVIDENCE_INSTRUCTIONS,
    EVIDENCE_TASK,
    ProbeError,
    ProbePersistenceError,
    ProbeTrace,
    run_evidence_agent,
    timestamp,
)
from antenna_paper_extraction.mcp_architecture import (
    finalize_architecture_report,
    reserve_architecture_output,
)
from antenna_paper_extraction.runs import (
    PhaseFailure,
    RunManifest,
    load_run_status,
    mark_architecture_mcp_extraction_failed,
    mark_architecture_mcp_extraction_running,
    mark_architecture_mcp_extraction_succeeded,
    sha256_file,
)

EXPECTED_TOOLS = frozenset(
    {
        "get_paper_overview",
        "read_pages",
        "read_section",
        "search_paper",
        "list_assets",
        "get_asset",
    }
)
SESSION_TIMEOUT_SECONDS = 600


class OverviewIdentity(BaseModel):
    # The remaining overview fields contain evidence, outside this probe's scope.
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    paper: str = Field(min_length=1)
    document_id: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    pdf_pages: int = Field(ge=1)


class QuietStdioServer(MCPServerStdio):
    """Use the public transport hook to keep child stderr out of diagnostics."""

    def __init__(self, *, errlog: TextIO, trace: ProbeTrace, **kwargs):
        super().__init__(**kwargs)
        self.errlog = errlog
        self.trace = trace

    def create_streams(self):
        return stdio_client(self.params, errlog=self.errlog)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        meta: dict[str, Any] | None = None,
    ) -> CallToolResult:
        data = copy.deepcopy(self.trace.data)
        call = {
            "call_id": f"local-{uuid4().hex}",
            "call_id_source": "locally_generated",
            "trace_id": data["trace_id"],
            "tool_name": self.trace.sanitize(tool_name),
            "arguments": self.trace.sanitize(arguments),
            "started_at": timestamp(),
            "state": "started",
        }
        if "model_requests" in data:
            call.update(
                sdk_tool_call_id=self.trace.active_tool_call_id,
                model_request_id=(
                    data["model_requests"][-1]["request_id"]
                    if data["model_requests"]
                    else None
                ),
            )
        data["calls"].append(call)
        self.trace.event(data, "mcp_call", call["call_id"])
        self.trace.save(data)
        started = perf_counter()
        data = copy.deepcopy(self.trace.data)
        call = data["calls"][-1]
        try:
            result = await super().call_tool(tool_name, arguments, meta=meta)
        except (Exception, asyncio.CancelledError) as error:
            call.update(
                state="cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "transport_error",
                exception_type=type(error).__name__,
                finished_at=timestamp(),
                elapsed_seconds=perf_counter() - started,
            )
            try:
                self.trace.save(data)
            except ProbePersistenceError:
                # Keep the original failure/cancellation if diagnostic saving fails.
                pass
            raise
        response = result.model_dump(mode="json", by_alias=True)
        call.update(
            state="mcp_error" if response["isError"] else "returned",
            response=self.trace.sanitize(response),
            finished_at=timestamp(),
            elapsed_seconds=perf_counter() - started,
        )
        self.trace.event(data, "mcp_response", call["call_id"])
        self.trace.save(data)
        if tool_name == "get_asset":
            self.trace.enrich_asset_response(response, arguments)
        return result


def verify_run(run_dir: Path) -> tuple[RunManifest, Path, str]:
    if not run_dir.is_dir():
        raise ProbeError("Run directory must already exist.")
    for name in ("manifest.json", "status.json"):
        if not (run_dir / name).resolve().is_relative_to(run_dir):
            raise ProbeError("Run metadata path escapes the run directory.")
    try:
        manifest = RunManifest.model_validate_json(
            (run_dir / "manifest.json").read_text(encoding="utf-8")
        )
        status = load_run_status(run_dir)
    except (OSError, ValueError):
        raise ProbeError(
            "Run manifest/status is missing, unreadable or invalid."
        ) from None
    if (
        status.run_id != manifest.run_id
        or status.phases.source_preservation.state != "succeeded"
    ):
        raise ProbeError("Run must have matching identity and successful preservation.")

    relative_path = Path(manifest.source_pdf.relative_path)
    pdf = (run_dir / relative_path).resolve()
    if relative_path.is_absolute() or not pdf.is_relative_to(run_dir / "input"):
        raise ProbeError("Preserved PDF must be inside the run input directory.")
    if not pdf.is_file():
        raise ProbeError("Preserved PDF is missing or is not a regular file.")
    digest = sha256_file(pdf)
    if digest != manifest.source_pdf.sha256:
        raise ProbeError("Preserved PDF SHA-256 does not match the run manifest.")
    if manifest.document_id != f"sha256:{digest}":
        raise ProbeError("Run document identity does not match the preserved PDF.")

    storage = run_dir / "mcp"
    if not storage.resolve().is_relative_to(run_dir) or (
        storage.exists() and not storage.is_dir()
    ):
        raise ProbeError("MCP storage must be a directory contained in the run.")
    return manifest, pdf, digest


def child_environment(
    pdf: Path,
    run_dir: Path,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    visual_model: str | None = None,
    visual_timeout_seconds: float | str | None = None,
) -> dict[str, str]:
    # Inherit only launch variables; endpoint/visual settings are passed explicitly.
    env = get_default_environment()
    for key in ("COMSPEC", "WINDIR", "TMP"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(
        PDF_INGESTION_PDF=str(pdf.resolve()),
        PDF_INGESTION_RUN_DIR=str((run_dir / "mcp").resolve()),
        PYTHONDONTWRITEBYTECODE="1",
    )
    for key, value in (
        ("SKYNET_BASE_URL", base_url),
        ("SKYNET_API_KEY", api_key),
        ("VISUAL_INSPECTION_MODEL", visual_model),
        ("VISUAL_INSPECTION_TIMEOUT_SECONDS", visual_timeout_seconds),
    ):
        if value is not None:
            env[key] = str(value)
    return env


def decode_overview(result: CallToolResult) -> OverviewIdentity:
    if result.model_dump(by_alias=True)["isError"]:
        raise ProbeError("get_paper_overview returned an MCP error result.")
    # FastMCP serializes the overview dictionary as one JSON TextContent block.
    if len(result.content) != 1 or result.content[0].type != "text":
        raise ProbeError("Overview must contain exactly one JSON text block.")
    try:
        payload = json.loads(result.content[0].text)
    except ValueError:
        raise ProbeError("Overview contains malformed JSON.") from None
    try:
        return OverviewIdentity.model_validate(payload)
    except ValidationError:
        raise ProbeError("Overview identity fields are missing or invalid.") from None


async def probe(
    run_dir: Path,
    mcp_executable: Path,
    mcp_cwd: Path,
    *,
    agent_model: str | None = None,
    agent_task: str = "geometry",
    max_turns: int = 8,
    persist_architecture: bool = False,
    base_url: str | None = None,
    api_key: str | None = None,
    principal_timeout_seconds: float = 600,
    visual_model: str | None = None,
    visual_timeout_seconds: float | str | None = None,
    session_timeout_seconds: float = SESSION_TIMEOUT_SECONDS,
) -> Path | None:
    if agent_task not in {"geometry", "architecture"}:
        raise ProbeError("agent_task must be geometry or architecture.")
    if agent_task == "architecture" and agent_model is None:
        raise ProbeError("Architecture selection requires --agent-model.")
    if persist_architecture and (agent_task != "architecture" or agent_model is None):
        raise ProbeError(
            "--persist-architecture requires --agent-task architecture and --agent-model."
        )
    instructions, task = (
        (MCP_ARCHITECTURE_INSTRUCTIONS, MCP_ARCHITECTURE_TASK)
        if agent_task == "architecture"
        else (EVIDENCE_INSTRUCTIONS, EVIDENCE_TASK)
    )
    run_dir = run_dir.resolve()
    manifest, pdf, digest = verify_run(run_dir)
    mcp_executable, mcp_cwd = mcp_executable.resolve(), mcp_cwd.resolve()
    if not mcp_executable.is_file():
        raise ProbeError("MCP executable must be an existing file.")
    if not mcp_cwd.is_dir():
        raise ProbeError("MCP working directory must already exist.")

    configuration = None
    if agent_model is not None:
        if not agent_model.strip():
            raise ProbeError("agent_model must be a nonblank model identifier.")
        agent_model = agent_model.strip()
        if (
            isinstance(max_turns, bool)
            or not isinstance(max_turns, int)
            or max_turns <= 0
        ):
            raise ProbeError("max_turns must be a positive integer.")
        for name, value in (("SKYNET_BASE_URL", base_url), ("SKYNET_API_KEY", api_key)):
            if value is None or not value.strip():
                raise ProbeError(f"Missing required environment variable: {name}")
        base_url, api_key = base_url.strip(), api_key.strip()
        configuration = {
            "agent_task": agent_task,
            "model": agent_model,
            "max_turns": max_turns,
            "model_timeout_seconds": principal_timeout_seconds,
            "session_timeout_seconds": session_timeout_seconds,
            "model_max_retries": 0,
            "mcp_max_retry_attempts": 0,
            "parallel_tool_calls": False,
            "max_function_tool_concurrency": 1,
            "sdk_tracing_disabled": True,
            "visual_model": visual_model,
            "visual_timeout_seconds": visual_timeout_seconds,
        }
    if (
        persist_architecture
        and load_run_status(run_dir).phases.architecture_mcp_extraction.state
        != "pending"
    ):
        raise ProbeError("MCP architecture extraction can only start from pending.")
    trace = (
        ProbeTrace(run_dir, manifest)
        if configuration is None
        else ProbeTrace(
            run_dir,
            manifest,
            configuration=configuration,
            instructions=instructions,
            task=task,
            output_path=(
                reserve_architecture_output(run_dir) if persist_architecture else None
            ),
        )
    )
    print(f"Trace: {json.dumps(str(trace.path))}")
    operation = "startup"
    phase_started = False
    published_report: Path | None = None
    try:
        if persist_architecture:
            operation = "lifecycle start"
            mark_architecture_mcp_extraction_running(run_dir)
            phase_started = True
            operation = "startup"
        # The null device provides an OS handle for child stderr without file I/O.
        with open(os.devnull, "w", encoding="utf-8") as errlog:  # noqa: ASYNC230
            async with QuietStdioServer(
                params={
                    "command": str(mcp_executable),
                    "args": [],
                    "cwd": str(mcp_cwd),
                    "env": child_environment(
                        pdf,
                        run_dir,
                        base_url=base_url,
                        api_key=api_key,
                        visual_model=visual_model,
                        visual_timeout_seconds=visual_timeout_seconds,
                    ),
                },
                name="run-pdf-connection-probe",
                errlog=errlog,
                trace=trace,
                client_session_timeout_seconds=session_timeout_seconds,
                max_retry_attempts=0,
                failure_error_function=None,
            ) as server:
                operation = "tool discovery"
                tools = await server.list_tools()
                names = [tool.name for tool in tools]
                if len(names) != len(EXPECTED_TOOLS) or set(names) != EXPECTED_TOOLS:
                    raise ProbeError(
                        "MCP tool discovery must match exactly the six tools."
                    )
                operation = "get_paper_overview"
                overview = decode_overview(
                    await server.call_tool("get_paper_overview", {})
                )
                if overview.document_id.removeprefix("sha256:") != digest:
                    raise ProbeError(
                        "Server document identity does not match the verified PDF."
                    )
                if agent_model is not None:
                    operation = "agent execution"
                    await run_evidence_agent(
                        server,
                        trace,
                        model_name=agent_model,
                        base_url=base_url,
                        api_key=api_key,
                        principal_timeout_seconds=principal_timeout_seconds,
                        max_turns=max_turns,
                    )
                operation = "cleanup"
        if persist_architecture:
            operation = "report publication"
            finalize_architecture_report(trace)
            published_report = trace.path.parent / "architecture_evidence_report.md"
            operation = "lifecycle success"
            mark_architecture_mcp_extraction_succeeded(run_dir)
    except (Exception, asyncio.CancelledError) as error:
        cancelled = isinstance(error, asyncio.CancelledError)
        reason = (
            "cancellation"
            if cancelled
            else "persistence_failure"
            if operation in {"lifecycle start", "lifecycle success"}
            or trace.persistence_failed
            or isinstance(error, ProbePersistenceError)
            else "max_turns"
            if isinstance(error, MaxTurnsExceeded)
            else "model_failure"
            if isinstance(error, ModelBehaviorError)
            or (
                trace.data.get("model_requests")
                and trace.data["model_requests"][-1]["state"] == "model_error"
            )
            else "tool_failure"
            if operation != "cleanup"
            else "cleanup_failure"
        )
        diagnostic = (
            "Probe cancelled."
            if cancelled
            else "MCP architecture lifecycle persistence failed; execution stopped."
            if operation in {"lifecycle start", "lifecycle success"}
            else str(error)
            if isinstance(error, ProbeError)
            else "Agent turn budget exhausted."
            if reason == "max_turns"
            else "Principal model failed or returned unusable/truncated output."
            if reason == "model_failure"
            else f"MCP {operation} failed; check the executable and server configuration."
        )
        if (
            not cancelled
            and trace.persistence_failed
            and agent_model is not None
            and operation != "report publication"
        ):
            diagnostic = "MCP trace persistence failed; probe stopped."
        if published_report is not None:
            try:
                published_report.unlink()
            except OSError:
                diagnostic += " Published report removal failed."
        # Each file remains independently atomic; attempt both failure updates.
        if phase_started:
            try:
                mark_architecture_mcp_extraction_failed(
                    run_dir, PhaseFailure(type=reason, message=diagnostic)
                )
            except Exception:  # noqa: BLE001 -- exclude raw persistence errors
                diagnostic += " MCP architecture failure status could not be persisted."
        try:
            if published_report is not None:
                data = copy.deepcopy(trace.data)
                data.update(
                    report_path=None,
                    state="cancelled" if cancelled else "failed",
                    finished_at=timestamp(),
                    diagnostic=diagnostic,
                    termination_reason=reason,
                )
                trace.save(data)
            else:
                trace.finish(
                    "cancelled" if cancelled else "failed", diagnostic, reason=reason
                )
        except ProbePersistenceError:
            diagnostic += " Execution failure diagnostics could not be persisted."
        if cancelled:
            if diagnostic != "Probe cancelled.":
                print(diagnostic, file=sys.stderr)
            raise
        raise ProbeError(diagnostic) from None

    # Report success only after the connection and child process have closed.
    if not persist_architecture:
        trace.finish("succeeded", reason="final_answer" if agent_model else None)
    print(f"Run: {json.dumps(manifest.run_id)}")
    print(f"Document: {manifest.document_id}")
    print(f"Tools: {', '.join(sorted(names))}")
    if agent_model is None:
        print("Connection verified; model calls: 0.")
    else:
        print(f"Agent completed; counts: {json.dumps(trace.data['counts'])}.")

    return published_report
