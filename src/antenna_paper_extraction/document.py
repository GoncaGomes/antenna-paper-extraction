import base64
import hashlib
import re

from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel, ConfigDict

from antenna_paper_extraction.pages import PageAsset
from antenna_paper_extraction.model_client import RawChatCompletion

DOCUMENT_CONVERSION_INSTRUCTION = (
    "Convert the following page images into one Markdown document "
    "in the provided order. Each PAGE_ID marker immediately "
    "precedes the image it identifies. Copy each marker exactly "
    "once into the output immediately before the Markdown "
    "transcribed from that image. Do not include this instruction "
    "in the output. Do not rename, omit, duplicate, or reorder "
    "the PAGE_ID markers."
)

PAGE_ID_PATTERN = re.compilere.compile(r"<!-- PAGE_ID: (page_[0-9]{4,}) -->")


class _ResponseMessage(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, strict=True)

    content: str


class _ResponseChoice(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, strict=True)

    index: int
    message: _ResponseMessage
    finish_reason: str | None


class _ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model: str | None = None
    choices: list[_ResponseChoice]
    usage: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocumentResponse:
    markdown: str
    model: str | None
    finish_reason: str
    usage: dict[str, object] | None


def parse_document_markdown_response(
    *,
    response: RawChatCompletion,
    expected_page_ids: tuple[str, ...],
) -> ParsedDocumentResponse:
    if not 200 <= response.status_code < 300:
        raise ValueError(
            f"NuExtract3 returned an unsuccessful HTTP status: {response.status_code}"
        )

    parsed_response = _ChatCompletionResponse.model_validate_json(response.body)

    if len(parsed_response.choices) != 1:
        raise ValueError("NuExtract3 response must contain exactly one choice.")

    choice = parsed_response.choices[0]

    if choice.finish_reason != "stop":
        raise ValueError(
            f"NuExtract3 response did not finish successfully: {choice.finish_reason}"
        )

    markdown = choice.message.content

    if not markdown.strip():
        raise ValueError("NuExtract3 returned empty Markdown content.")

    actual_page_ids = tuple(PAGE_ID_PATTERN.findall(markdown))

    if actual_page_ids != expected_page_ids:
        raise ValueError(f"NuExtract3 returned unexpected page IDs: {actual_page_ids}")

    return ParsedDocumentResponse(
        markdown=markdown,
        model=parsed_response.model,
        finish_reason=choice.finish_reason,
        usage=parsed_response.usage,
    )


def build_document_messages(
    run_dir: Path,
    pages: tuple[PageAsset, ...],
) -> list[dict[str, object]]:
    request_content: list[dict[str, object]] = [
        {
            "type": "text",
            "text": DOCUMENT_CONVERSION_INSTRUCTION,
        }
    ]

    for page in pages:
        page_bytes = _read_verified_page_bytes(
            run_dir=run_dir,
            page=page,
        )
        page_base64 = base64.b64encode(page_bytes).decode("ascii")

        request_content.extend(
            [
                {
                    "type": "text",
                    "text": f"<!-- PAGE_ID: {page.asset_id} -->",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (f"data:{page.media_type};base64,{page_base64}")
                    },
                },
            ]
        )

    return [
        {
            "role": "user",
            "content": request_content,
        }
    ]


def _read_verified_page_bytes(
    *,
    run_dir: Path,
    page: PageAsset,
) -> bytes:
    resolved_run_dir = run_dir.resolve()
    page_path = (resolved_run_dir / page.relative_path).resolve()

    if not page_path.is_relative_to(resolved_run_dir):
        raise ValueError(f"Page asset path escapes run directory: {page.relative_path}")

    if not page_path.exists():
        raise FileNotFoundError(f"Page asset does not exist: {page_path}")

    if not page_path.is_file():
        raise IsADirectoryError(f"Page asset path is not a file: {page_path}")

    page_bytes = page_path.read_bytes()

    if len(page_bytes) != page.size_bytes:
        raise ValueError(f"Page asset size does not match manifest: {page.asset_id}")

    page_sha256 = hashlib.sha256(page_bytes).hexdigest()

    if page_sha256 != page.sha256:
        raise ValueError(
            f"Page asset checksum does not match manifest: {page.asset_id}"
        )

    return page_bytes
