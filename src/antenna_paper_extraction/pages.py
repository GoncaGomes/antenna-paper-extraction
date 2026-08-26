import hashlib
import io
from importlib.metadata import version
from pathlib import Path
from typing import Literal

import pypdfium2 as pdfium
from pydantic import BaseModel, ConfigDict, Field

from antenna_paper_extraction.persistence import write_json, read_json
from antenna_paper_extraction.runs import sha256_file


class RenderingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    renderer_name: Literal["pypdfium2"] = "pypdfium2"
    renderer_version: str = Field(min_length=1)
    dpi: int = Field(default=200, gt=0)
    image_format: Literal["png"] = "png"
    color_space: Literal["RGB"] = "RGB"
    background_color: Literal["white"] = "white"
    draw_annotations: Literal[True] = True


class PageAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    asset_id: str = Field(pattern=r"^page_[0-9]{4,}$")
    page_number: int = Field(ge=1)
    relative_path: str
    media_type: Literal["image/png"] = "image/png"
    width_pixels: int = Field(gt=0)
    height_pixels: int = Field(gt=0)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PagesManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    document_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    render_settings: RenderingSettings
    pages: tuple[PageAsset, ...]


def render_pdf_pages(
    run_dir: Path,
    *,
    dpi: int = 200,
) -> PagesManifest:

    run_maifest = read_json(run_dir / "manifest.json")
    source_relative_path = run_maifest["source_pdf"]["relative_path"]
    source_pdf = run_dir / source_relative_path
    output_dir = run_dir / "pages"
    manifest_path = run_dir / "pages.json"

    _validate_source_pdf(source_pdf)

    if output_dir.exists() or manifest_path.exists():
        raise FileExistsError(
            f"Page rendering output already exists for run: {run_dir}"
        )

    render_settings = RenderingSettings(
        renderer_version=version("pypdfium2"),
        dpi=dpi,
    )

    document_id = f"sha256:{sha256_file(source_pdf)}"
    page_assets: list[PageAsset] = []

    with pdfium.PdfDocument(source_pdf) as pdf:
        page_count = len(pdf)

        if page_count == 0:
            raise ValueError("The source PDF does not contain any pages.")

        output_dir.mkdir()

        for page_index in range(page_count):
            page_number = page_index + 1
            asset_id = f"page_{page_number:04d}"
            output_file = output_dir / f"{asset_id}.png"

            page = pdf[page_index]

            try:
                image_bytes, width_pixels, height_pixels = _render_page_to_png(
                    page, dpi=dpi
                )
            finally:
                page.close()

            output_file.write_bytes(image_bytes)

            page_assets.append(
                PageAsset(
                    asset_id=asset_id,
                    page_number=page_number,
                    relative_path=output_file.relative_to(run_dir).as_posix(),
                    width_pixels=width_pixels,
                    height_pixels=height_pixels,
                    size_bytes=len(image_bytes),
                    sha256=hashlib.sha256(image_bytes).hexdigest(),
                )
            )

    pages_manifest = PagesManifest(
        document_id=document_id,
        page_count=page_count,
        render_settings=render_settings,
        pages=tuple(page_assets),
    )

    write_json(
        manifest_path,
        pages_manifest.model_dump(mode="json"),
    )

    return pages_manifest


def _validate_source_pdf(source_pdf: Path) -> None:
    if not source_pdf.exists():
        raise FileNotFoundError(f"Run source PDF does not exist: {source_pdf}")

    if not source_pdf.is_file():
        raise IsADirectoryError(f"Run source PDF path is not a file: {source_pdf}")


def _render_page_to_png(
    page: pdfium.PdfPage,
    *,
    dpi: int,
) -> tuple[bytes, int, int]:
    scale_factor = dpi / 72

    bitmap = page.render(
        scale=scale_factor,
        fill_color=(255, 255, 255, 255),
        draw_annots=True,
    )

    try:
        raw_image = bitmap.to_pil()

        try:
            image = raw_image.convert("RGB")
        finally:
            raw_image.close()
    finally:
        bitmap.close()

    try:
        width, height = image.size

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        return buffer.getvalue(), width, height
    finally:
        image.close()
