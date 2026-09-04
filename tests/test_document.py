import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter

from antenna_paper_extraction.document import (
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
    markdown = "<!-- PAGE_ID: page_0001 -->\n# Test document"

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

    markdown = "<!-- PAGE_ID: page_0001 -->\n# Test document"

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

    assert document_path == run_dir / "document.md"
    assert document_path.read_text(encoding="utf-8") == markdown

    assert (run_dir / "nuextract3_raw_response.json").read_bytes() == (
        raw_response_body
    )

    trace = json.loads((run_dir / "nuextract3_trace.json").read_text(encoding="utf-8"))

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

    assert not (run_dir / "nuextract3_raw_response.json").exists()
    assert not (run_dir / "document.md").exists()

    assert client.create_raw_chat_completion.call_count == 1


def test_convert_document_to_markdown_preserves_incomplete_raw_response(
    tmp_path: Path,
) -> None:
    run_dir = _create_rendered_run(tmp_path)

    response_payload = {
        "id": "chatcmpl-incomplete",
        "object": "chat.completion",
        "created": 1788253200,
        "model": "nuextract3",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "<!-- PAGE_ID: page_0001 -->\n# Partial document",
                },
                "finish_reason": "length",
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
        },
    }

    raw_response_body = json.dumps(response_payload).encode("utf-8")

    client = Mock()
    client.create_raw_chat_completion.return_value = RawChatCompletion(
        status_code=200,
        headers={"content-type": "application/json"},
        body=raw_response_body,
    )

    with pytest.raises(
        ValueError,
        match="did not finish successfully: length",
    ):
        convert_document_to_markdown(
            run_dir=run_dir,
            client=client,
            model="nuextract3",
        )

    assert (run_dir / "nuextract3_raw_response.json").read_bytes() == (
        raw_response_body
    )
    assert not (run_dir / "document.md").exists()

    conversion_status = load_run_status(run_dir).phases.document_conversion

    assert conversion_status.state == "failed"
    assert conversion_status.error is not None
    assert conversion_status.error.type == "ValueError"
    assert conversion_status.error.message == (
        "Document conversion failed during response parsing."
    )

    assert client.create_raw_chat_completion.call_count == 1


def test_convert_document_to_markdown_rejects_existing_output(
    tmp_path: Path,
) -> None:
    run_dir = _create_rendered_run(tmp_path)

    raw_response_path = run_dir / "nuextract3_raw_response.json"
    existing_content = b"existing raw response"
    raw_response_path.write_bytes(existing_content)

    client = Mock()

    with pytest.raises(
        FileExistsError,
        match="nuextract3_raw_response.json",
    ):
        convert_document_to_markdown(
            run_dir=run_dir,
            client=client,
            model="nuextract3",
        )

    assert raw_response_path.read_bytes() == existing_content

    conversion_status = load_run_status(run_dir).phases.document_conversion

    assert conversion_status.state == "pending"

    client.create_raw_chat_completion.assert_not_called()


def _create_rendered_run(tmp_path: Path) -> Path:
    input_pdf = tmp_path / "source.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)

    with input_pdf.open("wb") as file:
        writer.write(file)

    run_dir = create_run(
        input_pdf=input_pdf,
        runs_root=tmp_path / "runs",
    )

    render_pdf_pages(run_dir)

    return run_dir
