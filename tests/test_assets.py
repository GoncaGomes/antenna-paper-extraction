import json
from pathlib import Path

import pytest

from antenna_paper_extraction.assets import build_visual_catalog


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "run"
    (directory / "pages").mkdir(parents=True)
    (directory / "figures").mkdir()

    pages_manifest = {
        "schema_version": "1.0",
        "document_id": f"sha256:{'0' * 64}",
        "page_count": 3,
        "render_settings": {
            "renderer_version": "test",
        },
        "pages": [
            {
                "asset_id": f"page_{number:04d}",
                "page_number": number,
                "relative_path": f"pages/page_{number:04d}.png",
                "width_pixels": 100,
                "height_pixels": 100,
                "size_bytes": 1,
                "sha256": "0" * 64,
            }
            for number in range(1, 4)
        ],
    }

    (directory / "pages" / "pages.json").write_text(
        json.dumps(pages_manifest),
        encoding="utf-8",
    )
    _write_figures(directory, [])

    return directory


@pytest.fixture
def figure_entry() -> dict:
    return {
        "figure_id": "figure_8",
        "label": "Figure 8",
        "relative_path": "figures/figure_8.png",
        "caption": "Figure 8. Test caption.",
        "caption_source": "markdown",
        "association_method": "docling",
        "caption_recovery": None,
        "markdown_captions": ["Figure 8. Test caption."],
        "candidates": [
            {
                "docling_ref": "#/pictures/0",
                "caption_docling": "Fig. 8. Test caption.",
                "caption_refs": [],
                "positions": [{"page_no": 2}],
            }
        ],
        "unresolved_reason": None,
    }


def _write_figures(run_dir: Path, entries: list[dict]) -> None:
    manifest = {
        "schema_version": "1.0",
        "document_id": f"sha256:{'0' * 64}",
        "figures": entries,
    }

    (run_dir / "figures" / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def test_build_visual_catalog_returns_minimal_data_without_images(
    run_dir: Path,
    figure_entry: dict,
) -> None:
    _write_figures(run_dir, [figure_entry])

    catalog = build_visual_catalog(run_dir)

    assert catalog.model_dump(mode="json") == {
        "figures": [
            {
                "figure_id": "figure_8",
                "status": "available",
                "page_id": "page_0002",
            }
        ],
        "pages": [
            "page_0001",
            "page_0002",
            "page_0003",
        ],
    }
    assert list(run_dir.rglob("*.png")) == []


@pytest.mark.parametrize(
    ("caption_count", "candidate_count", "has_crop", "expected_status"),
    [
        (1, 1, True, "available"),
        (1, 1, False, "unresolved"),
        (0, 1, False, "unresolved"),
        (1, 0, False, "unresolved"),
        (2, 1, False, "ambiguous"),
        (1, 2, False, "ambiguous"),
        (2, 1, True, "ambiguous"),
    ],
    ids=[
        "materialized-crop",
        "crop-not-materialized",
        "missing-markdown-caption",
        "missing-candidate",
        "duplicate-captions",
        "multiple-candidates",
        "ambiguity-takes-precedence",
    ],
)
def test_build_visual_catalog_assigns_figure_status(
    run_dir: Path,
    figure_entry: dict,
    caption_count: int,
    candidate_count: int,
    has_crop: bool,
    expected_status: str,
) -> None:
    figure_entry["markdown_captions"] = ["Figure 8. Test caption."] * caption_count
    figure_entry["candidates"] = [
        {"positions": [{"page_no": 2}]} for _ in range(candidate_count)
    ]
    figure_entry["relative_path"] = "figures/figure_8.png" if has_crop else None
    _write_figures(run_dir, [figure_entry])

    catalog = build_visual_catalog(run_dir)

    assert catalog.figures[0].status == expected_status


@pytest.mark.parametrize(
    ("source_pages", "expected_page_id"),
    [
        ([[2]], "page_0002"),
        ([], None),
        ([[]], None),
        ([[1, 2]], None),
        ([[2], [2]], None),
        ([[99]], None),
    ],
    ids=[
        "unique-declared-page",
        "caption-without-candidate",
        "candidate-without-position",
        "multiple-positions",
        "multiple-candidates-on-same-page",
        "undeclared-page",
    ],
)
def test_build_visual_catalog_links_only_unambiguous_declared_pages(
    run_dir: Path,
    figure_entry: dict,
    source_pages: list[list[int]],
    expected_page_id: str | None,
) -> None:
    figure_entry["relative_path"] = None
    figure_entry["candidates"] = [
        {"positions": [{"page_no": number} for number in candidate_pages]}
        for candidate_pages in source_pages
    ]
    _write_figures(run_dir, [figure_entry])

    catalog = build_visual_catalog(run_dir)

    assert catalog.figures[0].page_id == expected_page_id


def test_build_visual_catalog_preserves_page_link_with_ambiguous_captions(
    run_dir: Path,
    figure_entry: dict,
) -> None:
    figure_entry["markdown_captions"] = [
        "Figure 8. First caption.",
        "Figure 8. Second caption.",
    ]
    figure_entry["relative_path"] = None
    _write_figures(run_dir, [figure_entry])

    catalog = build_visual_catalog(run_dir)

    assert catalog.figures[0].status == "ambiguous"
    assert catalog.figures[0].page_id == "page_0002"


def test_build_visual_catalog_sorts_figures_numerically(
    run_dir: Path,
    figure_entry: dict,
) -> None:
    entries = [
        {
            **figure_entry,
            "figure_id": f"figure_{number}",
            "label": f"Figure {number}",
            "caption": f"Figure {number}. Test caption.",
            "markdown_captions": [f"Figure {number}. Test caption."],
            "relative_path": f"figures/figure_{number}.png",
        }
        for number in (10, 2, 1)
    ]
    _write_figures(run_dir, entries)

    catalog = build_visual_catalog(run_dir)

    assert [entry.figure_id for entry in catalog.figures] == [
        "figure_1",
        "figure_2",
        "figure_10",
    ]
    assert catalog.pages == (
        "page_0001",
        "page_0002",
        "page_0003",
    )


def test_build_visual_catalog_keeps_pages_without_figures(
    run_dir: Path,
) -> None:
    catalog = build_visual_catalog(run_dir)

    assert catalog.figures == ()
    assert catalog.pages == (
        "page_0001",
        "page_0002",
        "page_0003",
    )


def test_build_visual_catalog_omits_entries_without_figure_id(
    run_dir: Path,
    figure_entry: dict,
) -> None:
    figure_entry["figure_id"] = None
    figure_entry["label"] = None
    figure_entry["relative_path"] = None
    _write_figures(run_dir, [figure_entry])

    original_manifest = (run_dir / "figures" / "manifest.json").read_bytes()

    catalog = build_visual_catalog(run_dir)

    assert catalog.figures == ()
    assert (run_dir / "figures" / "manifest.json").read_bytes() == original_manifest


def test_build_visual_catalog_rejects_duplicate_figure_ids(
    run_dir: Path,
    figure_entry: dict,
) -> None:
    _write_figures(run_dir, [figure_entry, figure_entry])

    with pytest.raises(
        ValueError,
        match="Duplicate figure identifier: figure_8",
    ):
        build_visual_catalog(run_dir)


@pytest.mark.parametrize(
    "relative_path",
    [
        "figures/manifest.json",
        "pages/pages.json",
    ],
)
def test_build_visual_catalog_rejects_manifest_symlink_outside_run(
    run_dir: Path,
    tmp_path: Path,
    relative_path: str,
) -> None:
    outside_manifest = tmp_path / "outside.json"
    outside_manifest.write_text("invalid JSON", encoding="utf-8")

    manifest_path = run_dir / relative_path
    manifest_path.unlink()

    try:
        manifest_path.symlink_to(outside_manifest)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symbolic links is unavailable.")

    with pytest.raises(ValueError, match="escapes the run directory"):
        build_visual_catalog(run_dir)
