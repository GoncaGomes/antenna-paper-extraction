"""Explicit connection or narrow evidence-agent probe for one preserved run."""

import argparse
import asyncio
import copy
import json
import logging
import os
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO
from uuid import uuid4

from agents.exceptions import MaxTurnsExceeded, ModelBehaviorError
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv
from mcp import stdio_client
from mcp.client.stdio import get_default_environment
from mcp.types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antenna_paper_extraction.mcp_agent import (
    ProbeError,
    ProbePersistenceError,
    ProbeTrace,
    run_evidence_agent,
    timestamp,
)
from antenna_paper_extraction.runs import (
    RunManifest,
    load_run_status,
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
    pdf: Path, run_dir: Path, *, agent_mode: bool = False
) -> dict[str, str]:
    # Inherit only launch-related variables; model credentials/settings stay out.
    env = get_default_environment()
    for key in ("COMSPEC", "WINDIR", "TMP"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(
        PDF_INGESTION_PDF=str(pdf.resolve()),
        PDF_INGESTION_RUN_DIR=str((run_dir / "mcp").resolve()),
        PYTHONDONTWRITEBYTECODE="1",
    )
    if agent_mode:
        for key in (
            "SKYNET_BASE_URL",
            "SKYNET_API_KEY",
            "VISUAL_INSPECTION_MODEL",
            "VISUAL_INSPECTION_TIMEOUT_SECONDS",
        ):
            if key in os.environ:
                env[key] = os.environ[key]
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
    max_turns: int = 8,
) -> None:
    run_dir = run_dir.resolve()
    manifest, pdf, digest = verify_run(run_dir)
    mcp_executable, mcp_cwd = mcp_executable.resolve(), mcp_cwd.resolve()
    if not mcp_executable.is_file():
        raise ProbeError("MCP executable must be an existing file.")
    if not mcp_cwd.is_dir():
        raise ProbeError("MCP working directory must already exist.")

    configuration = None
    if agent_model is not None:
        agent_model = nonblank_model(agent_model)
        if (
            isinstance(max_turns, bool)
            or not isinstance(max_turns, int)
            or max_turns <= 0
        ):
            raise ProbeError("max_turns must be a positive integer.")
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        for name in ("SKYNET_BASE_URL", "SKYNET_API_KEY"):
            if not os.environ.get(name, "").strip():
                raise ProbeError(f"Missing required environment variable: {name}")
        configuration = {
            "model": agent_model,
            "max_turns": max_turns,
            "model_timeout_seconds": 600,
            "session_timeout_seconds": 600,
            "model_max_retries": 0,
            "mcp_max_retry_attempts": 0,
            "parallel_tool_calls": False,
            "max_function_tool_concurrency": 1,
            "sdk_tracing_disabled": True,
            "visual_model": os.environ.get("VISUAL_INSPECTION_MODEL"),
            "visual_timeout_seconds": os.environ.get(
                "VISUAL_INSPECTION_TIMEOUT_SECONDS"
            ),
        }
    trace = (
        ProbeTrace(run_dir, manifest)
        if configuration is None
        else ProbeTrace(run_dir, manifest, configuration=configuration)
    )
    print(f"Trace: {json.dumps(str(trace.path))}")
    operation = "startup"
    try:
        # The null device provides an OS handle for child stderr without file I/O.
        with open(os.devnull, "w", encoding="utf-8") as errlog:  # noqa: ASYNC230
            async with QuietStdioServer(
                params={
                    "command": str(mcp_executable),
                    "args": [],
                    "cwd": str(mcp_cwd),
                    "env": child_environment(
                        pdf, run_dir, agent_mode=agent_model is not None
                    ),
                },
                name="run-pdf-connection-probe",
                errlog=errlog,
                trace=trace,
                client_session_timeout_seconds=SESSION_TIMEOUT_SECONDS,
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
                        base_url=os.environ["SKYNET_BASE_URL"].strip(),
                        api_key=os.environ["SKYNET_API_KEY"].strip(),
                        max_turns=max_turns,
                    )
                operation = "cleanup"
    except asyncio.CancelledError:
        try:
            trace.finish("cancelled", "Probe cancelled.", reason="cancellation")
        except ProbePersistenceError:
            pass
        raise
    except Exception as error:  # noqa: BLE001 -- never display external error bodies
        reason = (
            "persistence_failure"
            if trace.persistence_failed
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
            str(error)
            if isinstance(error, ProbeError)
            else "Agent turn budget exhausted."
            if reason == "max_turns"
            else "Principal model failed or returned unusable/truncated output."
            if reason == "model_failure"
            else f"MCP {operation} failed; check the executable and server configuration."
        )
        if trace.persistence_failed and agent_model is not None:
            diagnostic = "MCP trace persistence failed; probe stopped."
        try:
            trace.finish("failed", diagnostic, reason=reason)
        except ProbePersistenceError:
            pass
        raise ProbeError(diagnostic) from None

    # Report success only after the connection and child process have closed.
    trace.finish("succeeded", reason="final_answer" if agent_model else None)
    print(f"Run: {json.dumps(manifest.run_id)}")
    print(f"Document: {manifest.document_id}")
    print(f"Tools: {', '.join(sorted(names))}")
    if agent_model is None:
        print("Connection verified; model calls: 0.")
    else:
        print(f"Agent completed; counts: {json.dumps(trace.data['counts'])}.")


def nonblank_model(value: str) -> str:
    if not value.strip():
        raise ProbeError("agent_model must be a nonblank model identifier.")
    return value.strip()


def positive_turns(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "max-turns must be a positive integer."
        ) from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError("max-turns must be a positive integer.")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--mcp-executable", type=Path, required=True)
    parser.add_argument("--mcp-cwd", type=Path, required=True)
    parser.add_argument("--agent-model", type=nonblank_model)
    parser.add_argument("--max-turns", type=positive_turns, default=8)
    args = parser.parse_args(argv)
    # SDK logs can include tool/error bodies. This standalone probe emits only
    # controlled diagnostics and restores logging for callers of main().
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(
            probe(
                args.run_dir,
                args.mcp_executable,
                args.mcp_cwd,
                agent_model=args.agent_model,
                max_turns=args.max_turns,
            )
        )
    except ProbeError as error:
        print(f"Connection verification failed: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Connection verification cancelled.", file=sys.stderr)
        return 130
    except Exception:  # noqa: BLE001 -- CLI boundary excludes sensitive raw errors
        print(
            "Connection verification failed during file access; check run paths.",
            file=sys.stderr,
        )
        return 1
    finally:
        logging.disable(previous_logging_disable)
    return 0


if __name__ == "__main__":
    sys.exit(main())
