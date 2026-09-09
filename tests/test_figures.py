from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import io
from PIL import Image

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
)

from antenna_paper_extraction import figures
from antenna_paper_extraction.figures import (
    extract_figure_label,
    extract_markdown_captions,
    group_captions_by_label,
)


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

    with io.BytesIO(png_bytes) as buffer:
        with Image.open(buffer) as cropped_image:
            assert cropped_image.format == "PNG"
            assert cropped_image.mode == "RGB"
            assert cropped_image.size == (10, 10)

            assert cropped_image.getpixel((0, 0)) == (255, 0, 0)
            assert cropped_image.getpixel((9, 9)) == (0, 0, 255)
            assert cropped_image.getpixel((5, 5)) == (255, 255, 255)