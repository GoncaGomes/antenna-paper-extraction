import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from antenna_paper_extraction.document import (
    DOCUMENT_CONVERSION_INSTRUCTION,
    build_document_messages,
    parse_document_markdown_response,
)
from antenna_paper_extraction.model_client import RawChatCompletion
from antenna_paper_extraction.pages import PageAsset


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
                    "type": "text",
                    "text": "<!-- PAGE_ID: page_0001 -->",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": ("data:image/png;base64,Zmlyc3QtcGFnZQ==")},
                },
                {
                    "type": "text",
                    "text": "<!-- PAGE_ID: page_0002 -->",
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
        expected_page_ids=("page_0001",),
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
            expected_page_ids=("page_0001",),
        )
