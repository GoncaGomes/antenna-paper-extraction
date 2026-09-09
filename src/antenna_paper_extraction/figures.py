import io
import re
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from importlib.metadata import version
from math import ceil, floor, isfinite
from pathlib import Path
from time import perf_counter

import pypdfium2 as pdfium
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    PictureItem,
    TextItem,
)
from PIL import Image

from antenna_paper_extraction.persistence import write_bytes, write_json
from antenna_paper_extraction.runs import (
    PhaseFailure,
    RunManifest,
    load_run_status,
    mark_figure_extraction_failed,
    mark_figure_extraction_running,
    mark_figure_extraction_succeeded,
    sha256_file,
)

DOCLING_IMAGES_SCALE = 3.0
MAX_CAPTION_DISTANCE_PT = 30.0
MIN_CAPTION_WIDTH_OVERLAP = 0.8


@dataclass(frozen=True)
class FigureCaptionRecovery:
    caption: TextItem
    distance_pt: float


@dataclass(frozen=True)
class FigureCaptionAssociation:
    label: str | None
    markdown_captions: tuple[str, ...]
    pictures: tuple[PictureItem, ...]
    unresolved_reason: str | None
    caption_recovery: FigureCaptionRecovery | None = None


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
        images_scale=DOCLING_IMAGES_SCALE,
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
    *,
    caption_recoveries: dict[str, FigureCaptionRecovery] | None = None,
) -> tuple[dict[str, list[PictureItem]], list[PictureItem]]:
    grouped: dict[str, list[PictureItem]] = {}
    unrecognized: list[PictureItem] = []
    recoveries = caption_recoveries if caption_recoveries is not None else {}

    for picture in candidates:
        caption = picture.caption_text(document)
        recovery = recoveries.get(picture.self_ref)

        if not caption.strip() and recovery is not None:
            caption = recovery.caption.text

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
    caption_recoveries = recover_figure_captions(document, candidates)

    pictures_by_label, unrecognized_pictures = group_figure_candidates_by_label(
        document,
        candidates,
        caption_recoveries=caption_recoveries,
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
                caption_recovery=(
                    caption_recoveries.get(pictures[0].self_ref)
                    if len(pictures) == 1
                    else None
                ),
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


def _build_figure_manifest_entries(
    results: list[FigureCropResult],
    document: DoclingDocument,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []

    for result in results:
        association = result.association
        unique_association = association.unresolved_reason is None

        figure_id = None
        if association.label is not None:
            number = association.label.removeprefix("Figure ")
            figure_id = f"figure_{number}"

        caption = None
        if unique_association:
            caption = association.markdown_captions[0]

        candidates = []

        for picture in association.pictures:
            candidates.append(
                {
                    "docling_ref": picture.self_ref,
                    "caption_docling": picture.caption_text(document),
                    "caption_refs": [reference.cref for reference in picture.captions],
                    "positions": [
                        provenance.model_dump(mode="json")
                        for provenance in picture.prov
                    ],
                }
            )

        recovery = association.caption_recovery
        recovery_details = None
        association_method = None

        if unique_association:
            association_method = (
                "geometric_recovery" if recovery is not None else "docling"
            )

        if recovery is not None:
            recovery_details = {
                "docling_ref": recovery.caption.self_ref,
                "text": recovery.caption.text,
                "positions": [
                    provenance.model_dump(mode="json")
                    for provenance in recovery.caption.prov
                ],
                "distance_pt": recovery.distance_pt,
            }

        entries.append(
            {
                "figure_id": figure_id,
                "label": association.label,
                "relative_path": result.relative_path,
                "caption": caption,
                "caption_source": "markdown" if caption is not None else None,
                "association_method": association_method,
                "caption_recovery": recovery_details,
                "markdown_captions": list(association.markdown_captions),
                "candidates": candidates,
                "unresolved_reason": result.unresolved_reason,
            }
        )

    return entries


def extract_figures(
    run_dir: Path,
    *,
    scale: float = 3.0,
    margin_pt: float = 2.0,
) -> Path:
    run_dir = Path(run_dir).resolve()

    run_manifest = RunManifest.model_validate_json(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    run_status = load_run_status(run_dir)

    if run_status.run_id != run_manifest.run_id:
        raise ValueError("Run status identity does not match the run manifest.")

    if run_status.phases.document_conversion.state != "succeeded":
        raise ValueError("Document conversion must succeed before figure extraction.")

    if run_status.phases.figure_extraction.state != "pending":
        raise ValueError("Figure extraction can only start from the pending state.")

    if not isfinite(scale) or scale <= 0:
        raise ValueError("Rendering scale must be finite and positive.")

    if not isfinite(margin_pt) or margin_pt < 0:
        raise ValueError("Crop margin must be finite and non-negative.")

    output_dir = run_dir / "figures"

    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Figure output already exists: {output_dir}")

    document_path = run_dir / "document_conversion" / "document.md"
    manifest_path = output_dir / "manifest.json"

    mark_figure_extraction_running(run_dir)
    failure_stage = "input validation"

    try:
        pdf_path = _load_preserved_pdf(run_dir)
        markdown = document_path.read_text(encoding="utf-8")

        if not markdown.strip():
            raise ValueError("Converted Markdown is empty.")

        failure_stage = "Docling processing"
        started = perf_counter()

        document = load_docling_document(pdf_path)

        docling_seconds = perf_counter() - started

        failure_stage = "caption association"
        started = perf_counter()

        candidates = collect_figure_candidates(document)
        associations = associate_figure_captions(
            markdown,
            document,
            candidates,
        )

        association_seconds = perf_counter() - started

        failure_stage = "figure rendering"
        started = perf_counter()

        results = render_run_figure_crops(
            run_dir,
            associations,
            scale=scale,
            margin_pt=margin_pt,
        )

        rendering_seconds = perf_counter() - started

        failure_stage = "manifest preparation"

        manifest = {
            "schema_version": "1.0",
            "document_id": run_manifest.document_id,
            "source_pdf": run_manifest.source_pdf.relative_path,
            "markdown_path": "document_conversion/document.md",
            "docling": {
                "version": version("docling"),
                "core_version": version("docling-core"),
                "images_scale": DOCLING_IMAGES_SCALE,
                "generate_picture_images": False,
                "generate_page_images": False,
            },
            "rendering": {
                "renderer": "pypdfium2",
                "version": version("pypdfium2"),
                "scale": scale,
                "margin_pt": margin_pt,
            },
            "timings_seconds": {
                "docling": docling_seconds,
                "association": association_seconds,
                "figure_rendering": rendering_seconds,
            },
            "figures": _build_figure_manifest_entries(results, document),
        }

        failure_stage = "manifest persistence"

        write_json(manifest_path, manifest)

        failure_stage = "status update"

        mark_figure_extraction_succeeded(run_dir)

    except Exception as error:
        failure = PhaseFailure(
            type=type(error).__name__,
            message=(f"Figure extraction failed during {failure_stage}: {error}"),
        )
        mark_figure_extraction_failed(run_dir, failure)
        raise

    return manifest_path


def calculate_caption_distance(
    caption: TextItem,
    picture: PictureItem,
) -> float | None:
    if len(caption.prov) != 1 or len(picture.prov) != 1:
        return None

    caption_position = caption.prov[0]
    picture_position = picture.prov[0]

    if caption_position.page_no != picture_position.page_no:
        return None

    caption_box = caption_position.bbox
    figure_box = picture_position.bbox

    if (
        caption_box.coord_origin != CoordOrigin.BOTTOMLEFT
        or figure_box.coord_origin != CoordOrigin.BOTTOMLEFT
    ):
        return None

    coordinates = (
        caption_box.l,
        caption_box.t,
        caption_box.r,
        caption_box.b,
        figure_box.l,
        figure_box.t,
        figure_box.r,
        figure_box.b,
    )

    if not all(isfinite(value) for value in coordinates):
        return None

    if (
        caption_box.l >= caption_box.r
        or caption_box.b >= caption_box.t
        or figure_box.l >= figure_box.r
        or figure_box.b >= figure_box.t
    ):
        return None

    distance = figure_box.b - caption_box.t

    if not 0 <= distance <= MAX_CAPTION_DISTANCE_PT:
        return None

    caption_width = caption_box.r - caption_box.l
    overlap = max(
        0.0,
        min(caption_box.r, figure_box.r) - max(caption_box.l, figure_box.l),
    )

    if overlap / caption_width < MIN_CAPTION_WIDTH_OVERLAP:
        return None

    return distance


def recover_figure_captions(
    document: DoclingDocument,
    candidates: list[PictureItem],
) -> dict[str, FigureCaptionRecovery]:
    captions = [
        text
        for text in document.texts
        if text.label == DocItemLabel.CAPTION
        and extract_figure_label(text.text) is not None
    ]

    label_counts = Counter(extract_figure_label(caption.text) for caption in captions)

    existing_labels = {
        extract_figure_label(picture.caption_text(document)) for picture in candidates
    }
    linked_caption_refs = {
        reference.cref for picture in candidates for reference in picture.captions
    }

    pairs: list[tuple[TextItem, PictureItem, float]] = []

    for caption in captions:
        for picture in candidates:
            distance = calculate_caption_distance(caption, picture)

            if distance is not None:
                pairs.append((caption, picture, distance))

    caption_counts = Counter(caption.self_ref for caption, _picture, _distance in pairs)
    picture_counts = Counter(picture.self_ref for _caption, picture, _distance in pairs)

    recoveries: dict[str, FigureCaptionRecovery] = {}

    for caption, picture, distance in pairs:
        label = extract_figure_label(caption.text)

        if picture.captions or picture.caption_text(document).strip():
            continue

        if caption.self_ref in linked_caption_refs:
            continue

        if label in existing_labels:
            continue

        if (
            label_counts[label] != 1
            or caption_counts[caption.self_ref] != 1
            or picture_counts[picture.self_ref] != 1
        ):
            continue

        recoveries[picture.self_ref] = FigureCaptionRecovery(
            caption=caption,
            distance_pt=distance,
        )

    return recoveries
