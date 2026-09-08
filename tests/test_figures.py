import pytest

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
