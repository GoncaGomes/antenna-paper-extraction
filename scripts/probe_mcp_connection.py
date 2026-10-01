"""Explicit deterministic MCP connection check for one preserved extraction run."""

import argparse
import asyncio
import copy
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO
from uuid import uuid4

from agents.mcp import MCPServerStdio
from mcp import stdio_client
from mcp.client.stdio import get_default_environment
from mcp.types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antenna_paper_extraction.persistence import write_json
from antenna_paper_extraction.runs import (
    PORTUGAL_TIMEZONE,
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


class ProbeError(ValueError):
    """A controlled diagnostic safe to display without external error bodies."""


class ProbePersistenceError(ProbeError):
    """A required trace write failed; execution must stop."""


def timestamp() -> str:
    return datetime.now(PORTUGAL_TIMEZONE).isoformat()


class ProbeTrace:
    """Small local trace, committed only through the existing atomic writer."""

    def __init__(self, run_dir: Path, manifest: RunManifest):
        trace_id = uuid4().hex
        self.path = run_dir / "mcp" / f"probe_connection_{trace_id}.json"
        self.data: dict[str, Any] = {
            "trace_id": trace_id,
            "run_id": manifest.run_id,
            "document_id": manifest.document_id,
            "started_at": timestamp(),
            "finished_at": None,
            "state": "running",
            "calls": [],
        }
        self.persistence_failed = False
        credential_name = re.compile(
            r"(?:^|_)(?:API_KEY|KEY|TOKEN|PASSWORD|SECRET|CREDENTIALS?|AUTH)(?:_|$)",
            re.IGNORECASE,
        )
        self.credential_values = sorted(
            {
                value
                for key, value in os.environ.items()
                if value and credential_name.search(key)
            },
            key=len,
            reverse=True,
        )
        self.save(self.data)

    def sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            image = value.get("type") == "image" or str(
                value.get("mimeType", "")
            ).lower().startswith("image/")
            sanitized = {}
            for key, item in value.items():
                if image and key in ("data", "blob"):
                    sanitized[f"{key}_omitted"] = "image payload"
                else:
                    sanitized[self.sanitize(key)] = self.sanitize(item)
            return sanitized
        if isinstance(value, list):
            return [self.sanitize(item) for item in value]
        if isinstance(value, str):
            value = re.sub(
                r"data:image/[^\s\"'<>\\)]+",
                "[omitted image data URI]",
                value,
                flags=re.IGNORECASE,
            )
            for credential in self.credential_values:
                value = value.replace(credential, "[redacted credential]")
        return value

    def save(self, data: dict[str, Any]) -> None:
        if self.persistence_failed:
            raise ProbePersistenceError("MCP trace persistence failed; probe stopped.")
        try:
            write_json(self.path, data)
        except Exception:  # noqa: BLE001 -- persistence errors may contain secrets
            self.persistence_failed = True
            raise ProbePersistenceError(
                "MCP trace persistence failed; probe stopped."
            ) from None
        self.data = data

    def finish(self, state: str, diagnostic: str | None = None) -> None:
        data = copy.deepcopy(self.data)
        data.update(state=state, finished_at=timestamp())
        if diagnostic is not None:
            data["diagnostic"] = diagnostic
        self.save(data)


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
        data["calls"].append(call)
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


def child_environment(pdf: Path, run_dir: Path) -> dict[str, str]:
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


async def probe(run_dir: Path, mcp_executable: Path, mcp_cwd: Path) -> None:
    run_dir = run_dir.resolve()
    manifest, pdf, digest = verify_run(run_dir)
    mcp_executable, mcp_cwd = mcp_executable.resolve(), mcp_cwd.resolve()
    if not mcp_executable.is_file():
        raise ProbeError("MCP executable must be an existing file.")
    if not mcp_cwd.is_dir():
        raise ProbeError("MCP working directory must already exist.")

    trace = ProbeTrace(run_dir, manifest)
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
                    "env": child_environment(pdf, run_dir),
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
                operation = "cleanup"
    except asyncio.CancelledError:
        try:
            trace.finish("cancelled", "Connection verification cancelled.")
        except ProbePersistenceError:
            pass
        raise
    except Exception as error:  # noqa: BLE001 -- never display external error bodies
        diagnostic = (
            str(error)
            if isinstance(error, ProbeError)
            else f"MCP {operation} failed; check the executable and server configuration."
        )
        try:
            trace.finish("failed", diagnostic)
        except ProbePersistenceError:
            pass
        raise ProbeError(diagnostic) from None

    # Report success only after the connection and child process have closed.
    trace.finish("succeeded")
    print(f"Run: {json.dumps(manifest.run_id)}")
    print(f"Document: {manifest.document_id}")
    print(f"Tools: {', '.join(sorted(names))}")
    print("Connection verified; model calls: 0.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--mcp-executable", type=Path, required=True)
    parser.add_argument("--mcp-cwd", type=Path, required=True)
    args = parser.parse_args(argv)
    # SDK logs can include tool/error bodies. This standalone probe emits only
    # controlled diagnostics and restores logging for callers of main().
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(probe(args.run_dir, args.mcp_executable, args.mcp_cwd))
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
