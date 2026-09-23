import pytest

from antenna_paper_extraction.architecture_report import (
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

## 4. Derivations and conflicts

No reconstruction-related derivation or source conflict was identified.

## 5. Reconstruction gaps

The substrate properties, conductor thickness and feeding details are missing.
"""

INCOMPLETE_REPORT = """\
## 1. Selected antenna

The supplied material does not identify a final antenna design.

## 2. Components, materials and layers

No supported component or material description could be extracted.

## 3. Geometry, dimensions and feeding

Dimensions and feeding details are unavailable.

## 4. Derivations and conflicts

No supported derivation is possible from the available information.

## 5. Reconstruction gaps

The available information is insufficient to reconstruct an antenna.
"""


def test_accepts_report_with_sourced_claims_and_gaps() -> None:
    assert validate_architecture_report(VALID_REPORT) == ()


def test_accepts_honest_report_without_extractable_claims() -> None:
    assert validate_architecture_report(INCOMPLETE_REPORT) == ()


def test_rejects_empty_report() -> None:
    assert validate_architecture_report(" \n") == ("The architecture report is empty.",)


def test_rejects_missing_section() -> None:
    report = VALID_REPORT.replace(
        "## 5. Reconstruction gaps",
        "### Reconstruction gaps",
    )

    errors = validate_architecture_report(report)

    assert any("five required sections" in error for error in errors)


def test_rejects_wrong_section_order() -> None:
    report = VALID_REPORT.replace(
        "## 2. Components, materials and layers",
        "## 3. Geometry, dimensions and feeding",
    ).replace(
        "## 3. Geometry, dimensions and feeding\n\n- A002",
        "## 2. Components, materials and layers\n\n- A002",
    )

    errors = validate_architecture_report(report)

    assert any("five required sections" in error for error in errors)


def test_rejects_empty_section() -> None:
    report = VALID_REPORT.replace(
        "The substrate material and conductor thickness are not reported.",
        "",
    )

    errors = validate_architecture_report(report)

    assert "Section is empty: ## 2. Components, materials and layers" in errors


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
