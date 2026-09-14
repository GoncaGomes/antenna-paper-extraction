"""Local integration tests using real assets and scripted HTTP responses."""

import asyncio
import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from agents import OpenAIChatCompletionsModel
from agents.exceptions import ModelBehaviorError, UserError
from openai import APITimeoutError, AsyncOpenAI, InternalServerError
from PIL import Image

from antenna_paper_extraction import visual_inspection
from antenna_paper_extraction.assets import AssetResolution, build_visual_catalog

MARKDOWN = "# Test paper\n\nComplete document text.\n"
FINAL_TEXT = "Inspection complete."
UNAVAILABLE_REASON = "Figure crop is not materialized."


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "\n".join(
        part["text"] for part in content or [] if part.get("type") == "text"
    )


def _tool_call(arguments: str, call_id: str = "call_visual_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "get_visual_assets", "arguments": arguments},
    }


def _asset_call(*asset_ids: str, call_id: str = "call_visual_1") -> dict:
    return _tool_call(json.dumps({"asset_ids": list(asset_ids)}), call_id)


def _completion(*tool_calls: dict, text: str = FINAL_TEXT) -> httpx.Response:
    message: dict = {"role": "assistant", "content": text}
    if tool_calls:
        message.update(content=None, tool_calls=list(tool_calls))
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                }
            ],
        },
    )


@dataclass
class _InspectionCase:
    run_dir: Path
    payloads: dict[str, bytes]
    requests: list[dict] = field(default_factory=list)
    resolver_calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        responses: list[httpx.Response | httpx.TransportError],
        *,
        max_assets: int = 3,
    ) -> visual_inspection.VisualInspectionResult:
        def respond(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/chat/completions"
            self.requests.append(json.loads(request.content))
            assert len(self.requests) <= len(responses), "Unexpected HTTP request"
            response = responses[len(self.requests) - 1]
            if isinstance(response, httpx.TransportError):
                raise response
            return response

        async def execute() -> visual_inspection.VisualInspectionResult:
            async with AsyncOpenAI(
                api_key="test-key",
                base_url="https://model.invalid/v1",
                max_retries=0,
                http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(respond),
                ),
            ) as client:
                model = OpenAIChatCompletionsModel(
                    model="test-model",
                    openai_client=client,
                )
                return await visual_inspection.run_visual_inspection(
                    run_dir=self.run_dir,
                    model=model,
                    instructions="Inspect the supplied document.",
                    max_assets=max_assets,
                )

        return asyncio.run(execute())


@pytest.fixture
def inspection_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _InspectionCase:
    run_dir = tmp_path / "run"
    for directory in ("document_conversion", "pages", "figures"):
        (run_dir / directory).mkdir(parents=True)
    (run_dir / "document_conversion" / "document.md").write_text(
        MARKDOWN, encoding="utf-8"
    )

    payloads: dict[str, bytes] = {}
    for asset_id, directory, color in (
        ("figure_1", "figures", "red"),
        ("page_0001", "pages", "blue"),
    ):
        with Image.new("RGB", (2, 2), color=color) as image, io.BytesIO() as buffer:
            image.save(buffer, format="PNG")
            payloads[asset_id] = buffer.getvalue()
        (run_dir / directory / f"{asset_id}.png").write_bytes(payloads[asset_id])

    pages_manifest = {
        "schema_version": "1.0",
        "document_id": f"sha256:{'0' * 64}",
        "page_count": 1,
        "render_settings": {"renderer_version": "test"},
        "pages": [
            {
                "asset_id": "page_0001",
                "page_number": 1,
                "relative_path": "pages/page_0001.png",
                "width_pixels": 2,
                "height_pixels": 2,
                "size_bytes": len(payloads["page_0001"]),
                "sha256": "0" * 64,
            }
        ],
    }
    (run_dir / "pages" / "pages.json").write_text(
        json.dumps(pages_manifest), encoding="utf-8"
    )
    # Only the fields consumed by the catalog and resolver are needed here.
    figures = [
        {
            "figure_id": f"figure_{number}",
            "relative_path": "figures/figure_1.png" if number == 1 else None,
            "markdown_captions": [f"Figure {number}. Test caption."],
            "candidates": [{"positions": [{"page_no": 1}]}],
        }
        for number in (1, 2)
    ]
    (run_dir / "figures" / "manifest.json").write_text(
        json.dumps({"figures": figures}), encoding="utf-8"
    )

    case = _InspectionCase(run_dir=run_dir, payloads=payloads)
    original_resolver = visual_inspection.resolve_visual_assets

    def record_resolution(
        directory: Path,
        asset_ids: tuple[str, ...],
        *,
        max_assets: int,
    ) -> tuple[AssetResolution, ...]:
        assert directory == run_dir.resolve()
        case.resolver_calls.append(asset_ids)
        return original_resolver(directory, asset_ids, max_assets=max_assets)

    monkeypatch.setattr(visual_inspection, "resolve_visual_assets", record_resolution)
    return case


def _assert_initial_input(case: _InspectionCase) -> None:
    messages = case.requests[0]["messages"]
    user_text = "\n".join(
        _message_text(message) for message in messages if message["role"] == "user"
    )
    assert MARKDOWN in user_text
    assert build_visual_catalog(case.run_dir).model_dump_json(indent=2) in user_text
    assert "data:image/" not in json.dumps(messages)


def _assert_continuation(case: _InspectionCase) -> list[dict]:
    initial = case.requests[0]["messages"]
    continuation = case.requests[1]["messages"]
    assert continuation[: len(initial)] == initial
    additions = continuation[len(initial) :]
    assert additions[0]["role"] == "assistant"
    assert additions[0]["tool_calls"][0]["id"] == "call_visual_1"
    tool_messages = [item for item in additions if item["role"] == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "call_visual_1"
    return additions


def test_run_visual_inspection_returns_direct_answer(
    inspection_case: _InspectionCase,
) -> None:
    result = inspection_case.run([_completion()])
    assert result == visual_inspection.VisualInspectionResult(
        final_text=FINAL_TEXT,
        requested_asset_ids=(),
        model_calls=1,
        tool_executions=0,
    )
    assert len(inspection_case.requests) == 1
    assert inspection_case.resolver_calls == []
    _assert_initial_input(inspection_case)


@pytest.mark.parametrize(
    "asset_ids",
    [
        ("page_0001",),
        ("figure_1",),
        ("figure_1", "page_0001"),
        ("page_0001", "figure_1"),
        ("figure_1", "figure_2", "page_0001"),
    ],
    ids=["page", "figure", "figure-page", "page-figure", "partly-unavailable"],
)
def test_run_visual_inspection_preserves_asset_order_and_image_bytes(
    inspection_case: _InspectionCase,
    asset_ids: tuple[str, ...],
) -> None:
    case = inspection_case
    result = case.run([_completion(_asset_call(*asset_ids)), _completion()])
    assert result == visual_inspection.VisualInspectionResult(
        final_text=FINAL_TEXT,
        requested_asset_ids=asset_ids,
        model_calls=2,
        tool_executions=1,
    )
    assert len(case.requests) == 2
    assert case.resolver_calls == [asset_ids]
    _assert_initial_input(case)
    additions = _assert_continuation(case)

    image_messages = [item for item in additions if item["role"] == "user"]
    assert len(image_messages) == 1
    parts = image_messages[0]["content"]
    assert isinstance(parts, list)

    position = 0
    for asset_id in asset_ids:
        metadata = {"asset_id": asset_id, "status": "available"}
        if asset_id == "figure_2":
            metadata.update(status="unavailable", reason=UNAVAILABLE_REASON)
        assert parts[position]["type"] == "text"
        assert json.loads(parts[position]["text"]) == metadata
        position += 1
        if asset_id == "figure_2":
            continue
        assert parts[position]["type"] == "image_url"
        image_url = parts[position]["image_url"]["url"]
        prefix = "data:image/png;base64,"
        assert image_url.startswith(prefix)
        assert base64.b64decode(image_url[len(prefix) :]) == case.payloads[asset_id]
        position += 1
    assert position == len(parts)


def test_run_visual_inspection_reports_unavailable_asset_without_page_fallback(
    inspection_case: _InspectionCase,
) -> None:
    case = inspection_case
    # The associated page exists, but it must not be substituted automatically.
    assert build_visual_catalog(case.run_dir).figures[1].page_id == "page_0001"
    result = case.run([_completion(_asset_call("figure_2")), _completion()])
    assert result == visual_inspection.VisualInspectionResult(
        final_text=FINAL_TEXT,
        requested_asset_ids=("figure_2",),
        model_calls=2,
        tool_executions=1,
    )
    assert len(case.requests) == 2
    assert case.resolver_calls == [("figure_2",)]
    additions = _assert_continuation(case)
    assert [item["role"] for item in additions] == ["assistant", "tool"]
    assert json.loads(_message_text(additions[1])) == {
        "asset_id": "figure_2",
        "status": "unavailable",
        "reason": UNAVAILABLE_REASON,
    }
    assert "data:image/" not in json.dumps(case.requests[1]["messages"])


@pytest.mark.parametrize(
    "arguments",
    ["{not-json", "{}", '{"asset_ids": 42}'],
    ids=["malformed-json", "missing-argument", "wrong-type"],
)
def test_run_visual_inspection_rejects_invalid_tool_arguments(
    inspection_case: _InspectionCase,
    arguments: str,
) -> None:
    with pytest.raises(ModelBehaviorError, match="Invalid JSON input for tool"):
        inspection_case.run([_completion(_tool_call(arguments))])
    assert len(inspection_case.requests) == 1
    assert inspection_case.resolver_calls == []


@pytest.mark.parametrize(
    ("asset_ids", "max_assets", "message"),
    [
        (("figure_999",), 3, "Unknown visual asset"),
        (("figure_1", "figure_1"), 3, "Repeated asset identifiers"),
        ((), 3, "At least one asset"),
        (("figure_1", "page_0001"), 1, "exceed the limit"),
    ],
    ids=["unknown", "duplicate", "empty", "over-limit"],
)
def test_run_visual_inspection_propagates_resolver_rejections(
    inspection_case: _InspectionCase,
    asset_ids: tuple[str, ...],
    max_assets: int,
    message: str,
) -> None:
    with pytest.raises(UserError, match=message) as caught:
        inspection_case.run(
            [_completion(_asset_call(*asset_ids))], max_assets=max_assets
        )
    assert isinstance(caught.value.__cause__, ValueError)
    assert len(inspection_case.requests) == 1
    assert inspection_case.resolver_calls == [asset_ids]


@pytest.mark.parametrize("same_response", [True, False], ids=["same-turn", "next-turn"])
def test_run_visual_inspection_rejects_an_additional_tool_request(
    inspection_case: _InspectionCase,
    same_response: bool,
) -> None:
    first = _asset_call("figure_1")
    second = _asset_call("page_0001", call_id="call_visual_2")
    responses = (
        [_completion(first, second)]
        if same_response
        else [_completion(first), _completion(second)]
    )
    with pytest.raises(
        UserError, match="A second asset request is not allowed"
    ) as caught:
        inspection_case.run(responses)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert len(inspection_case.requests) == (1 if same_response else 2)
    assert inspection_case.resolver_calls == [("figure_1",)]


@pytest.mark.parametrize("after_tool", [False, True], ids=["before-tool", "after-tool"])
@pytest.mark.parametrize("failure", ["http-500", "timeout"])
def test_run_visual_inspection_propagates_model_failure_without_retry(
    inspection_case: _InspectionCase,
    after_tool: bool,
    failure: str,
) -> None:
    responses: list[httpx.Response | httpx.TransportError] = []
    if after_tool:
        responses.append(_completion(_asset_call("figure_1")))
    if failure == "http-500":
        responses.append(
            httpx.Response(
                500,
                json={
                    "error": {
                        "message": "Synthetic server failure.",
                        "type": "server_error",
                    }
                },
            )
        )
        expected_error = InternalServerError
    else:
        responses.append(httpx.ReadTimeout("Synthetic timeout."))
        expected_error = APITimeoutError
    with pytest.raises(expected_error):
        inspection_case.run(responses)
    assert len(inspection_case.requests) == (2 if after_tool else 1)
    assert inspection_case.resolver_calls == ([("figure_1",)] if after_tool else [])


def test_run_visual_inspection_rejects_empty_final_text(
    inspection_case: _InspectionCase,
) -> None:
    with pytest.raises(RuntimeError, match="Visual inspection returned no final text"):
        inspection_case.run([_completion(text=" ")])
    assert len(inspection_case.requests) == 1
    assert inspection_case.resolver_calls == []
