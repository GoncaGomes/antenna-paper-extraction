from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI

from antenna_paper_extraction.architecture_report import (
    ARCHITECTURE_INSTRUCTIONS,
    validate_architecture_report,
)
from antenna_paper_extraction.persistence import write_bytes, write_json
from antenna_paper_extraction.runs import (
    PORTUGAL_TIMEZONE,
    PhaseFailure,
    RunManifest,
    load_run_status,
    mark_architecture_extraction_failed,
    mark_architecture_extraction_running,
    mark_architecture_extraction_succeeded,
)
from antenna_paper_extraction.visual_inspection import (
    InspectionChatCompletionsModel,
    build_inspection_instructions,
    run_visual_inspection,
)


async def run_architecture_agent(
    *,
    run_dir: Path,
    client: AsyncOpenAI,
    model_name: str,
    max_assets: int = 6,
) -> Path:
    """Generate an architecture report and persist execution events.

    The caller owns the client and must disable automatic retries.
    Existing architecture output directories are never overwritten.
    Success means execution and structural validation succeeded.
    It does not mean that the report passed scientific review.
    """
    if not model_name.strip():
        raise ValueError("Architecture model name must not be empty.")

    if not isinstance(max_assets, int) or isinstance(max_assets, bool):
        raise TypeError("Maximum asset count must be an integer.")

    if max_assets < 1:
        raise ValueError("Maximum asset count must be positive.")

    if client.max_retries != 0:
        raise ValueError("Architecture execution requires client max_retries=0.")

    run_dir = Path(run_dir).resolve()
    output_dir = run_dir / "architecture"

    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Architecture output already exists for run: {run_dir}")

    manifest = RunManifest.model_validate_json(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    run_status = load_run_status(run_dir)

    if run_status.run_id != manifest.run_id:
        raise ValueError("Run manifest and status identifiers do not match.")

    if run_status.phases.figure_extraction.state != "succeeded":
        raise ValueError(
            "Figure extraction must succeed before architecture extraction."
        )

    if run_status.phases.architecture_extraction.state != "pending":
        raise ValueError(
            "Architecture extraction can only start from the pending state."
        )

    report_path = output_dir / "architecture_evidence_report.md"
    execution_path = output_dir / "architecture_execution.json"

    # Reserve this execution's directory before creating any output.
    output_dir.mkdir()

    started_at = datetime.now(PORTUGAL_TIMEZONE)
    started_clock = perf_counter()
    events: list[dict[str, Any]] = []

    execution: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": manifest.run_id,
        "document_id": manifest.document_id,
        "state": "running",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "duration_seconds": 0.0,
        "configuration": {
            "model": model_name,
            "base_url": str(client.base_url),
            "client_timeout": repr(client.timeout),
            "max_retries": client.max_retries,
            "max_assets": max_assets,
            "max_turns": 2,
        },
        "instructions": build_inspection_instructions(
            ARCHITECTURE_INSTRUCTIONS,
            max_assets=max_assets,
        ),
        "events": events,
        "final_text": None,
        "inspection_summary": None,
        "structural_validation": None,
        "report_path": None,
        "error": None,
    }

    def save_execution() -> None:
        execution["duration_seconds"] = perf_counter() - started_clock
        execution["counts"] = {
            "model_requests": sum(event["type"] == "model_request" for event in events),
            "model_responses": sum(
                event["type"] == "model_response" for event in events
            ),
            "tool_invocations": sum(
                event["type"] == "tool_request" for event in events
            ),
            "tool_results": sum(event["type"] == "tool_result" for event in events),
        }
        write_json(execution_path, execution)

    def record_event(event: dict[str, Any]) -> None:
        events.append(event)
        save_execution()

    report_written = False
    phase_started = False

    try:
        running_status = mark_architecture_extraction_running(run_dir)
        phase_started = True

        running_phase = running_status.phases.architecture_extraction
        execution["started_at"] = running_phase.model_dump(mode="json")["started_at"]

        save_execution()

        model = InspectionChatCompletionsModel(
            model=model_name,
            openai_client=client,
            on_event=record_event,
        )

        result = await run_visual_inspection(
            run_dir=run_dir,
            model=model,
            instructions=ARCHITECTURE_INSTRUCTIONS,
            max_assets=max_assets,
        )

        execution["final_text"] = result.final_text
        execution["inspection_summary"] = {
            "requested_asset_ids": list(result.requested_asset_ids),
            "model_calls": result.model_calls,
            "tool_executions": result.tool_executions,
        }

        validation_errors = validate_architecture_report(result.final_text)

        execution["structural_validation"] = {
            "passed": not validation_errors,
            "errors": list(validation_errors),
        }

        # Preserve the candidate report and validation before accepting it.
        save_execution()

        if validation_errors:
            raise ValueError(
                "Architecture report failed structural validation: "
                + "; ".join(validation_errors)
            )

        write_bytes(report_path, result.final_text.encode("utf-8"))
        report_written = True

        execution["state"] = "succeeded"
        execution["finished_at"] = datetime.now(PORTUGAL_TIMEZONE).isoformat()
        execution["report_path"] = report_path.relative_to(run_dir).as_posix()
        save_execution()

        mark_architecture_extraction_succeeded(run_dir)

    except Exception as error:
        # Remove only a report created by this execution, if finalization failed.
        if report_written:
            try:
                report_path.unlink()
            except OSError as cleanup_error:
                error.add_note(
                    "Could not remove the report after execution failure: "
                    f"{cleanup_error}"
                )

        execution["state"] = "failed"
        execution["finished_at"] = datetime.now(PORTUGAL_TIMEZONE).isoformat()
        execution["report_path"] = None
        execution["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }

        try:
            save_execution()
        except (OSError, TypeError, ValueError) as persistence_error:
            error.add_note(
                f"Could not persist the final failure state: {persistence_error}"
            )

        if phase_started:
            try:
                mark_architecture_extraction_failed(
                    run_dir,
                    PhaseFailure(
                        type=type(error).__name__,
                        message=str(error),
                    ),
                )
            except (OSError, ValueError) as status_error:
                error.add_note(
                    f"Could not persist the global failure state: {status_error}"
                )

        raise

    return report_path
