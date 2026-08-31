import base64
import hashlib
from pathlib import Path

from antenna_paper_extraction.pages import PageAsset

DOCUMENT_CONVERSION_INSTRUCTION = (
    "Convert the following page images into one Markdown document "
    "in the provided order. Each PAGE_ID marker immediately "
    "precedes the image it identifies. Copy each marker exactly "
    "once into the output immediately before the Markdown "
    "transcribed from that image. Do not include this instruction "
    "in the output. Do not rename, omit, duplicate, or reorder "
    "the PAGE_ID markers."
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
