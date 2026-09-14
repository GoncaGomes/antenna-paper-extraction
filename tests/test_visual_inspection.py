import asyncio
import base64
import io
import json
from pathlib import Path

import httpx
import pytest
from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from PIL import Image

from antenna_paper_extraction import visual_inspection
from antenna_paper_extraction.assets import AssetResolution, VisualCatalog


def _message_text(message: dict) -> str:
    content = message.get("content")

    if isinstance(content, str):
        return content

    return "\n".join(
        part["text"] for part in content or [] if part.get("type") == "text"
    )


@pytest.mark.parametrize(
    "request_image",
    [False, True],
    ids=["direct-answer", "image-then-answer"],
)
def test_run_visual_inspection_success_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request_image: bool,
) -> None:
    run_dir = tmp_path / "run"
    document_dir = run_dir / "document_conversion"
    document_dir.mkdir(parents=True)

    markdown = "# Test paper\n\nComplete document text.\n"
    (document_dir / "document.md").write_text(
        markdown,
        encoding="utf-8",
    )

    catalog = VisualCatalog(
        figures=(),
        pages=("page_0001",),
    )

    with Image.new("RGB", (2, 2), color="red") as image, io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

    resolver_calls: list[tuple[str, ...]] = []
    requests: list[dict] = []

    def fake_catalog(directory: Path) -> VisualCatalog:
        assert directory == run_dir.resolve()
        return catalog

    def fake_resolver(
        directory: Path,
        asset_ids: tuple[str, ...],
        *,
        max_assets: int,
    ) -> tuple[AssetResolution, ...]:
        assert directory == run_dir.resolve()
        assert asset_ids == ("page_0001",)
        assert max_assets == 1

        resolver_calls.append(asset_ids)

        return (
            AssetResolution(
                asset_id="page_0001",
                status="available",
                media_type="image/png",
                image_bytes=image_bytes,
                reason=None,
            ),
        )

    monkeypatch.setattr(
        visual_inspection,
        "build_visual_catalog",
        fake_catalog,
    )
    monkeypatch.setattr(
        visual_inspection,
        "resolve_visual_assets",
        fake_resolver,
    )

    expected_calls = 2 if request_image else 1

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"

        requests.append(json.loads(request.content))
        assert len(requests) <= expected_calls

        if request_image and len(requests) == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_visual_1",
                        "type": "function",
                        "function": {
                            "name": "get_visual_assets",
                            "arguments": json.dumps({"asset_ids": ["page_0001"]}),
                        },
                    }
                ],
            }
            finish_reason = "tool_calls"
        else:
            message = {
                "role": "assistant",
                "content": "Inspection complete.",
            }
            finish_reason = "stop"

        return httpx.Response(
            200,
            json={
                "id": f"chatcmpl-test-{len(requests)}",
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
            },
        )

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
                run_dir=run_dir,
                model=model,
                instructions="Inspect the supplied document.",
                max_assets=1,
            )

    result = asyncio.run(execute())

    expected_ids = ("page_0001",) if request_image else ()

    assert result.final_text == "Inspection complete."
    assert result.requested_asset_ids == expected_ids
    assert result.model_calls == expected_calls
    assert result.tool_executions == int(request_image)
    assert len(requests) == expected_calls
    assert resolver_calls == ([expected_ids] if request_image else [])

    initial_messages = requests[0]["messages"]
    initial_text = "\n".join(
        _message_text(message)
        for message in initial_messages
        if message["role"] == "user"
    )

    assert markdown in initial_text
    assert catalog.model_dump_json(indent=2) in initial_text
    assert "data:image/" not in json.dumps(initial_messages)

    if request_image:
        continuation = requests[1]["messages"]

        assert continuation[: len(initial_messages)] == initial_messages

        tool_messages = [
            message for message in continuation if message["role"] == "tool"
        ]
        assert len(tool_messages) == 1
        assert tool_messages[0]["tool_call_id"] == "call_visual_1"

        image_messages = [
            message
            for message in continuation
            if message["role"] == "user"
            and isinstance(message.get("content"), list)
            and any(part.get("type") == "image_url" for part in message["content"])
        ]
        assert len(image_messages) == 1

        parts = image_messages[0]["content"]

        assert json.loads(parts[0]["text"]) == {
            "asset_id": "page_0001",
            "status": "available",
        }
        assert parts[1]["type"] == "image_url"

        image_url = parts[1]["image_url"]["url"]
        prefix = "data:image/png;base64,"

        assert image_url.startswith(prefix)
        assert base64.b64decode(image_url[len(prefix) :]) == image_bytes
