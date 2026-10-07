import pytest

from antenna_paper_extraction.architecture_report import (
    REPORT_SECTIONS,
    validate_architecture_report,
)

VALID_REPORT = """\
## 1. Selected antenna

- A001 [Reported] The paper selects Design B as the final simulated design.
  Evidence: Section 3; "Design B is selected as the final design".

Fabrication and measurement are not established by the supplied source.

## 2. Components, materials and layers

The substrate material and conductor thickness are not reported.

## 3. Geometry, dimensions and feeding

- A002 [Reported] The final patch has the following dimensions:

  | Parameter | Value |
  | --- | --- |
  | Length | 12 mm |
  | Width | 8 mm |

  Evidence: Table 1; "Length: 12 mm; Width: 8 mm".

The feeding arrangement is not specified.

## 4. Semantic interpretations and conflicts

No reconstruction-related derivation or source conflict was identified.

## 5. Reconstruction gaps

The substrate properties, conductor thickness and feeding details are missing.

## 6. Final architecture

Design B is the final simulated design; fabrication and measurement are not
established. Its patch is 12 mm long and 8 mm wide (A001, A002).

Blocking reconstruction gaps: substrate material and properties, conductor
thickness and feeding details are unavailable, preventing a complete construction.
"""

INCOMPLETE_REPORT = """\
## 1. Selected antenna

The supplied material does not identify a final antenna design.

## 2. Components, materials and layers

No supported component or material description could be extracted.

## 3. Geometry, dimensions and feeding

Dimensions and feeding details are unavailable.

## 4. Semantic interpretations and conflicts

No supported derivation is possible from the available information.

## 5. Reconstruction gaps

The available information is insufficient to reconstruct an antenna.

## 6. Final architecture

No supported antenna configuration can be described from the supplied material.
Blocking reconstruction gaps: the final design, components, materials, dimensions,
placement and electrical connections are unavailable.
"""


def test_accepts_report_with_sourced_claims_and_gaps() -> None:
    assert validate_architecture_report(VALID_REPORT) == ()


def test_accepts_honest_report_without_extractable_claims() -> None:
    assert validate_architecture_report(INCOMPLETE_REPORT) == ()


def test_rejects_empty_report() -> None:
    assert validate_architecture_report(" \n") == ("The architecture report is empty.",)


@pytest.mark.parametrize("heading", REPORT_SECTIONS)
def test_rejects_missing_section(heading: str) -> None:
    report = VALID_REPORT.replace(
        heading,
        heading.replace("## ", "### ", 1),
    )

    errors = validate_architecture_report(report)

    assert any("six required sections" in error for error in errors)


def test_rejects_wrong_section_order() -> None:
    report = VALID_REPORT.replace(
        "## 2. Components, materials and layers",
        "## 3. Geometry, dimensions and feeding",
    ).replace(
        "## 3. Geometry, dimensions and feeding\n\n- A002",
        "## 2. Components, materials and layers\n\n- A002",
    )

    errors = validate_architecture_report(report)

    assert any("six required sections" in error for error in errors)


@pytest.mark.parametrize("heading", REPORT_SECTIONS)
def test_rejects_empty_section(heading: str) -> None:
    index = REPORT_SECTIONS.index(heading)
    start = VALID_REPORT.index(heading) + len(heading)
    end = (
        VALID_REPORT.index(REPORT_SECTIONS[index + 1])
        if index + 1 < len(REPORT_SECTIONS)
        else len(VALID_REPORT)
    )
    report = VALID_REPORT[:start] + "\n\n" + VALID_REPORT[end:]

    errors = validate_architecture_report(report)

    assert f"Section is empty: {heading}" in errors


def test_rejects_duplicate_claim_definitions() -> None:
    report = VALID_REPORT.replace("- A002 [Reported]", "- A001 [Reported]")

    errors = validate_architecture_report(report)

    assert "Duplicate claim identifier: A001" in errors


def test_allows_references_to_existing_claims() -> None:
    report = VALID_REPORT.replace(
        "No reconstruction-related derivation or source conflict was identified.",
        "The dimensions in A002 do not establish the feeding position.",
    )

    assert validate_architecture_report(report) == ()


@pytest.mark.parametrize(
    "replacement",
    [
        "- A001 [Assumed] The paper selects Design B.",
        "- A001 The paper selects Design B.",
        "- A001 [Reported]",
    ],
)
def test_rejects_invalid_claim_definition(replacement: str) -> None:
    report = VALID_REPORT.replace(
        "- A001 [Reported] The paper selects Design B as the final simulated design.",
        replacement,
    )

    errors = validate_architecture_report(report)

    assert "A001 must have a supported classification and claim text." in errors


@pytest.mark.parametrize(
    "replacement",
    ["", "  Evidence:   "],
)
def test_rejects_missing_or_empty_claim_evidence(replacement: str) -> None:
    report = VALID_REPORT.replace(
        '  Evidence: Section 3; "Design B is selected as the final design".',
        replacement,
    )

    errors = validate_architecture_report(report)

    assert "A001 has no non-empty Evidence line." in errors


def test_does_not_borrow_evidence_from_the_next_claim() -> None:
    report = VALID_REPORT.replace(
        '  Evidence: Section 3; "Design B is selected as the final design".',
        "",
    )

    errors = validate_architecture_report(report)

    assert "A001 has no non-empty Evidence line." in errors
    assert "A002 has no non-empty Evidence line." not in errors


def test_rejects_report_wrapped_in_code_fences() -> None:
    report = f"```markdown\n{VALID_REPORT}\n```"

    errors = validate_architecture_report(report)

    assert "The report must not contain fenced code blocks." in errors
