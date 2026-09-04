import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict

from antenna_paper_extraction.model_client import (
    OpenAICompatibleClient,
    RawChatCompletion,
)
from antenna_paper_extraction.pages import (
    PageAsset,
    load_pages_manifest,
)
from antenna_paper_extraction.persistence import (
    write_bytes,
    write_json,
)
from antenna_paper_extraction.runs import (
    PhaseFailure,
    RunManifest,
    load_run_status,
    mark_document_conversion_failed,
    mark_document_conversion_running,
    mark_document_conversion_succeeded,
)

DOCUMENT_CONVERSION_INSTRUCTION = (
    "Convert the following page images into one Markdown document "
    "in the provided order. Preserve the complete readable content, "
    "including headings, prose, tables, equations, figure and table "
    "captions, labels, symbols, units, footnotes, and references. "
    "Do not summarize, omit, interpret, or reorder the content."
)


class _ResponseMessage(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, strict=True)

    content: str


class _ResponseChoice(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, strict=True)

    index: int
    message: _ResponseMessage
    finish_reason: str | None


class _ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    model: str | None = None
    choices: list[_ResponseChoice]
    usage: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocumentResponse:
    markdown: str
    model: str | None
    finish_reason: str
    usage: dict[str, object] | None


class DocumentConversionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    requested_model: str
    temperature: float
    mode: Literal["markdown"]
    enable_thinking: bool
    http_status_code: int
    finish_reason: str
    usage: dict[str, object] | None
    model_latency_seconds: float


def parse_document_markdown_response(
    *,
    response: RawChatCompletion,
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

    return ParsedDocumentResponse(
        markdown=markdown,
        model=parsed_response.model,
        finish_reason=choice.finish_reason,
        usage=parsed_response.usage,
    )


def convert_document_to_markdown(
    *,
    run_dir: Path,
    client: OpenAICompatibleClient,
    model: str,
) -> Path:
    run_dir = Path(run_dir)

    run_manifest_path = run_dir / "manifest.json"
    run_manifest = RunManifest.model_validate_json(
        run_manifest_path.read_text(encoding="utf-8")
    )

    pages_manifest = load_pages_manifest(run_dir)
    run_status = load_run_status(run_dir)

    if run_status.run_id != run_manifest.run_id:
        raise ValueError("Run status identity does not match the run manifest")

    if run_status.phases.page_rendering.state != "succeeded":
        raise ValueError("Page rendering must succeed before document conversion")

    if pages_manifest.document_id != run_manifest.document_id:
        raise ValueError("Page manifest document identity does not match run manifest")

    raw_response_path = run_dir / "nuextract3_raw_response.json"
    document_path = run_dir / "document.md"
    trace_path = run_dir / "nuextract3_trace.json"

    existing_outputs = tuple(
        path for path in (raw_response_path, document_path, trace_path) if path.exists()
    )

    if existing_outputs:
        existing_names = ", ".join(path.name for path in existing_outputs)
        raise FileExistsError(
            f"Document conversion output already exists: {existing_names}"
        )

    temperature = 0.0
    mode: Literal["markdown"] = "markdown"
    enable_thinking = False

    mark_document_conversion_running(run_dir)

    failure_stage = "request preparation"

    try:
        messages = build_document_messages(
            run_dir=run_dir,
            pages=pages_manifest.pages,
        )

        failure_stage = "model request"
        request_started = perf_counter()

        response = client.create_raw_chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            extra_body={
                "chat_template_kwargs": {
                    "mode": mode,
                    "enable_thinking": enable_thinking,
                }
            },
        )

        model_latency_seconds = perf_counter() - request_started

        failure_stage = "raw response persistence"

        write_bytes(
            raw_response_path,
            response.body,
        )

        failure_stage = "response parsing"

        parsed_response = parse_document_markdown_response(
            response=response,
        )

        failure_stage = "trace persistence"

        trace = DocumentConversionTrace(
            requested_model=model,
            temperature=temperature,
            mode=mode,
            enable_thinking=enable_thinking,
            http_status_code=response.status_code,
            finish_reason=parsed_response.finish_reason,
            usage=parsed_response.usage,
            model_latency_seconds=model_latency_seconds,
        )

        write_json(
            trace_path,
            trace.model_dump(mode="json"),
        )

        failure_stage = "document persistence"

        write_bytes(
            document_path,
            parsed_response.markdown.encode("utf-8"),
        )

        failure_stage = "status update"

        mark_document_conversion_succeeded(run_dir)

    except Exception as error:
        failure = PhaseFailure(
            type=type(error).__name__,
            message=(f"Document conversion failed during {failure_stage}."),
        )

        mark_document_conversion_failed(
            run_dir,
            failure,
        )

        raise

    return document_path


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
