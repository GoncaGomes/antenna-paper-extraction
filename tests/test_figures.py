from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from docling.datamodel.base_models import ConversionStatus
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
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
