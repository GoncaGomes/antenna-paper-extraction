import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter

from antenna_paper_extraction import document
from antenna_paper_extraction.document import (
    DOCUMENT_CONVERSION_BATCH_SIZE,
    DOCUMENT_CONVERSION_INSTRUCTION,
    build_document_messages,
    convert_document_to_markdown,
    parse_document_markdown_response,
)
from antenna_paper_extraction.model_client import RawChatCompletion
from antenna_paper_extraction.pages import PageAsset, render_pdf_pages
from antenna_paper_extraction.runs import create_run, load_run_status


def test_build_document_messages_preserves_page_order_and_identity(
    tmp_path: Path,
) -> None:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()

    first_page_bytes = b"first-page"
    second_page_bytes = b"second-page"

    (pages_dir / "page_0001.png").write_bytes(first_page_bytes)
    (pages_dir / "page_0002.png").write_bytes(second_page_bytes)

    page_assets = (
        PageAsset(
            asset_id="page_0001",
            page_number=1,
            relative_path="pages/page_0001.png",
            width_pixels=1,
            height_pixels=1,
            size_bytes=len(first_page_bytes),
            sha256=hashlib.sha256(first_page_bytes).hexdigest(),
        ),
        PageAsset(
            asset_id="page_0002",
            page_number=2,
            relative_path="pages/page_0002.png",
            width_pixels=1,
            height_pixels=1,
            size_bytes=len(second_page_bytes),
            sha256=hashlib.sha256(second_page_bytes).hexdigest(),
        ),
    )

    messages = build_document_messages(
        run_dir=tmp_path,
        pages=page_assets,
    )

    assert messages == [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": DOCUMENT_CONVERSION_INSTRUCTION,
                },
                {
                    "type": "image_url",
                    "image_url": {"url": ("data:image/png;base64,Zmlyc3QtcGFnZQ==")},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": ("data:image/png;base64,c2Vjb25kLXBhZ2U=")},
                },
            ],
        }
    ]


def test_build_document_messages_rejects_modified_page_content(
    tmp_path: Path,
) -> None:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()

    expected_page_bytes = b"first-page"
    modified_page_bytes = b"x" * len(expected_page_bytes)

    assert len(modified_page_bytes) == len(expected_page_bytes)

    (pages_dir / "page_0001.png").write_bytes(modified_page_bytes)
    page = PageAsset(
        asset_id="page_0001",
        page_number=1,
        relative_path="pages/page_0001.png",
        width_pixels=1,
        height_pixels=1,
        size_bytes=len(expected_page_bytes),
        sha256=hashlib.sha256(expected_page_bytes).hexdigest(),
    )

    with pytest.raises(
        ValueError,
        match="checksum does not match manifest",
    ):
        build_document_messages(
            run_dir=tmp_path,
            pages=(page,),
        )


def test_build_document_messages_rejects_path_outside_run(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    outside_page_bytes = b"outside-page"
    outside_page = tmp_path / "outside-page.png"

    outside_page.write_bytes(outside_page_bytes)

    page = PageAsset(
        asset_id="page_0001",
        page_number=1,
        relative_path="../outside-page.png",
        width_pixels=1,
        height_pixels=1,
        size_bytes=len(outside_page_bytes),
        sha256=hashlib.sha256(outside_page_bytes).hexdigest(),
    )

    with pytest.raises(ValueError, match="path escapes run directory"):
        build_document_messages(
            run_dir=run_dir,
            pages=(page,),
        )


def test_build_document_messages_rejects_missing_page(
    tmp_path: Path,
) -> None:
    expected_page_bytes = b"missing-page"

    page = PageAsset(
        asset_id="page_0001",
        page_number=1,
        relative_path="pages/page_0001.png",
        width_pixels=1,
        height_pixels=1,
        size_bytes=len(expected_page_bytes),
        sha256=hashlib.sha256(expected_page_bytes).hexdigest(),
    )

    with pytest.raises(
        FileNotFoundError,
        match="Page asset does not exist",
    ):
        build_document_messages(
            run_dir=tmp_path,
            pages=(page,),
        )


def test_build_document_messages_rejects_incorrect_page_size(
    tmp_path: Path,
) -> None:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()

    page_bytes = b"page-content"
    (pages_dir / "page_0001.png").write_bytes(page_bytes)

    page = PageAsset(
        asset_id="page_0001",
        page_number=1,
        relative_path="pages/page_0001.png",
        width_pixels=1,
        height_pixels=1,
        size_bytes=len(page_bytes) + 1,
        sha256=hashlib.sha256(page_bytes).hexdigest(),
    )

    with pytest.raises(
        ValueError,
        match="size does not match manifest",
    ):
        build_document_messages(
            run_dir=tmp_path,
            pages=(page,),
        )


def test_parse_document_markdown_response_accepts_openai_compatible_envelope() -> None:
    markdown = "# Test document"

    usage = {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
    }

    response_payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1788253200,
        "model": "nuextract3",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": markdown,
                    "refusal": None,
                },
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
        "usage": usage,
        "system_fingerprint": None,
        "service_tier": "default",
    }

    response = RawChatCompletion(
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(response_payload).encode("utf-8"),
    )

    parsed_response = parse_document_markdown_response(
        response=response,
    )

    assert parsed_response.markdown == markdown
    assert parsed_response.finish_reason == "stop"
    assert parsed_response.usage == usage


def test_parse_document_markdown_response_rejects_non_string_content() -> None:
    response_payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1788253200,
        "model": "nuextract3",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": 123,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": None,
    }

    response = RawChatCompletion(
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(response_payload).encode("utf-8"),
    )

    with pytest.raises(ValidationError, match="content"):
        parse_document_markdown_response(
            response=response,
        )


def test_convert_document_to_markdown_persists_successful_conversion(
    tmp_path: Path,
) -> None:
    run_dir = _create_rendered_run(tmp_path)

    markdown = "# Test document"

    usage = {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
    }

    response_payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1788253200,
        "model": "nuextract3",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": markdown,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }

    raw_response_body = json.dumps(response_payload).encode("utf-8")

    client = Mock()
    client.create_raw_chat_completion.return_value = RawChatCompletion(
        status_code=200,
        headers={"content-type": "application/json"},
        body=raw_response_body,
    )

    document_path = convert_document_to_markdown(
        run_dir=run_dir,
        client=client,
        model="nuextract3",
    )

    conversion_path = run_dir / "document_conversion"

    assert document_path == conversion_path / "document.md"
    assert document_path.read_text(encoding="utf-8") == markdown

    assert (
        conversion_path / "nuextract3_raw_response_batch_0001.json"
    ).read_bytes() == (raw_response_body)

    trace = json.loads(
        (conversion_path / "nuextract3_trace_batch_0001.json").read_text(
            encoding="utf-8"
        )
    )

    assert trace["requested_model"] == "nuextract3"
    assert trace["temperature"] == 0.0
    assert trace["mode"] == "markdown"
    assert trace["enable_thinking"] is False
    assert trace["http_status_code"] == 200
    assert trace["finish_reason"] == "stop"
    assert trace["usage"] == usage
    assert trace["model_latency_seconds"] >= 0.0

    conversion_status = load_run_status(run_dir).phases.document_conversion

    assert conversion_status.state == "succeeded"
    assert conversion_status.started_at is not None
    assert conversion_status.finished_at is not None
    assert conversion_status.finished_at >= conversion_status.started_at
    assert conversion_status.error is None

    client.create_raw_chat_completion.assert_called_once()

    request = client.create_raw_chat_completion.call_args.kwargs

    assert request["model"] == "nuextract3"
    assert request["temperature"] == 0.0
    assert request["extra_body"] == {
        "chat_template_kwargs": {
            "mode": "markdown",
            "enable_thinking": False,
        }
    }


def test_convert_document_to_markdown_batches_pages_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _create_rendered_run(tmp_path, page_count=19)
    conversion_path = run_dir / "document_conversion"
    batch_markdowns = ["# Pages 1-8", "# Pages 9-16", "# Pages 17-19"]
    page_batches: list[tuple[int, ...]] = []

    def track_batch_pages(
        run_dir: Path,
        pages: tuple[PageAsset, ...],
    ) -> list[dict[str, object]]:
        page_batches.append(tuple(page.page_number for page in pages))
        return build_document_messages(run_dir, pages)

    monkeypatch.setattr(document, "build_document_messages", track_batch_pages)

    responses = [
        _raw_chat_completion(markdown, response_id=f"chatcmpl-batch-{batch_number}")
        for batch_number, markdown in enumerate(batch_markdowns, start=1)
    ]

    client = Mock()
    client.create_raw_chat_completion.side_effect = responses

    document_path = convert_document_to_markdown(
        run_dir=run_dir,
        client=client,
        model="nuextract3",
    )

    assert DOCUMENT_CONVERSION_BATCH_SIZE == 8
    assert client.create_raw_chat_completion.call_count == 3
    assert page_batches == [
        tuple(range(1, 9)),
        tuple(range(9, 17)),
        tuple(range(17, 20)),
    ]
    assert document_path.read_text(encoding="utf-8") == "\n\n".join(batch_markdowns)
    assert list(run_dir.rglob("document.md")) == [document_path]
    assert sorted(path.name for path in conversion_path.glob("*.json")) == [
        "nuextract3_raw_response_batch_0001.json",
        "nuextract3_raw_response_batch_0002.json",
        "nuextract3_raw_response_batch_0003.json",
        "nuextract3_trace_batch_0001.json",
        "nuextract3_trace_batch_0002.json",
        "nuextract3_trace_batch_0003.json",
    ]

    for batch_number, response in enumerate(responses, start=1):
        assert (
            conversion_path / f"nuextract3_raw_response_batch_{batch_number:04d}.json"
        ).read_bytes() == response.body


def test_convert_document_to_markdown_records_transport_failure(
    tmp_path: Path,
) -> None:
    run_dir = _create_rendered_run(tmp_path)

    client = Mock()
    client.create_raw_chat_completion.side_effect = TimeoutError("secret-api-key-value")

    with pytest.raises(
        TimeoutError,
        match="secret-api-key-value",
    ):
        convert_document_to_markdown(
            run_dir=run_dir,
            client=client,
            model="nuextract3",
        )

    conversion_status = load_run_status(run_dir).phases.document_conversion

    assert conversion_status.state == "failed"
    assert conversion_status.started_at is not None
    assert conversion_status.finished_at is not None
    assert conversion_status.finished_at >= conversion_status.started_at
    assert conversion_status.error is not None
    assert conversion_status.error.type == "TimeoutError"
    assert conversion_status.error.message == (
        "Document conversion failed during model request."
    )

    assert "secret-api-key-value" not in (run_dir / "status.json").read_text(
        encoding="utf-8"
    )

    conversion_path = run_dir / "document_conversion"

    assert not (conversion_path / "nuextract3_raw_response_batch_0001.json").exists()
    assert not (conversion_path / "document.md").exists()

    assert client.create_raw_chat_completion.call_count == 1


def test_convert_document_to_markdown_preserves_incomplete_raw_response(
    tmp_path: Path,
) -> None:
    run_dir = _create_rendered_run(tmp_path, page_count=19)

    first_response = _raw_chat_completion(
        "# Pages 1-8",
        response_id="chatcmpl-first-batch",
    )
    incomplete_response = _raw_chat_completion(
        "# Partial pages 9-16",
        response_id="chatcmpl-incomplete",
        finish_reason="length",
    )

    client = Mock()
    client.create_raw_chat_completion.side_effect = [
        first_response,
        incomplete_response,
    ]

    with pytest.raises(
        ValueError,
        match="did not finish successfully: length",
    ):
        convert_document_to_markdown(
            run_dir=run_dir,
            client=client,
            model="nuextract3",
        )

    conversion_path = run_dir / "document_conversion"

    assert (
        conversion_path / "nuextract3_raw_response_batch_0001.json"
    ).read_bytes() == first_response.body
    assert (
        conversion_path / "nuextract3_raw_response_batch_0002.json"
    ).read_bytes() == incomplete_response.body
    assert (conversion_path / "nuextract3_trace_batch_0001.json").is_file()
    assert not (conversion_path / "nuextract3_trace_batch_0002.json").exists()
    assert not (conversion_path / "nuextract3_raw_response_batch_0003.json").exists()
    assert not (conversion_path / "document.md").exists()

    conversion_status = load_run_status(run_dir).phases.document_conversion

    assert conversion_status.state == "failed"
    assert conversion_status.error is not None
    assert conversion_status.error.type == "ValueError"
    assert conversion_status.error.message == (
        "Document conversion failed during response parsing."
    )

    assert client.create_raw_chat_completion.call_count == 2


@pytest.mark.parametrize(
    "output_name",
    [
        "document.md",
        "nuextract3_raw_response_batch_0001.json",
        "nuextract3_trace_batch_0001.json",
    ],
)
def test_convert_document_to_markdown_rejects_existing_output(
    tmp_path: Path,
    output_name: str,
) -> None:
    run_dir = _create_rendered_run(tmp_path)

    conversion_path = run_dir / "document_conversion"
    conversion_path.mkdir()
    output_path = conversion_path / output_name
    existing_content = b"existing output"
    output_path.write_bytes(existing_content)

    client = Mock()

    with pytest.raises(
        FileExistsError,
        match=output_name,
    ):
        convert_document_to_markdown(
            run_dir=run_dir,
            client=client,
            model="nuextract3",
        )

    assert output_path.read_bytes() == existing_content

    conversion_status = load_run_status(run_dir).phases.document_conversion

    assert conversion_status.state == "pending"

    client.create_raw_chat_completion.assert_not_called()


def _create_rendered_run(tmp_path: Path, *, page_count: int = 1) -> Path:
    input_pdf = tmp_path / "source.pdf"

    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)

    with input_pdf.open("wb") as file:
        writer.write(file)

    run_dir = create_run(
        input_pdf=input_pdf,
        runs_root=tmp_path / "runs",
    )

    render_pdf_pages(run_dir)

    return run_dir


def _raw_chat_completion(
    markdown: str,
    *,
    response_id: str,
    finish_reason: str = "stop",
) -> RawChatCompletion:
    response_payload = {
        "id": response_id,
        "object": "chat.completion",
        "created": 1788253200,
        "model": "nuextract3",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": markdown,
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
        },
    }

    return RawChatCompletion(
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(response_payload).encode("utf-8"),
    )
