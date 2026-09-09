import io
import re
from contextlib import closing
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from math import ceil, floor, isfinite
from pathlib import Path

import pypdfium2 as pdfium
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DoclingDocument,
    PictureItem,
)
from PIL import Image

from antenna_paper_extraction.persistence import write_bytes
from antenna_paper_extraction.runs import RunManifest, sha256_file


@dataclass(frozen=True)
class FigureCaptionAssociation:
    label: str | None
    markdown_captions: tuple[str, ...]
    pictures: tuple[PictureItem, ...]
    unresolved_reason: str | None


@dataclass(frozen=True)
class FigureCropResult:
    association: FigureCaptionAssociation
    relative_path: str | None
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

    with (
        page_image.crop(bounds) as cropped_image,
        cropped_image.convert("RGB") as rgb_image,
        io.BytesIO() as buffer,
    ):
        rgb_image.save(buffer, format="PNG")
        return buffer.getvalue()


def _load_preserved_pdf(run_dir: Path) -> Path:
    run_dir = Path(run_dir).resolve()

    manifest = RunManifest.model_validate_json(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )

    pdf_path = (run_dir / manifest.source_pdf.relative_path).resolve()

    if not pdf_path.is_relative_to(run_dir / "input"):
        raise ValueError("Source PDF must be inside the run input directory.")

    if not pdf_path.exists():
        raise FileNotFoundError(f"Preserved PDF does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise IsADirectoryError(f"Preserved PDF path is not a file: {pdf_path}")

    source_sha256 = sha256_file(pdf_path)

    if source_sha256 != manifest.source_pdf.sha256:
        raise ValueError("Preserved PDF checksum does not match the run manifest.")

    if manifest.document_id != f"sha256:{source_sha256}":
        raise ValueError("Document identity does not match the preserved PDF.")

    return pdf_path


def _group_figure_crops_by_page(
    associations: list[FigureCaptionAssociation],
) -> tuple[dict[int, list[int]], list[FigureCropResult]]:
    by_page: dict[int, list[int]] = {}
    results: list[FigureCropResult] = []

    for index, association in enumerate(associations):
        reason = association.unresolved_reason

        if reason is None:
            if (
                association.label is None
                or len(association.markdown_captions) != 1
                or len(association.pictures) != 1
            ):
                reason = "Figure association is not unique."
            else:
                picture = association.pictures[0]

                if len(picture.prov) != 1:
                    reason = f"Expected one source region; found {len(picture.prov)}."
                else:
                    page_number = picture.prov[0].page_no
                    by_page.setdefault(page_number, []).append(index)

        results.append(
            FigureCropResult(
                association=association,
                relative_path=None,
                unresolved_reason=reason,
            )
        )

    return by_page, results


def render_run_figure_crops(
    run_dir: Path,
    associations: list[FigureCaptionAssociation],
    *,
    scale: float = 3.0,
    margin_pt: float = 2.0,
) -> list[FigureCropResult]:
    run_dir = Path(run_dir).resolve()

    if not isfinite(scale) or scale <= 0:
        raise ValueError("Rendering scale must be finite and positive.")

    if not isfinite(margin_pt) or margin_pt < 0:
        raise ValueError("Crop margin must be finite and non-negative.")

    pdf_path = _load_preserved_pdf(run_dir)
    output_dir = run_dir / "figures"

    if output_dir.exists():
        raise FileExistsError(f"Figure output already exists: {output_dir}")

    by_page, results = _group_figure_crops_by_page(associations)

    if not by_page:
        return results

    with pdfium.PdfDocument(pdf_path) as pdf:
        output_dir.mkdir(exist_ok=False)

        for page_number, indexes in sorted(by_page.items()):
            if not 1 <= page_number <= len(pdf):
                for index in indexes:
                    results[index] = replace(
                        results[index],
                        unresolved_reason=(
                            f"Source page {page_number} is outside the PDF."
                        ),
                    )
                continue

            with closing(pdf[page_number - 1]) as page:
                page_size = page.get_size()

                with (
                    closing(
                        page.render(
                            scale=scale,
                            fill_color=(255, 255, 255, 255),
                            draw_annots=True,
                        )
                    ) as bitmap,
                    bitmap.to_pil() as page_image,
                ):
                    for index in indexes:
                        association = results[index].association
                        picture = association.pictures[0]

                        try:
                            png_bytes = crop_figure_to_png(
                                page_image=page_image,
                                bbox=picture.prov[0].bbox,
                                page_size=page_size,
                                margin_pt=margin_pt,
                            )
                        except ValueError as error:
                            results[index] = replace(
                                results[index],
                                unresolved_reason=f"Invalid figure region: {error}",
                            )
                            continue

                        label = association.label

                        if label is None:
                            raise ValueError("Renderable figure has no label.")

                        figure_number = int(label.removeprefix("Figure "))
                        relative_path = f"figures/figure_{figure_number}.png"
                        output_path = run_dir / relative_path

                        if output_path.exists():
                            raise FileExistsError(
                                f"Figure file already exists: {output_path}"
                            )

                        write_bytes(output_path, png_bytes)

                        results[index] = replace(
                            results[index],
                            relative_path=relative_path,
                        )

    return results
