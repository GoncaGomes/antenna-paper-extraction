import json
from pathlib import Path

import pytest

from antenna_paper_extraction.assets import (
    AssetResolution,
    build_visual_catalog,
    resolve_visual_assets,
)


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


@pytest.fixture
def available_assets(
    run_dir: Path,
    figure_entry: dict,
) -> dict[str, bytes]:
    _write_figures(run_dir, [figure_entry])

    payloads = {
        "figure_8": b"synthetic figure bytes",
        "page_0001": b"synthetic first page bytes",
        "page_0002": b"synthetic second page bytes",
        "page_0003": b"synthetic third page bytes",
    }

    for asset_id, payload in payloads.items():
        directory = "figures" if asset_id.startswith("figure_") else "pages"
        (run_dir / directory / f"{asset_id}.png").write_bytes(payload)

    return payloads


@pytest.mark.parametrize(
    "asset_ids",
    [
        ("figure_8",),
        ("page_0002",),
        ("figure_8", "page_0002"),
        ("page_0002", "figure_8"),
        ("page_0003", "page_0001"),
    ],
    ids=[
        "figure",
        "page-despite-existing-crop",
        "mixed-figure-first",
        "mixed-page-first",
        "pages-in-requested-order",
    ],
)
def test_resolve_visual_assets_returns_requested_images_in_order(
    run_dir: Path,
    available_assets: dict[str, bytes],
    asset_ids: tuple[str, ...],
) -> None:
    results = resolve_visual_assets(
        run_dir,
        asset_ids,
        max_assets=len(asset_ids),
    )

    assert results == tuple(
        AssetResolution(
            asset_id=asset_id,
            status="available",
            media_type="image/png",
            image_bytes=available_assets[asset_id],
            reason=None,
        )
        for asset_id in asset_ids
    )


def test_resolve_visual_assets_reads_only_requested_images(
    run_dir: Path,
    available_assets: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_bytes = Path.read_bytes
    reads: list[Path] = []

    expected_paths = [
        (run_dir / "pages" / "page_0002.png").resolve(),
        (run_dir / "figures" / "figure_8.png").resolve(),
    ]

    def record_read(path: Path) -> bytes:
        assert path in expected_paths, f"Unexpected image read: {path}"
        reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", record_read)

    results = resolve_visual_assets(
        run_dir,
        ("page_0002", "figure_8"),
    )

    assert reads == expected_paths
    assert results[0].image_bytes == available_assets["page_0002"]
    assert results[1].image_bytes == available_assets["figure_8"]


@pytest.mark.parametrize(
    ("asset_ids", "max_assets", "message"),
    [
        ((), 6, "At least one asset"),
        (("figure_8", "figure_8"), 6, "Repeated asset identifiers"),
        (("figure_999",), 6, "Unknown visual asset"),
        (("../outside.png",), 6, "Unknown visual asset"),
        (("figure_8", "page_0002"), 1, "exceed the limit"),
        (("figure_8",), 0, "must be positive"),
        (("figure_8",), -1, "must be positive"),
        ("figure_8", 6, "tuple of strings"),
        ((8,), 6, "tuple of strings"),
    ],
)
def test_resolve_visual_assets_rejects_invalid_requests_before_image_reads(
    run_dir: Path,
    available_assets: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
    asset_ids: object,
    max_assets: object,
    message: str,
) -> None:
    def reject_read(path: Path) -> bytes:
        raise AssertionError(f"Invalid request attempted an image read: {path}")

    monkeypatch.setattr(Path, "read_bytes", reject_read)

    with pytest.raises(ValueError, match=message):
        resolve_visual_assets(
            run_dir,
            asset_ids,
            max_assets=max_assets,
        )


@pytest.mark.parametrize("max_assets", [1.5, True])
def test_resolve_visual_assets_rejects_non_integer_limit(
    run_dir: Path,
    max_assets: float | bool,
) -> None:
    with pytest.raises(
        TypeError,
        match="Maximum asset count must be an integer.",
    ):
        resolve_visual_assets(
            run_dir,
            ("figure_8",),
            max_assets=max_assets,
        )


@pytest.mark.parametrize(
    "figure_status",
    ["unresolved", "ambiguous"],
)
def test_resolve_visual_assets_reports_unavailable_figure_without_fallback(
    run_dir: Path,
    figure_entry: dict,
    available_assets: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
    figure_status: str,
) -> None:
    if figure_status == "unresolved":
        figure_entry["relative_path"] = None
        expected_reason = "Figure crop is not materialized."
    else:
        figure_entry["markdown_captions"] = [
            "Figure 8. First caption.",
            "Figure 8. Second caption.",
        ]
        expected_reason = "Figure association is ambiguous."

    _write_figures(run_dir, [figure_entry])

    def reject_read(path: Path) -> bytes:
        raise AssertionError(f"Unavailable figure triggered an image read: {path}")

    monkeypatch.setattr(Path, "read_bytes", reject_read)

    results = resolve_visual_assets(run_dir, ("figure_8",))

    assert results == (
        AssetResolution(
            asset_id="figure_8",
            status="unavailable",
            media_type=None,
            image_bytes=None,
            reason=expected_reason,
        ),
    )


@pytest.mark.parametrize(
    ("missing_id", "relative_path", "remaining_id"),
    [
        ("figure_8", "figures/figure_8.png", "page_0002"),
        ("page_0002", "pages/page_0002.png", "figure_8"),
    ],
)
def test_resolve_visual_assets_preserves_available_results_when_file_is_missing(
    run_dir: Path,
    available_assets: dict[str, bytes],
    missing_id: str,
    relative_path: str,
    remaining_id: str,
) -> None:
    (run_dir / relative_path).unlink()

    results = resolve_visual_assets(
        run_dir,
        (missing_id, remaining_id),
    )

    assert results == (
        AssetResolution(
            asset_id=missing_id,
            status="unavailable",
            media_type=None,
            image_bytes=None,
            reason="Asset file is missing or is not a regular file.",
        ),
        AssetResolution(
            asset_id=remaining_id,
            status="available",
            media_type="image/png",
            image_bytes=available_assets[remaining_id],
            reason=None,
        ),
    )


def test_resolve_visual_assets_reports_directory_as_unavailable(
    run_dir: Path,
    available_assets: dict[str, bytes],
) -> None:
    image_path = run_dir / "figures" / "figure_8.png"
    image_path.unlink()
    image_path.mkdir()

    results = resolve_visual_assets(run_dir, ("figure_8",))

    assert results == (
        AssetResolution(
            asset_id="figure_8",
            status="unavailable",
            media_type=None,
            image_bytes=None,
            reason="Asset file is missing or is not a regular file.",
        ),
    )


def test_resolve_visual_assets_preserves_other_results_after_read_failure(
    run_dir: Path,
    available_assets: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_bytes = Path.read_bytes
    figure_path = (run_dir / "figures" / "figure_8.png").resolve()

    def fail_figure_read(path: Path) -> bytes:
        if path == figure_path:
            raise PermissionError("Synthetic read failure.")

        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_figure_read)

    results = resolve_visual_assets(
        run_dir,
        ("figure_8", "page_0002"),
    )

    assert results == (
        AssetResolution(
            asset_id="figure_8",
            status="unavailable",
            media_type=None,
            image_bytes=None,
            reason="Asset could not be read (PermissionError).",
        ),
        AssetResolution(
            asset_id="page_0002",
            status="available",
            media_type="image/png",
            image_bytes=available_assets["page_0002"],
            reason=None,
        ),
    )


@pytest.mark.parametrize("path_kind", ["relative", "absolute"])
def test_resolve_visual_assets_rejects_escaping_path_before_any_image_read(
    run_dir: Path,
    tmp_path: Path,
    figure_entry: dict,
    available_assets: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
    path_kind: str,
) -> None:
    outside_image = tmp_path / "outside.png"
    outside_image.write_bytes(b"outside image")

    figure_entry["relative_path"] = (
        "../outside.png" if path_kind == "relative" else str(outside_image.resolve())
    )
    _write_figures(run_dir, [figure_entry])

    def reject_read(path: Path) -> bytes:
        raise AssertionError(f"Unsafe request attempted an image read: {path}")

    monkeypatch.setattr(Path, "read_bytes", reject_read)

    with pytest.raises(ValueError, match="escapes the run directory"):
        resolve_visual_assets(
            run_dir,
            ("page_0002", "figure_8"),
        )


def test_resolve_visual_assets_rejects_image_symlink_outside_run(
    run_dir: Path,
    tmp_path: Path,
    available_assets: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside_image = tmp_path / "outside.png"
    outside_image.write_bytes(b"outside image")

    figure_path = run_dir / "figures" / "figure_8.png"
    figure_path.unlink()

    try:
        figure_path.symlink_to(outside_image)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symbolic links is unavailable.")

    def reject_read(path: Path) -> bytes:
        raise AssertionError(f"Unsafe request attempted an image read: {path}")

    monkeypatch.setattr(Path, "read_bytes", reject_read)

    with pytest.raises(ValueError, match="escapes the run directory"):
        resolve_visual_assets(
            run_dir,
            ("page_0002", "figure_8"),
        )
