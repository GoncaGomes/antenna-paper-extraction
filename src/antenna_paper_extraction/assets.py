import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from antenna_paper_extraction.pages import load_pages_manifest


class FigureCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    figure_id: str
    status: Literal["available", "unresolved", "ambiguous"]
    page_id: str | None


class VisualCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    figures: tuple[FigureCatalogEntry, ...]
    pages: tuple[str, ...]


def build_visual_catalog(run_dir: Path) -> VisualCatalog:
    run_dir = Path(run_dir).resolve()

    figure_manifest_path = run_dir / "figures" / "manifest.json"
    pages_manifest_path = run_dir / "pages" / "pages.json"

    for manifest_path in (figure_manifest_path, pages_manifest_path):
        if not manifest_path.resolve().is_relative_to(run_dir):
            raise ValueError("Visual manifest path escapes the run directory")

    pages_manifest = load_pages_manifest(run_dir)
    figure_manifest = json.loads(figure_manifest_path.read_text(encoding="utf-8"))

    page_ids_by_number = {
        page.page_number: page.asset_id for page in pages_manifest.pages
    }

    figures: list[FigureCatalogEntry] = []
    seen_figure_ids: set[str] = set()

    for entry in figure_manifest["figures"]:
        figure_id = entry["figure_id"]

        if figure_id is None:
            continue

        if figure_id in seen_figure_ids:
            raise ValueError(f"Duplicate figure identifier: {figure_id}")

        seen_figure_ids.add(figure_id)

        captions = entry["markdown_captions"]
        candidates = entry["candidates"]

        if len(captions) > 1 or len(candidates) > 1:
            status = "ambiguous"
        elif entry["relative_path"] is not None:
            status = "available"
        else:
            status = "unresolved"

        page_id = None

        if len(candidates) == 1:
            positions = candidates[0]["positions"]

            if len(positions) == 1:
                page_number = positions[0]["page_no"]
                page_id = page_ids_by_number.get(page_number)

        figures.append(
            FigureCatalogEntry(
                figure_id=figure_id,
                status=status,
                page_id=page_id,
            )
        )

    figures.sort(key=lambda figure: int(figure.figure_id.removeprefix("figure_")))

    return VisualCatalog(
        figures=tuple(figures),
        pages=tuple(page.asset_id for page in pages_manifest.pages),
    )
