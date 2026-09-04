import hashlib
import io
from importlib.metadata import version
from pathlib import Path
from typing import Literal, Self

import pypdfium2 as pdfium
from pydantic import BaseModel, ConfigDict, Field, model_validator

from antenna_paper_extraction.persistence import write_bytes, write_json
from antenna_paper_extraction.runs import (
    PhaseFailure,
    RunManifest,
    mark_page_rendering_failed,
    mark_page_rendering_running,
    mark_page_rendering_succeeded,
    sha256_file,
)


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

    @model_validator(mode="after")
    def validate_page_consistency(self) -> Self:
        if len(self.pages) != self.page_count:
            raise ValueError("Page count does not match page asset count.")

        expected_page_numbers = tuple(range(1, self.page_count + 1))
        actual_page_numbers = tuple(page.page_number for page in self.pages)

        if actual_page_numbers != expected_page_numbers:
            raise ValueError(
                "Pages must be contiguous, one-based, and ordered by page_number."
            )

        for page in self.pages:
            expected_asset_id = f"page_{page.page_number:04d}"
            if page.asset_id != expected_asset_id:
                raise ValueError(
                    f"Page asset_id does not match page_number: {page.asset_id}"
                )
            expected_relative_path = f"pages/{expected_asset_id}.png"
            if page.relative_path != expected_relative_path:
                raise ValueError(
                    "Page relative_path does not match its canonical identity: "
                    f"{page.relative_path}"
                )

        return self


def load_pages_manifest(run_dir: Path) -> PagesManifest:
    manifest_path = run_dir / "pages" / "pages.json"
    return PagesManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def render_pdf_pages(
    run_dir: Path,
    *,
    dpi: int = 170,
) -> PagesManifest:

    mark_page_rendering_running(run_dir)

    try:
        run_manifest_path = run_dir / "manifest.json"
        run_manifest = RunManifest.model_validate_json(
            run_manifest_path.read_text(encoding="utf-8")
        )

        source_pdf = run_dir / run_manifest.source_pdf.relative_path
        output_dir = run_dir / "pages"
        pages_manifest_path = output_dir / "pages.json"

        _validate_source_pdf(source_pdf)

        source_sha256 = sha256_file(source_pdf)

        if source_sha256 != run_manifest.source_pdf.sha256:
            raise ValueError("Run source PDF checksum does not match manifest.")

        document_id = f"sha256:{source_sha256}"

        if document_id != run_manifest.document_id:
            raise ValueError("Run document identity does not match manifest.")

        if output_dir.exists() or pages_manifest_path.exists():
            raise FileExistsError(
                f"Page rendering output already exists for run: {run_dir}"
            )

        render_settings = RenderingSettings(
            renderer_version=version("pypdfium2"),
            dpi=dpi,
        )

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

                write_bytes(output_file, image_bytes)

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
            document_id=run_manifest.document_id,
            page_count=page_count,
            render_settings=render_settings,
            pages=tuple(page_assets),
        )

        write_json(
            pages_manifest_path,
            pages_manifest.model_dump(mode="json"),
        )

        mark_page_rendering_succeeded(run_dir)

    except Exception as e:
        failure = PhaseFailure(type=type(e).__name__, message=str(e))
        mark_page_rendering_failed(run_dir, failure)
        raise

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
