import asyncio
from pathlib import Path

import pytest
from agents.exceptions import ModelBehaviorError
from openai import AsyncOpenAI

from antenna_paper_extraction import architecture
from antenna_paper_extraction.architecture_report import ARCHITECTURE_INSTRUCTIONS
from antenna_paper_extraction.persistence import read_json, write_json
from antenna_paper_extraction.visual_inspection import VisualInspectionResult

REPORT = """\
## 1. Selected antenna

The supplied material does not identify a final antenna design.

## 2. Components, materials and layers

Material properties and layer details are unavailable.

## 3. Geometry, dimensions and feeding

Dimensions and feeding details are unavailable.

## 4. Derivations and conflicts

No supported derivation can be established.

## 5. Reconstruction gaps

The available information is insufficient for reconstruction.
"""


def _completion(
    text: str | None,
    *,
    finish_reason: str = "stop",
    tool_calls: list[dict] | None = None,
) -> dict:
    message = {
        "role": "assistant",
        "content": text,
    }

    if tool_calls is not None:
        message["tool_calls"] = tool_calls

    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }


def _run(run_dir: Path) -> Path:
    async def execute() -> Path:
        async with AsyncOpenAI(
            api_key="test-key",
            base_url="https://model.invalid/v1",
            max_retries=0,
            timeout=30.0,
        ) as client:
            return await architecture.run_architecture_agent(
                run_dir=run_dir,
                client=client,
                model_name="test-model",
                max_assets=3,
            )

    return asyncio.run(execute())


@pytest.fixture
def prepared_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    timestamp = "2026-09-17T10:00:00+01:00"
    document_id = f"sha256:{'0' * 64}"

    write_json(
        run_dir / "manifest.json",
        {
            "run_id": "run_test",
            "created_at": timestamp,
            "document_id": document_id,
            "source_pdf": {
                "original_filename": "paper.pdf",
                "relative_path": "input/paper.pdf",
                "sha256": "0" * 64,
                "size_bytes": 1,
            },
        },
    )

    completed_phase = {
        "state": "succeeded",
        "started_at": timestamp,
        "finished_at": timestamp,
    }

    write_json(
        run_dir / "status.json",
        {
            "run_id": "run_test",
            "phases": {
                name: completed_phase
                for name in (
                    "source_preservation",
                    "page_rendering",
                    "document_conversion",
                    "figure_extraction",
                )
            },
        },
    )

    return run_dir


@pytest.fixture
def install_inspection(monkeypatch: pytest.MonkeyPatch):
    def install(
        *,
        final_text: str = REPORT,
        events: list[dict] | None = None,
        error: Exception | None = None,
    ) -> list[Path]:
        calls: list[Path] = []

        scripted_events = (
            events
            if events is not None
            else [
                {"type": "model_request"},
                {
                    "type": "model_response",
                    "response": _completion(final_text),
                },
            ]
        )

        async def inspect(
            *,
            run_dir: Path,
            model,
            instructions: str,
            max_assets: int,
        ) -> VisualInspectionResult:
            calls.append(run_dir)

            assert instructions == ARCHITECTURE_INSTRUCTIONS
            assert max_assets == 3

            execution_path = run_dir / "architecture" / "architecture_execution.json"

            for index, event in enumerate(scripted_events):
                model.record_event(event)

                # Each event must already be on disk before execution continues.
                saved = read_json(execution_path)
                assert saved["state"] == "running"
                assert saved["events"] == scripted_events[: index + 1]

            if error is not None:
                raise error

            return VisualInspectionResult(
                final_text=final_text,
                requested_asset_ids=(),
                model_calls=1,
                tool_executions=0,
            )

        monkeypatch.setattr(architecture, "run_visual_inspection", inspect)
        return calls

    return install


def test_persists_events_and_publishes_valid_report(
    prepared_run: Path,
    install_inspection,
) -> None:
    calls = install_inspection()
    original_status = (prepared_run / "status.json").read_bytes()

    report_path = _run(prepared_run)

    assert calls == [prepared_run.resolve()]
    assert report_path.read_text(encoding="utf-8") == REPORT

    execution = read_json(prepared_run / "architecture" / "architecture_execution.json")

    assert execution["state"] == "succeeded"
    assert execution["run_id"] == "run_test"
    assert execution["final_text"] == REPORT
    assert execution["structural_validation"] == {
        "passed": True,
        "errors": [],
    }
    assert execution["counts"] == {
        "model_requests": 1,
        "model_responses": 1,
        "tool_invocations": 0,
        "tool_results": 0,
    }
    assert execution["events"][1]["response"] == _completion(REPORT)
    assert execution["report_path"] == ("architecture/architecture_evidence_report.md")
    assert execution["error"] is None
    assert execution["finished_at"] is not None
    assert execution["duration_seconds"] >= 0
    assert "Visual inspection rules:" in execution["instructions"]

    # Global lifecycle integration belongs to the next increment.
    assert (prepared_run / "status.json").read_bytes() == original_status


def test_preserves_invalid_final_text_without_publishing_report(
    prepared_run: Path,
    install_inspection,
) -> None:
    invalid_report = "A report without the required sections."
    install_inspection(final_text=invalid_report)

    with pytest.raises(ValueError, match="failed structural validation"):
        _run(prepared_run)

    output_dir = prepared_run / "architecture"
    execution = read_json(output_dir / "architecture_execution.json")

    assert execution["state"] == "failed"
    assert execution["final_text"] == invalid_report
    assert execution["structural_validation"]["passed"] is False
    assert execution["structural_validation"]["errors"]
    assert execution["error"]["type"] == "ValueError"
    assert not (output_dir / "architecture_evidence_report.md").exists()


def test_preserves_truncated_response_without_publishing_report(
    prepared_run: Path,
    install_inspection,
) -> None:
    response = _completion(
        "The antenna consists of",
        finish_reason="length",
    )
    install_inspection(
        events=[
            {"type": "model_request"},
            {"type": "model_response", "response": response},
        ],
        error=ModelBehaviorError("finish_reason='length'"),
    )

    with pytest.raises(ModelBehaviorError, match="length"):
        _run(prepared_run)

    output_dir = prepared_run / "architecture"
    execution = read_json(output_dir / "architecture_execution.json")

    assert execution["state"] == "failed"
    assert execution["events"][1]["response"] == response
    assert execution["final_text"] is None
    assert execution["structural_validation"] is None
    assert not (output_dir / "architecture_evidence_report.md").exists()


def test_preserves_tool_exchange_when_second_model_call_fails(
    prepared_run: Path,
    install_inspection,
) -> None:
    tool_call = {
        "id": "call_visual_1",
        "type": "function",
        "function": {
            "name": "get_visual_assets",
            "arguments": '{"asset_ids": ["figure_1"]}',
        },
    }
    first_response = _completion(
        None,
        finish_reason="tool_calls",
        tool_calls=[tool_call],
    )
    events = [
        {"type": "model_request"},
        {
            "type": "model_response",
            "response": first_response,
        },
        {
            "type": "tool_request",
            "call_id": "call_visual_1",
            "name": "get_visual_assets",
            "asset_ids": ["figure_1"],
        },
        {
            "type": "tool_result",
            "call_id": "call_visual_1",
            "status": "succeeded",
            "assets": [
                {
                    "asset_id": "figure_1",
                    "status": "available",
                }
            ],
        },
        {"type": "model_request"},
        {
            "type": "model_error",
            "error": {
                "type": "RuntimeError",
                "message": "Synthetic second-call failure.",
            },
        },
    ]
    install_inspection(
        events=events,
        error=RuntimeError("Synthetic second-call failure."),
    )

    with pytest.raises(RuntimeError, match="second-call failure"):
        _run(prepared_run)

    output_dir = prepared_run / "architecture"
    execution = read_json(output_dir / "architecture_execution.json")

    assert execution["state"] == "failed"
    assert execution["events"] == events
    assert execution["counts"] == {
        "model_requests": 2,
        "model_responses": 1,
        "tool_invocations": 1,
        "tool_results": 1,
    }
    assert execution["error"]["message"] == "Synthetic second-call failure."
    assert not (output_dir / "architecture_evidence_report.md").exists()


def test_rejects_existing_output_before_inspection(
    prepared_run: Path,
    install_inspection,
) -> None:
    calls = install_inspection()

    output_dir = prepared_run / "architecture"
    output_dir.mkdir()
    existing_report = output_dir / "architecture_evidence_report.md"
    existing_report.write_text("Existing report.", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        _run(prepared_run)

    assert calls == []
    assert existing_report.read_text(encoding="utf-8") == "Existing report."
    assert not (output_dir / "architecture_execution.json").exists()


def test_rejects_unfinished_figure_extraction(
    prepared_run: Path,
    install_inspection,
) -> None:
    calls = install_inspection()

    status = read_json(prepared_run / "status.json")
    status["phases"]["figure_extraction"] = {"state": "pending"}
    write_json(prepared_run / "status.json", status)

    with pytest.raises(ValueError, match="Figure extraction must succeed"):
        _run(prepared_run)

    assert calls == []
    assert not (prepared_run / "architecture").exists()


def test_removes_report_if_success_state_cannot_be_saved(
    prepared_run: Path,
    install_inspection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_inspection()
    original_write_json = architecture.write_json

    def fail_success_write(path: Path, data: dict) -> None:
        if data.get("state") == "succeeded":
            raise OSError("Synthetic finalization failure.")

        original_write_json(path, data)

    monkeypatch.setattr(architecture, "write_json", fail_success_write)

    with pytest.raises(OSError, match="finalization failure"):
        _run(prepared_run)

    output_dir = prepared_run / "architecture"
    execution = read_json(output_dir / "architecture_execution.json")

    assert execution["state"] == "failed"
    assert execution["final_text"] == REPORT
    assert execution["events"][1]["response"] == _completion(REPORT)
    assert execution["report_path"] is None
    assert not (output_dir / "architecture_evidence_report.md").exists()
