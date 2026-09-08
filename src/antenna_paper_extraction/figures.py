import re
from html.parser import HTMLParser
from pathlib import Path

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument, PictureItem


def extract_figure_label(caption: str) -> str | None:
    match = re.match(
        r"^(?:Figure|Fig\.?)\s+([0-9]+)(?=\s|[.:]|$)",
        caption.strip(),
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    return f"Figure {int(match.group(1))}"


class _FigureCaptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.captions: list[str] = []
        self._parts: list[str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ):
        if tag == "figcaption":
            if self._parts is not None:
                raise ValueError("Nested figure captions are not supported")

            self._parts = []

        elif tag == "br" and self._parts is not None:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "figcaption" and self._parts is not None:
            caption = "".join(self._parts).strip()
            self.captions.append(caption)
            self._parts = None

    def finish(self) -> list[str]:
        self.close()

        if self._parts is not None:
            raise ValueError("Unclosed figure caption in markdown")

        return self.captions


def extract_markdown_captions(markdown: str) -> list[str]:
    parser = _FigureCaptionParser()
    parser.feed(markdown)
    return parser.finish()


def group_captions_by_label(
    captions: list[str],
) -> tuple[dict[str, list[str]], list[str]]:
    grouped: dict[str, list[str]] = {}
    unrecognized: list[str] = []

    for caption in captions:
        label = extract_figure_label(caption)

        if label is None:
            unrecognized.append(caption)
        else:
            grouped.setdefault(label, []).append(caption)

    return grouped, unrecognized


def load_docling_document(pdf_path: Path) -> DoclingDocument:
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise IsADirectoryError(f"PDF path is not a file: {pdf_path}")

    pipeline_options = PdfPipelineOptions(
        images_scale=3.0,
        generate_picture_images=False,
        generate_page_images=False,
    )

    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            ),
        },
    )

    result = converter.convert(pdf_path)

    if result.status != ConversionStatus.SUCCESS:
        details = "; ".join(error.error_message for error in result.errors)
        raise RuntimeError(
            f"Docling conversion did not complete successfully: "
            f"{result.status.value}. {details}"
        )

    return result.document


def collect_figure_candidates(
    document: DoclingDocument,
) -> list[PictureItem]:
    candidates: list[PictureItem] = []

    for item, _level in document.iterate_items():
        if not isinstance(item, PictureItem):
            continue

        candidates.append(item)

    return candidates
