import re
import io
from dataclasses import dataclass
from html.parser import HTMLParser
from math import ceil, floor, isfinite
from pathlib import Path
from PIL import Image

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DoclingDocument,
    PictureItem,
)


@dataclass(frozen=True)
class FigureCaptionAssociation:
    label: str | None
    markdown_captions: tuple[str, ...]
    pictures: tuple[PictureItem, ...]
    unresolved_reason: str | None


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


def group_figure_candidates_by_label(
    document: DoclingDocument,
    candidates: list[PictureItem],
) -> tuple[dict[str, list[PictureItem]], list[PictureItem]]:
    grouped: dict[str, list[PictureItem]] = {}
    unrecognized: list[PictureItem] = []

    for picture in candidates:
        caption = picture.caption_text(document)
        label = extract_figure_label(caption)

        if label is None:
            unrecognized.append(picture)
            continue

        grouped.setdefault(label, []).append(picture)

    return grouped, unrecognized


def associate_figure_captions(
    markdown: str,
    document: DoclingDocument,
    candidates: list[PictureItem],
) -> list[FigureCaptionAssociation]:
    markdown_captions = extract_markdown_captions(markdown)

    markdown_by_label, unrecognized_captions = group_captions_by_label(
        markdown_captions
    )
    pictures_by_label, unrecognized_pictures = group_figure_candidates_by_label(
        document, candidates
    )

    associations: list[FigureCaptionAssociation] = []

    labels = dict.fromkeys([*markdown_by_label, *pictures_by_label])

    for label in labels:
        captions = markdown_by_label.get(label, [])
        pictures = pictures_by_label.get(label, [])

        reason = None

        if len(captions) != 1 or len(pictures) != 1:
            reason = (
                f"Expected one Markdown caption and one Docling candidate; "
                f"found {len(captions)} caption(s) and "
                f"{len(pictures)} candidate(s)."
            )

        associations.append(
            FigureCaptionAssociation(
                label=label,
                markdown_captions=tuple(captions),
                pictures=tuple(pictures),
                unresolved_reason=reason,
            )
        )

    for caption in unrecognized_captions:
        associations.append(
            FigureCaptionAssociation(
                label=None,
                markdown_captions=(caption,),
                pictures=(),
                unresolved_reason="Unrecognized Markdown figure label.",
            )
        )

    for picture in unrecognized_pictures:
        caption = picture.caption_text(document)

        reason = (
            "Missing Docling caption."
            if not caption.strip()
            else "Unrecognized Docling figure label."
        )

        associations.append(
            FigureCaptionAssociation(
                label=None,
                markdown_captions=(),
                pictures=(picture,),
                unresolved_reason=reason,
            )
        )

    return associations


def calculate_figure_crop_bounds(
    bbox: BoundingBox,
    page_size: tuple[float, float],
    image_size: tuple[int, int],
    *,
    margin_pt: float = 2.0,
) -> tuple[int, int, int, int]:
    page_width, page_height = page_size
    image_width, image_height = image_size

    values = (
        page_width,
        page_height,
        bbox.l,
        bbox.t,
        bbox.r,
        bbox.b,
        margin_pt,
    )

    if not all(isfinite(value) for value in values):
        raise ValueError("Page dimensions, crop coordinates and margin must be finite.")

    if page_width <= 0 or page_height <= 0:
        raise ValueError("Page dimensions must be positive.")

    if image_width <= 0 or image_height <= 0:
        raise ValueError("Rendered image dimensions must be positive.")

    if margin_pt < 0:
        raise ValueError("Crop margin must not be negative.")

    left = bbox.l
    right = bbox.r

    if bbox.coord_origin == CoordOrigin.BOTTOMLEFT:
        top = page_height - bbox.t
        bottom = page_height - bbox.b
    elif bbox.coord_origin == CoordOrigin.TOPLEFT:
        top = bbox.t
        bottom = bbox.b
    else:
        raise ValueError("Unsuported coordinate origin: {bbox.coord_origin}.")

    if left >= right or top >= bottom:
        raise ValueError("Figure region must have postive width and height.")

    scale_x = image_width / page_width
    scale_y = image_height / page_height

    bounds = (
        max(0, floor((left - margin_pt) * scale_x)),
        max(0, floor((top - margin_pt) * scale_y)),
        min(image_width, ceil((right + margin_pt) * scale_x)),
        min(image_height, ceil((bottom + margin_pt) * scale_y)),
    )
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError("Figure crop does not intersect the rendered page.")

    return bounds

def crop_figure_to_png(
    page_image: Image.Image,
    bbox: BoundingBox,
    page_size: tuple[float, float],
    *,
    margin_pt: float = 2.0,
) -> bytes:
    bounds = calculate_figure_crop_bounds(
        bbox=bbox,
        page_size=page_size,
        image_size=page_image.size,
        margin_pt=margin_pt,
    )

    with page_image.crop(bounds) as cropped_image:
        with cropped_image.convert("RGB") as rgb_image:
            with io.BytesIO() as buffer:
                rgb_image.save(buffer, format="PNG")
                return buffer.getvalue()