"""Reserve and publish MCP architecture artefacts without changing run lifecycle."""

import copy
from pathlib import Path

from antenna_paper_extraction.architecture_report import validate_architecture_report
from antenna_paper_extraction.mcp_agent import (
    ProbeError,
    ProbePersistenceError,
    ProbeTrace,
    timestamp,
)
from antenna_paper_extraction.persistence import write_bytes


def reserve_architecture_output(run_dir: Path) -> Path:
    """Exclusively reserve this execution after the caller's local preflight."""
    storage = run_dir / "mcp"
    output = storage / "architecture"
    if output.exists() or output.is_symlink():
        raise ProbeError("MCP architecture output already exists for this run.")
    if not storage.resolve().is_relative_to(run_dir.resolve()) or not (
        output.resolve().is_relative_to(storage.resolve())
    ):
        raise ProbeError("MCP architecture output escapes the run MCP directory.")
    try:
        output.mkdir(parents=True)
    except FileExistsError:
        raise ProbeError(
            "MCP architecture output already exists for this run."
        ) from None
    except OSError:
        raise ProbePersistenceError(
            "MCP architecture output reservation failed."
        ) from None
    return output / "architecture_execution.json"


def finalize_architecture_report(trace: ProbeTrace) -> None:
    """Publish persisted, redacted text only after model/server cleanup succeeds."""
    final_text = trace.data["final_text"]
    if not isinstance(final_text, str) or not final_text.strip():
        raise ProbeError("MCP architecture execution has no usable final text.")
    errors = validate_architecture_report(final_text)
    data = copy.deepcopy(trace.data)
    data["structural_validation"] = {"passed": not errors, "errors": list(errors)}
    # Required diagnostics must be durable before Markdown publication.
    trace.save(data)
    report_path = trace.path.parent / "architecture_evidence_report.md"
    try:
        write_bytes(report_path, trace.data["final_text"].encode("utf-8"))
    except Exception:  # noqa: BLE001 -- never expose external persistence errors
        raise ProbePersistenceError(
            "MCP architecture report publication failed."
        ) from None

    data = copy.deepcopy(trace.data)
    data.update(
        report_path=report_path.relative_to(trace.run_dir).as_posix(),
        state="succeeded",
        finished_at=timestamp(),
        termination_reason="final_answer",
    )
    try:
        trace.save(data)
    except ProbePersistenceError:
        # Remove only the report just published, preserving all execution evidence.
        try:
            report_path.unlink()
        except OSError:
            raise ProbePersistenceError(
                "MCP architecture finalization failed; published report removal failed."
            ) from None
        raise
