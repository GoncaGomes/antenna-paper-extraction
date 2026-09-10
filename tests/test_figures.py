import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pypdfium2 as pdfium
import pytest
from docling.datamodel.base_models import ConversionStatus
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    PictureItem,
    ProvenanceItem,
    TableData,
    TextItem,
)
from PIL import Image
from pypdf import PdfWriter

from antenna_paper_extraction import figures, runs
from antenna_paper_extraction.figures import (
    extract_figure_label,
    extract_markdown_captions,
    group_captions_by_label,
)
from antenna_paper_extraction.runs import create_run


@pytest.mark.parametrize(
    ("caption", "expected"),
    [
        ("Fig. 8. Radiation patterns.", "Figure 8"),
        ("Fig 8: Radiation patterns.", "Figure 8"),
        ("  FIGURE 08 Radiation patterns.  ", "Figure 8"),
        ("Figure 8", "Figure 8"),
        ("Fig. 8a. Radiation pattern.", None),
        ("See Fig. 8 for the radiation patterns.", None),
        ("Table 8. Antenna dimensions.", None),
        ("", None),
    ],
)
def test_extract_figure_label(
    caption: str,
    expected: str | None,
) -> None:
    assert extract_figure_label(caption) == expected


def test_extract_markdown_captions_reads_only_figcaption_text() -> None:
    markdown = """
# Results

See Fig. 8 for the radiation patterns.

<img src="img_7.png" alt="Generated image description">

<figcaption>Fig. 8. Measured <b>radiation patterns</b>.</figcaption>
<figcaption>Figure 7: Simulated &amp; measured.<br>At 2.4 GHz.</figcaption>
"""

    captions = extract_markdown_captions(markdown)

    assert captions == [
        "Fig. 8. Measured radiation patterns.",
        "Figure 7: Simulated & measured.\nAt 2.4 GHz.",
    ]


def test_extract_markdown_captions_returns_empty_list_without_figcaptions() -> None:
    markdown = "# Results\n\nSee Fig. 8 for the radiation patterns."

    assert extract_markdown_captions(markdown) == []


@pytest.mark.parametrize(
    ("markdown", "message"),
    [
        (
            "<figcaption>Fig. 1. Antenna geometry.",
            "Unclosed figure caption in markdown",
        ),
        (
            "<figcaption>Fig. 1. <figcaption>Fig. 2.</figcaption></figcaption>",
            "Nested figure captions are not supported",
        ),
    ],
)
def test_extract_markdown_captions_rejects_invalid_caption_structure(
    markdown: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        extract_markdown_captions(markdown)


def test_group_captions_preserves_duplicates_and_unrecognized_text() -> None:
    markdown = """
<figcaption>Fig. 8. First caption.</figcaption>
<figcaption>Figure 7: Another caption.</figcaption>
<figcaption>Figure 8: Second caption.</figcaption>
<figcaption>Antenna photograph.</figcaption>
"""

    captions = extract_markdown_captions(markdown)

    grouped, unrecognized = group_captions_by_label(captions)

    assert grouped == {
        "Figure 8": [
            "Fig. 8. First caption.",
            "Figure 8: Second caption.",
        ],
        "Figure 7": [
            "Figure 7: Another caption.",
        ],
    }
    assert unrecognized == ["Antenna photograph."]


@pytest.fixture
def fake_docling_converter(monkeypatch: pytest.MonkeyPatch) -> Mock:
    converter = Mock()

    monkeypatch.setattr(
        figures,
        "DocumentConverter",
        Mock(return_value=converter),
    )

    return converter


def test_load_docling_document_returns_successful_document(
    tmp_path: Path,
    fake_docling_converter: Mock,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"synthetic input")

    expected_document = DoclingDocument(name="paper")

    fake_docling_converter.convert.return_value = SimpleNamespace(
        status=ConversionStatus.SUCCESS,
        document=expected_document,
        errors=[],
    )

    document = figures.load_docling_document(pdf_path)

    assert document is expected_document
    fake_docling_converter.convert.assert_called_once_with(pdf_path)


@pytest.mark.parametrize(
    "status",
    [
        ConversionStatus.PARTIAL_SUCCESS,
        ConversionStatus.FAILURE,
    ],
)
def test_load_docling_document_rejects_unsuccessful_result(
    tmp_path: Path,
    fake_docling_converter: Mock,
    status: ConversionStatus,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"synthetic input")

    fake_docling_converter.convert.return_value = SimpleNamespace(
        status=status,
        document=DoclingDocument(name="partial"),
        errors=[SimpleNamespace(error_message="Page 2 could not be processed.")],
    )

    with pytest.raises(RuntimeError) as exception:
        figures.load_docling_document(pdf_path)

    message = str(exception.value)

    assert status.value in message
    assert "Page 2 could not be processed." in message


def test_load_docling_document_propagates_converter_exception(
    tmp_path: Path,
    fake_docling_converter: Mock,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"synthetic input")

    error = RuntimeError("Layout inference failed.")
    fake_docling_converter.convert.side_effect = error

    with pytest.raises(RuntimeError) as exception:
        figures.load_docling_document(pdf_path)

    assert exception.value is error


def test_load_docling_document_rejects_missing_file(
    tmp_path: Path,
    fake_docling_converter: Mock,
) -> None:
    pdf_path = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError, match="PDF does not exist"):
        figures.load_docling_document(pdf_path)

    fake_docling_converter.convert.assert_not_called()


def test_load_docling_document_rejects_directory(
    tmp_path: Path,
    fake_docling_converter: Mock,
) -> None:
    with pytest.raises(IsADirectoryError, match="PDF path is not a file"):
        figures.load_docling_document(tmp_path)

    fake_docling_converter.convert.assert_not_called()


def test_collect_figure_candidates_preserves_caption_and_position() -> None:
    document = DoclingDocument(name="synthetic")

    document.add_text(
        label=DocItemLabel.TEXT,
        text="The antenna is shown in Fig. 8.",
    )

    caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="Fig. 8. Antenna geometry.",
    )

    position = ProvenanceItem(
        page_no=4,
        bbox=BoundingBox(
            l=50.0,
            t=700.0,
            r=250.0,
            b=500.0,
            coord_origin=CoordOrigin.BOTTOMLEFT,
        ),
        charspan=(0, 0),
    )

    captioned_picture = document.add_picture(
        caption=caption,
        prov=position,
    )

    document.add_table(data=TableData())

    uncaptioned_picture = document.add_picture()

    candidates = figures.collect_figure_candidates(document)

    assert len(candidates) == 2
    assert candidates[0] is captioned_picture
    assert candidates[1] is uncaptioned_picture

    assert candidates[0].caption_text(document) == ("Fig. 8. Antenna geometry.")
    assert candidates[0].captions == [caption.get_ref()]
    assert candidates[0].prov == [position]

    assert candidates[1].caption_text(document) == ""
    assert candidates[1].captions == []
    assert candidates[1].prov == []


def _add_picture_with_caption(
    document: DoclingDocument,
    text: str,
) -> PictureItem:
    caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text=text,
    )

    return document.add_picture(caption=caption)


def test_associate_figure_captions_matches_labels_instead_of_picture_order() -> None:
    document = DoclingDocument(name="synthetic")

    picture_8 = _add_picture_with_caption(
        document,
        "Fig. 8. Original Docling caption for eight.",
    )
    picture_7 = _add_picture_with_caption(
        document,
        "Fig. 7. Original Docling caption for seven.",
    )

    markdown = """
<figcaption>Figure 7: Markdown caption for seven.</figcaption>
<figcaption>Figure 8: Markdown caption for eight.</figcaption>
"""

    original_document = document.model_dump()
    candidates = figures.collect_figure_candidates(document)

    associations = figures.associate_figure_captions(
        markdown,
        document,
        candidates,
    )

    assert len(associations) == 2

    association_7, association_8 = associations

    assert association_7.label == "Figure 7"
    assert association_7.markdown_captions == ("Figure 7: Markdown caption for seven.",)
    assert len(association_7.pictures) == 1
    assert association_7.pictures[0] is picture_7
    assert association_7.unresolved_reason is None

    assert association_8.label == "Figure 8"
    assert association_8.markdown_captions == ("Figure 8: Markdown caption for eight.",)
    assert len(association_8.pictures) == 1
    assert association_8.pictures[0] is picture_8
    assert association_8.unresolved_reason is None

    assert document.model_dump() == original_document


@pytest.mark.parametrize(
    ("caption_count", "picture_count"),
    [
        (1, 0),
        (0, 1),
        (2, 1),
        (1, 2),
    ],
)
def test_associate_figure_captions_preserves_non_unique_matches(
    caption_count: int,
    picture_count: int,
) -> None:
    document = DoclingDocument(name="synthetic")

    pictures = [
        _add_picture_with_caption(
            document,
            "Fig. 8. Original Docling caption.",
        )
        for _ in range(picture_count)
    ]

    markdown_caption = "Figure 8: Markdown caption."
    markdown = "\n".join(
        f"<figcaption>{markdown_caption}</figcaption>" for _ in range(caption_count)
    )

    associations = figures.associate_figure_captions(
        markdown,
        document,
        pictures,
    )

    assert len(associations) == 1

    association = associations[0]

    assert association.label == "Figure 8"
    assert association.markdown_captions == (markdown_caption,) * caption_count
    assert association.pictures == tuple(pictures)
    assert association.unresolved_reason is not None
    assert association.unresolved_reason.strip()


def test_associate_figure_captions_keeps_unrecognized_items_separate() -> None:
    document = DoclingDocument(name="synthetic")

    uncaptioned_picture = document.add_picture()
    unrecognized_picture = _add_picture_with_caption(
        document,
        "Antenna photograph.",
    )

    markdown = """
<figcaption>Prototype photograph.</figcaption>
"""

    associations = figures.associate_figure_captions(
        markdown,
        document,
        [uncaptioned_picture, unrecognized_picture],
    )

    assert len(associations) == 3

    markdown_item, missing_caption_item, unknown_label_item = associations

    assert markdown_item.label is None
    assert markdown_item.markdown_captions == ("Prototype photograph.",)
    assert markdown_item.pictures == ()
    assert markdown_item.unresolved_reason == ("Unrecognized Markdown figure label.")

    assert missing_caption_item.label is None
    assert missing_caption_item.markdown_captions == ()
    assert missing_caption_item.pictures == (uncaptioned_picture,)
    assert missing_caption_item.unresolved_reason == ("Missing Docling caption.")

    assert unknown_label_item.label is None
    assert unknown_label_item.markdown_captions == ()
    assert unknown_label_item.pictures == (unrecognized_picture,)
    assert unknown_label_item.unresolved_reason == (
        "Unrecognized Docling figure label."
    )


@pytest.mark.parametrize(
    ("origin", "top", "bottom"),
    [
        (CoordOrigin.TOPLEFT, 20.0, 100.0),
        (CoordOrigin.BOTTOMLEFT, 180.0, 100.0),
    ],
)
def test_calculate_figure_crop_bounds_handles_coordinate_origins(
    origin: CoordOrigin,
    top: float,
    bottom: float,
) -> None:
    bbox = BoundingBox(
        l=10.0,
        t=top,
        r=60.0,
        b=bottom,
        coord_origin=origin,
    )

    bounds = figures.calculate_figure_crop_bounds(
        bbox=bbox,
        page_size=(100.0, 200.0),
        image_size=(300, 600),
        margin_pt=2.0,
    )

    assert bounds == (24, 54, 186, 306)


def test_calculate_figure_crop_bounds_rounds_outward() -> None:
    bbox = BoundingBox(
        l=10.2,
        t=20.4,
        r=60.6,
        b=100.8,
        coord_origin=CoordOrigin.TOPLEFT,
    )

    bounds = figures.calculate_figure_crop_bounds(
        bbox=bbox,
        page_size=(100.0, 200.0),
        image_size=(301, 599),
        margin_pt=2.0,
    )

    assert bounds == (24, 55, 189, 308)


@pytest.mark.parametrize(
    ("margin_pt", "message"),
    [
        (-1.0, "must not be negative"),
        (float("nan"), "must be finite"),
    ],
)
def test_calculate_figure_crop_bounds_rejects_invalid_margin(
    margin_pt: float,
    message: str,
) -> None:
    bbox = BoundingBox(
        l=10.0,
        t=20.0,
        r=60.0,
        b=100.0,
        coord_origin=CoordOrigin.TOPLEFT,
    )

    with pytest.raises(ValueError, match=message):
        figures.calculate_figure_crop_bounds(
            bbox=bbox,
            page_size=(100.0, 200.0),
            image_size=(300, 600),
            margin_pt=margin_pt,
        )


def test_calculate_figure_crop_bounds_rejects_region_outside_page() -> None:
    bbox = BoundingBox(
        l=120.0,
        t=20.0,
        r=140.0,
        b=60.0,
        coord_origin=CoordOrigin.TOPLEFT,
    )

    with pytest.raises(ValueError, match="does not intersect"):
        figures.calculate_figure_crop_bounds(
            bbox=bbox,
            page_size=(100.0, 200.0),
            image_size=(300, 600),
            margin_pt=2.0,
        )


def test_crop_figure_to_png_preserves_pixels_and_source_image() -> None:
    bbox = BoundingBox(
        l=2.0,
        t=3.0,
        r=7.0,
        b=8.0,
        coord_origin=CoordOrigin.TOPLEFT,
    )

    with Image.new("RGBA", (20, 30), (255, 255, 255, 255)) as page_image:
        page_image.putpixel((4, 6), (255, 0, 0, 255))
        page_image.putpixel((13, 15), (0, 0, 255, 255))

        original_pixels = page_image.tobytes()

        png_bytes = figures.crop_figure_to_png(
            page_image=page_image,
            bbox=bbox,
            page_size=(10.0, 15.0),
            margin_pt=0.0,
        )

        assert page_image.tobytes() == original_pixels

    with io.BytesIO(png_bytes) as buffer, Image.open(buffer) as cropped_image:
        assert cropped_image.format == "PNG"
        assert cropped_image.mode == "RGB"
        assert cropped_image.size == (10, 10)

        assert cropped_image.getpixel((0, 0)) == (255, 0, 0)
        assert cropped_image.getpixel((9, 9)) == (0, 0, 255)
        assert cropped_image.getpixel((5, 5)) == (255, 255, 255)


def _create_figure_rendering_run(tmp_path: Path) -> Path:
    source_pdf = tmp_path / "paper.pdf"

    with PdfWriter() as writer:
        for width in (100, 120, 140):
            writer.add_blank_page(width=width, height=200)

        with source_pdf.open("wb") as output:
            writer.write(output)

    run_dir = create_run(source_pdf, tmp_path / "runs")
    source_pdf.unlink()

    return run_dir


def _make_render_association(
    document: DoclingDocument,
    number: int,
    page_number: int = 1,
) -> figures.FigureCaptionAssociation:
    picture = _add_picture_with_caption(
        document,
        f"Fig. {number}. Original Docling caption.",
    )

    picture.prov.append(
        ProvenanceItem(
            page_no=page_number,
            bbox=BoundingBox(
                l=10.0,
                t=20.0,
                r=40.0,
                b=60.0,
                coord_origin=CoordOrigin.TOPLEFT,
            ),
            charspan=(0, 0),
        )
    )

    return figures.FigureCaptionAssociation(
        label=f"Figure {number}",
        markdown_captions=(f"Figure {number}: Markdown caption.",),
        pictures=(picture,),
        unresolved_reason=None,
    )


def test_render_run_figure_crops_reuses_pages_and_preserves_associations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _create_figure_rendering_run(tmp_path)
    document = DoclingDocument(name="synthetic")

    associations = [
        _make_render_association(document, 8, page_number=2),
        _make_render_association(document, 7, page_number=1),
        _make_render_association(document, 9, page_number=1),
    ]

    rendered_page_sizes: list[tuple[float, float]] = []
    original_render = pdfium.PdfPage.render

    def track_render(
        page: pdfium.PdfPage,
        **kwargs: object,
    ) -> pdfium.PdfBitmap:
        rendered_page_sizes.append(page.get_size())
        return original_render(page, **kwargs)

    monkeypatch.setattr(pdfium.PdfPage, "render", track_render)

    results = figures.render_run_figure_crops(run_dir, associations)

    assert rendered_page_sizes == [
        (100.0, 200.0),
        (120.0, 200.0),
    ]
    assert not (run_dir / "pages").exists()

    assert [result.relative_path for result in results] == [
        "figures/figure_8.png",
        "figures/figure_7.png",
        "figures/figure_9.png",
    ]

    for result, association in zip(results, associations, strict=True):
        assert result.association is association
        assert result.unresolved_reason is None
        assert result.relative_path is not None

        with Image.open(run_dir / result.relative_path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGB"
            assert image.size == (102, 132)


@pytest.mark.parametrize(
    ("problem", "expected_reason"),
    [
        ("missing_region", "Expected one source region"),
        ("multiple_regions", "Expected one source region"),
        ("unknown_page", "Source page 4 is outside the PDF"),
        ("outside_page", "Invalid figure region"),
    ],
)
def test_render_run_figure_crops_preserves_unrenderable_figures(
    tmp_path: Path,
    problem: str,
    expected_reason: str,
) -> None:
    run_dir = _create_figure_rendering_run(tmp_path)
    document = DoclingDocument(name="synthetic")

    valid = _make_render_association(document, 1)
    problematic = _make_render_association(document, 2)
    picture = problematic.pictures[0]

    if problem == "missing_region":
        picture.prov.clear()
    elif problem == "multiple_regions":
        picture.prov.append(picture.prov[0])
    elif problem == "unknown_page":
        picture.prov[0].page_no = 4
    elif problem == "outside_page":
        picture.prov[0].bbox = BoundingBox(
            l=200.0,
            t=20.0,
            r=240.0,
            b=60.0,
            coord_origin=CoordOrigin.TOPLEFT,
        )

    results = figures.render_run_figure_crops(
        run_dir,
        [valid, problematic],
    )

    assert len(results) == 2

    assert results[0].relative_path == "figures/figure_1.png"
    assert results[0].unresolved_reason is None
    assert (run_dir / "figures" / "figure_1.png").is_file()

    assert results[1].association is problematic
    assert results[1].relative_path is None
    assert results[1].unresolved_reason is not None
    assert expected_reason in results[1].unresolved_reason
    assert not (run_dir / "figures" / "figure_2.png").exists()


def test_render_run_figure_crops_preserves_unresolved_association(
    tmp_path: Path,
) -> None:
    run_dir = _create_figure_rendering_run(tmp_path)

    association = figures.FigureCaptionAssociation(
        label="Figure 8",
        markdown_captions=("Figure 8: Markdown caption.",),
        pictures=(),
        unresolved_reason="No Docling candidate.",
    )

    results = figures.render_run_figure_crops(run_dir, [association])

    assert len(results) == 1
    assert results[0].association is association
    assert results[0].relative_path is None
    assert results[0].unresolved_reason == "No Docling candidate."
    assert not (run_dir / "figures").exists()


def test_render_run_figure_crops_rejects_existing_output(
    tmp_path: Path,
) -> None:
    run_dir = _create_figure_rendering_run(tmp_path)
    document = DoclingDocument(name="synthetic")
    association = _make_render_association(document, 1)

    output_dir = run_dir / "figures"
    output_dir.mkdir()

    existing_file = output_dir / "keep.txt"
    existing_file.write_text("existing output", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Figure output already exists"):
        figures.render_run_figure_crops(run_dir, [association])

    assert existing_file.read_text(encoding="utf-8") == "existing output"
    assert list(output_dir.iterdir()) == [existing_file]


def test_render_run_figure_crops_rejects_modified_preserved_pdf(
    tmp_path: Path,
) -> None:
    run_dir = _create_figure_rendering_run(tmp_path)
    document = DoclingDocument(name="synthetic")
    association = _make_render_association(document, 1)

    preserved_pdf = run_dir / "input" / "paper.pdf"
    preserved_pdf.write_bytes(b"modified source")

    with pytest.raises(ValueError, match="checksum does not match"):
        figures.render_run_figure_crops(run_dir, [association])

    assert not (run_dir / "figures").exists()


@pytest.fixture
def extraction_ready_run(
    tmp_path: Path,
    fake_docling_converter: Mock,
) -> Path:
    run_dir = _create_figure_rendering_run(tmp_path)

    runs.mark_page_rendering_running(run_dir)
    runs.mark_page_rendering_succeeded(run_dir)
    runs.mark_document_conversion_running(run_dir)
    runs.mark_document_conversion_succeeded(run_dir)

    conversion_dir = run_dir / "document_conversion"
    conversion_dir.mkdir()

    (conversion_dir / "document.md").write_text(
        "<figcaption>Figure 1: Markdown caption.</figcaption>\n"
        "<figcaption>Figure 2: Missing picture.</figcaption>\n",
        encoding="utf-8",
    )

    document = DoclingDocument(name="synthetic")
    _make_render_association(document, 1)

    fake_docling_converter.convert.return_value = SimpleNamespace(
        status=ConversionStatus.SUCCESS,
        document=document,
        errors=[],
    )

    return run_dir


def test_extract_figures_persists_images_manifest_and_status(
    extraction_ready_run: Path,
    fake_docling_converter: Mock,
) -> None:
    run_dir = extraction_ready_run
    document_path = run_dir / "document_conversion" / "document.md"
    original_markdown = document_path.read_bytes()

    manifest_path = figures.extract_figures(
        run_dir,
        scale=2.0,
        margin_pt=1.0,
    )

    assert manifest_path == run_dir / "figures" / "manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["document_id"] == run_manifest["document_id"]
    assert manifest["source_pdf"] == "input/paper.pdf"
    assert manifest["markdown_path"] == "document_conversion/document.md"
    assert manifest["rendering"]["scale"] == 2.0
    assert manifest["rendering"]["margin_pt"] == 1.0

    resolved, pending = manifest["figures"]

    assert resolved["figure_id"] == "figure_1"
    assert resolved["relative_path"] == "figures/figure_1.png"
    assert resolved["caption"] == "Figure 1: Markdown caption."
    assert resolved["caption_source"] == "markdown"
    assert resolved["association_method"] == "docling"
    assert resolved["unresolved_reason"] is None

    candidate = resolved["candidates"][0]

    assert candidate["caption_docling"] == ("Fig. 1. Original Docling caption.")
    assert candidate["caption_refs"]
    assert candidate["positions"][0]["page_no"] == 1
    assert candidate["positions"][0]["bbox"]["coord_origin"] == "TOPLEFT"

    assert pending["figure_id"] == "figure_2"
    assert pending["relative_path"] is None
    assert pending["markdown_captions"] == ["Figure 2: Missing picture."]
    assert pending["candidates"] == []
    assert pending["unresolved_reason"]

    with Image.open(run_dir / resolved["relative_path"]) as image:
        assert image.format == "PNG"
        assert image.mode == "RGB"
        assert image.size == (64, 84)

    assert set(manifest["timings_seconds"]) == {
        "docling",
        "association",
        "figure_rendering",
    }
    assert all(value >= 0 for value in manifest["timings_seconds"].values())

    assert document_path.read_bytes() == original_markdown
    assert runs.load_run_status(run_dir).phases.figure_extraction.state == ("succeeded")
    fake_docling_converter.convert.assert_called_once_with(
        run_dir / "input" / "paper.pdf"
    )


def test_extract_figures_writes_manifest_when_all_figures_are_unresolved(
    extraction_ready_run: Path,
    fake_docling_converter: Mock,
) -> None:
    fake_docling_converter.convert.return_value.document = DoclingDocument(name="empty")

    manifest_path = figures.extract_figures(extraction_ready_run)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(manifest["figures"]) == 2
    assert all(
        entry["relative_path"] is None and entry["unresolved_reason"]
        for entry in manifest["figures"]
    )
    assert list(manifest_path.parent.glob("*.png")) == []
    assert (
        runs.load_run_status(extraction_ready_run).phases.figure_extraction.state
        == "succeeded"
    )


def test_extract_figures_preserves_ambiguous_captions(
    extraction_ready_run: Path,
) -> None:
    caption = "Figure 1: Repeated caption."
    document_path = extraction_ready_run / "document_conversion" / "document.md"
    document_path.write_text(
        f"<figcaption>{caption}</figcaption>\n<figcaption>{caption}</figcaption>\n",
        encoding="utf-8",
    )

    manifest_path = figures.extract_figures(extraction_ready_run)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(manifest["figures"]) == 1

    entry = manifest["figures"][0]

    assert entry["markdown_captions"] == [caption, caption]
    assert len(entry["candidates"]) == 1
    assert entry["caption"] is None
    assert entry["association_method"] is None
    assert entry["relative_path"] is None
    assert entry["unresolved_reason"]


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        (None, FileNotFoundError),
        (" \n\t", ValueError),
    ],
)
def test_extract_figures_rejects_missing_or_empty_markdown(
    extraction_ready_run: Path,
    fake_docling_converter: Mock,
    content: str | None,
    expected_error: type[Exception],
) -> None:
    document_path = extraction_ready_run / "document_conversion" / "document.md"

    if content is None:
        document_path.unlink()
    else:
        document_path.write_text(content, encoding="utf-8")

    with pytest.raises(expected_error):
        figures.extract_figures(extraction_ready_run)

    phase = runs.load_run_status(extraction_ready_run).phases.figure_extraction

    assert phase.state == "failed"
    assert phase.error is not None
    assert "input validation" in phase.error.message
    assert not (extraction_ready_run / "figures").exists()
    fake_docling_converter.convert.assert_not_called()


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("conversion", "Document conversion must succeed"),
        ("identity", "Run status identity"),
        ("already_started", "pending state"),
    ],
)
def test_extract_figures_rejects_invalid_prerequisites(
    extraction_ready_run: Path,
    fake_docling_converter: Mock,
    problem: str,
    message: str,
) -> None:
    status_path = extraction_ready_run / "status.json"

    if problem == "already_started":
        runs.mark_figure_extraction_running(extraction_ready_run)
    else:
        payload = json.loads(status_path.read_text(encoding="utf-8"))

        if problem == "conversion":
            payload["phases"]["document_conversion"] = runs.PhaseStatus(
                state="pending"
            ).model_dump(mode="json")
        else:
            payload["run_id"] = "different-run"

        status_path.write_text(json.dumps(payload), encoding="utf-8")

    original_status = status_path.read_bytes()

    with pytest.raises(ValueError, match=message):
        figures.extract_figures(extraction_ready_run)

    assert status_path.read_bytes() == original_status
    fake_docling_converter.convert.assert_not_called()


def test_extract_figures_rejects_existing_output_before_docling(
    extraction_ready_run: Path,
    fake_docling_converter: Mock,
) -> None:
    output_dir = extraction_ready_run / "figures"
    output_dir.mkdir()

    existing_file = output_dir / "keep.txt"
    existing_file.write_text("existing output", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Figure output already exists"):
        figures.extract_figures(extraction_ready_run)

    assert existing_file.read_text(encoding="utf-8") == "existing output"
    assert list(output_dir.iterdir()) == [existing_file]
    assert (
        runs.load_run_status(extraction_ready_run).phases.figure_extraction.state
        == "pending"
    )
    fake_docling_converter.convert.assert_not_called()


def test_extract_figures_records_docling_failure(
    extraction_ready_run: Path,
    fake_docling_converter: Mock,
) -> None:
    fake_docling_converter.convert.side_effect = RuntimeError(
        "Synthetic layout failure."
    )

    with pytest.raises(RuntimeError, match="Synthetic layout failure"):
        figures.extract_figures(extraction_ready_run)

    phase = runs.load_run_status(extraction_ready_run).phases.figure_extraction

    assert phase.state == "failed"
    assert phase.error is not None
    assert phase.error.type == "RuntimeError"
    assert "Docling processing" in phase.error.message
    assert not (extraction_ready_run / "figures").exists()
    fake_docling_converter.convert.assert_called_once()


@pytest.mark.parametrize(
    ("failure_point", "expected_stage"),
    [
        ("second_image", "figure rendering"),
        ("manifest", "manifest persistence"),
    ],
)
def test_extract_figures_preserves_images_after_persistence_failure(
    extraction_ready_run: Path,
    fake_docling_converter: Mock,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    expected_stage: str,
) -> None:
    document = fake_docling_converter.convert.return_value.document
    _make_render_association(document, 2)

    if failure_point == "second_image":
        original_write_bytes = figures.write_bytes

        def fail_second_image(path: Path, data: bytes) -> None:
            if path.name == "figure_2.png":
                raise OSError("Synthetic write failure.")

            original_write_bytes(path, data)

        monkeypatch.setattr(figures, "write_bytes", fail_second_image)
    else:
        monkeypatch.setattr(
            figures,
            "write_json",
            Mock(side_effect=OSError("Synthetic write failure.")),
        )

    with pytest.raises(OSError, match="Synthetic write failure"):
        figures.extract_figures(extraction_ready_run)

    output_dir = extraction_ready_run / "figures"

    assert (output_dir / "figure_1.png").is_file()
    assert not (output_dir / "manifest.json").exists()

    if failure_point == "manifest":
        assert (output_dir / "figure_2.png").is_file()
    else:
        assert not (output_dir / "figure_2.png").exists()

    status = runs.load_run_status(extraction_ready_run)
    phase = status.phases.figure_extraction

    assert phase.state == "failed"
    assert phase.error is not None
    assert phase.error.type == "OSError"
    assert expected_stage in phase.error.message
    assert status.phases.document_conversion.state == "succeeded"


def _make_caption_recovery_document(
    *,
    caption_bbox: BoundingBox | None = None,
    caption_page: int = 1,
) -> tuple[DoclingDocument, PictureItem, TextItem]:
    document = DoclingDocument(name="caption-recovery")

    picture = document.add_picture()
    picture.prov.append(
        ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(
                l=20.0,
                t=160.0,
                r=80.0,
                b=100.0,
                coord_origin=CoordOrigin.BOTTOMLEFT,
            ),
            charspan=(0, 0),
        )
    )

    if caption_bbox is None:
        caption_bbox = BoundingBox(
            l=20.0,
            t=85.0,
            r=80.0,
            b=75.0,
            coord_origin=CoordOrigin.BOTTOMLEFT,
        )

    caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="Fig. 8. Original Docling caption.",
    )
    caption.prov.append(
        ProvenanceItem(
            page_no=caption_page,
            bbox=caption_bbox,
            charspan=(0, len(caption.text)),
        )
    )

    return document, picture, caption


@pytest.mark.parametrize(
    ("left", "top", "right", "bottom", "expected_distance"),
    [
        (20.0, 85.0, 80.0, 75.0, 15.0),
        (20.0, 100.0, 80.0, 90.0, 0.0),
        (20.0, 70.0, 80.0, 60.0, 30.0),
        (20.0, 69.9, 80.0, 59.9, None),
        (5.0, 85.0, 80.0, 75.0, 15.0),
        (4.0, 85.0, 80.0, 75.0, None),
        (20.0, 180.0, 80.0, 170.0, None),
        (20.0, 110.0, 80.0, 100.0, None),
    ],
    ids=[
        "caption-below-picture",
        "zero-gap",
        "maximum-gap",
        "gap-too-large",
        "minimum-overlap",
        "insufficient-overlap",
        "caption-above-picture",
        "vertical-overlap",
    ],
)
def test_calculate_caption_distance_checks_geometry(
    left: float,
    top: float,
    right: float,
    bottom: float,
    expected_distance: float | None,
) -> None:
    bbox = BoundingBox(
        l=left,
        t=top,
        r=right,
        b=bottom,
        coord_origin=CoordOrigin.BOTTOMLEFT,
    )
    _document, picture, caption = _make_caption_recovery_document(
        caption_bbox=bbox,
    )

    distance = figures.calculate_caption_distance(caption, picture)

    if expected_distance is None:
        assert distance is None
    else:
        assert distance == pytest.approx(expected_distance)


@pytest.mark.parametrize(
    "problem",
    ["different_page", "top_left_coordinates"],
)
def test_calculate_caption_distance_rejects_unsupported_positions(
    problem: str,
) -> None:
    caption_bbox = None
    caption_page = 1

    if problem == "different_page":
        caption_page = 2
    else:
        caption_bbox = BoundingBox(
            l=20.0,
            t=115.0,
            r=80.0,
            b=125.0,
            coord_origin=CoordOrigin.TOPLEFT,
        )

    _document, picture, caption = _make_caption_recovery_document(
        caption_bbox=caption_bbox,
        caption_page=caption_page,
    )

    assert figures.calculate_caption_distance(caption, picture) is None


@pytest.mark.parametrize("target", ["caption", "picture"])
@pytest.mark.parametrize("position_count", [0, 2])
def test_calculate_caption_distance_requires_unique_positions(
    target: str,
    position_count: int,
) -> None:
    _document, picture, caption = _make_caption_recovery_document()
    item = caption if target == "caption" else picture

    if position_count == 0:
        item.prov.clear()
    else:
        item.prov.append(item.prov[0].model_copy(deep=True))

    assert figures.calculate_caption_distance(caption, picture) is None


@pytest.mark.parametrize(
    "conflict",
    [
        "duplicate_caption",
        "competing_picture",
        "competing_caption",
    ],
)
def test_recover_figure_captions_rejects_ambiguous_matches(
    conflict: str,
) -> None:
    document, picture, caption = _make_caption_recovery_document()

    if conflict == "competing_picture":
        competitor = document.add_picture()
        competitor.prov.append(picture.prov[0].model_copy(deep=True))
    else:
        text = (
            caption.text
            if conflict == "duplicate_caption"
            else "Fig. 9. Another Docling caption."
        )
        competitor = document.add_text(
            label=DocItemLabel.CAPTION,
            text=text,
        )
        competitor.prov.append(caption.prov[0].model_copy(deep=True))

    original_document = document.model_dump()
    candidates = figures.collect_figure_candidates(document)

    recoveries = figures.recover_figure_captions(document, candidates)

    assert recoveries == {}
    assert document.model_dump() == original_document


def test_recover_figure_captions_preserves_existing_association() -> None:
    document, picture, caption = _make_caption_recovery_document()

    linked_picture = document.add_picture(caption=caption)
    linked_picture.prov.append(
        ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(
                l=200.0,
                t=160.0,
                r=260.0,
                b=100.0,
                coord_origin=CoordOrigin.BOTTOMLEFT,
            ),
            charspan=(0, 0),
        )
    )

    original_document = document.model_dump()
    candidates = figures.collect_figure_candidates(document)

    recoveries = figures.recover_figure_captions(document, candidates)

    assert recoveries == {}
    assert picture.captions == []
    assert linked_picture.caption_text(document) == caption.text
    assert document.model_dump() == original_document


def test_extract_figures_recovers_caption_and_preserves_provenance(
    extraction_ready_run: Path,
    fake_docling_converter: Mock,
) -> None:
    document, picture, caption = _make_caption_recovery_document()
    original_document = document.model_dump()

    fake_docling_converter.convert.return_value.document = document

    markdown_path = extraction_ready_run / "document_conversion" / "document.md"
    markdown_path.write_text(
        "<figcaption>Figure 8: Markdown caption.</figcaption>",
        encoding="utf-8",
    )

    manifest_path = figures.extract_figures(extraction_ready_run)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(manifest["figures"]) == 1

    entry = manifest["figures"][0]

    assert entry["figure_id"] == "figure_8"
    assert entry["label"] == "Figure 8"
    assert entry["relative_path"] == "figures/figure_8.png"
    assert entry["caption"] == "Figure 8: Markdown caption."
    assert entry["caption_source"] == "markdown"
    assert entry["association_method"] == "geometric_recovery"
    assert entry["unresolved_reason"] is None

    assert len(entry["candidates"]) == 1
    candidate = entry["candidates"][0]

    assert candidate["docling_ref"] == picture.self_ref
    assert candidate["caption_docling"] == ""
    assert candidate["caption_refs"] == []

    assert entry["caption_recovery"] == {
        "docling_ref": caption.self_ref,
        "text": "Fig. 8. Original Docling caption.",
        "positions": [
            provenance.model_dump(mode="json") for provenance in caption.prov
        ],
        "distance_pt": 15.0,
    }

    image_path = extraction_ready_run / entry["relative_path"]

    with Image.open(image_path) as image:
        assert image.format == "PNG"
        assert image.mode == "RGB"
        image.load()

    assert document.model_dump() == original_document
    assert (
        runs.load_run_status(extraction_ready_run).phases.figure_extraction.state
        == "succeeded"
    )

    fake_docling_converter.convert.assert_called_once_with(
        extraction_ready_run / "input" / "paper.pdf"
    )
