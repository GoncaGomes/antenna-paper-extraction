import json
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class AssetResolution:
    asset_id: str
    status: Literal["available", "unavailable"]
    media_type: Literal["image/png"] | None
    image_bytes: bytes | None
    reason: str | None


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


def resolve_visual_assets(
    run_dir: Path,
    asset_ids: tuple[str, ...],
    *,
    max_assets: int = 6,
) -> tuple[AssetResolution, ...]:
    if not isinstance(max_assets, int) or isinstance(max_assets, bool):
        raise TypeError("Maximum asset count must be an integer.")

    if max_assets < 1:
        raise ValueError("Maximum asset count must be positive.")

    if not isinstance(asset_ids, tuple) or not all(
        isinstance(asset_id, str) for asset_id in asset_ids
    ):
        raise ValueError("Asset identifiers must be a tuple of strings.")

    if not asset_ids:
        raise ValueError("At least one asset must be requested.")

    if len(asset_ids) > max_assets:
        raise ValueError(f"Requested assets exceed the limit of {max_assets}.")

    if len(set(asset_ids)) != len(asset_ids):
        raise ValueError("Repeated asset identifiers are not allowed.")

    run_dir = Path(run_dir).resolve()
    catalog = build_visual_catalog(run_dir)

    figure_states = {figure.figure_id: figure.status for figure in catalog.figures}
    declared_ids = set(figure_states) | set(catalog.pages)

    for asset_id in asset_ids:
        if asset_id not in declared_ids:
            raise ValueError(f"Unknown visual asset: {asset_id}")

    figure_manifest_path = _resolve_path_inside_run(
        run_dir,
        "figures/manifest.json",
    )
    _resolve_path_inside_run(run_dir, "pages/pages.json")

    figure_manifest = json.loads(figure_manifest_path.read_text(encoding="utf-8"))
    pages_manifest = load_pages_manifest(run_dir)

    declared_paths: dict[str, str | None] = {
        page.asset_id: page.relative_path for page in pages_manifest.pages
    }

    for entry in figure_manifest["figures"]:
        figure_id = entry["figure_id"]

        if figure_id is not None:
            declared_paths[figure_id] = entry["relative_path"]

    requested_paths: dict[str, Path | None] = {}

    for asset_id in asset_ids:
        relative_path = declared_paths[asset_id]
        requested_paths[asset_id] = (
            _resolve_path_inside_run(run_dir, relative_path)
            if relative_path is not None
            else None
        )

    results: list[AssetResolution] = []

    for asset_id in asset_ids:
        path = requested_paths[asset_id]
        figure_status = figure_states.get(asset_id)

        image_bytes = None
        reason = None

        if figure_status == "ambiguous":
            reason = "Figure association is ambiguous."
        elif figure_status == "unresolved" or path is None:
            reason = "Figure crop is not materialized."
        else:
            try:
                if not path.is_file():
                    reason = "Asset file is missing or is not a regular file."
                else:
                    image_bytes = path.read_bytes()
            except OSError as error:
                reason = f"Asset could not be read ({type(error).__name__})."

        results.append(
            AssetResolution(
                asset_id=asset_id,
                status=("available" if image_bytes is not None else "unavailable"),
                media_type="image/png" if image_bytes is not None else None,
                image_bytes=image_bytes,
                reason=reason,
            )
        )

    return tuple(results)


def _resolve_path_inside_run(run_dir: Path, relative_path: str) -> Path:
    path = (run_dir / relative_path).resolve()

    if not path.is_relative_to(run_dir):
        raise ValueError(f"Asset path escapes the run directory: {relative_path}")

    return path
