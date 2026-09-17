import re

REPORT_SECTIONS = (
    "## 1. Selected antenna",
    "## 2. Components, materials and layers",
    "## 3. Geometry, dimensions and feeding",
    "## 4. Derivations and conflicts",
    "## 5. Reconstruction gaps",
)

ARCHITECTURE_INSTRUCTIONS = """\
Extract an evidence-grounded technical description of the antenna architecture.
Write the report in English.

The report will support a later canonicalization step. Preserve the details
needed for reconstruction. Do not produce the final architecture JSON or a
CAD specification.

Target selection:
- Describe the final design supported by the paper.
- Prefer the final fabricated or measured design when the paper identifies it.
- A final design may be simulated only. Do not imply fabrication or measurement
  without evidence.
- Mention earlier iterations briefly to explain the design evolution. Do not
  reproduce their architectures or mix their dimensions into the final design.
- Reuse information from an earlier iteration only when the paper supports its
  applicability to the final design.
- If the final design cannot be identified, explain the ambiguity and keep
  candidate-specific information separate.

Architecture coverage:
- Preserve components, geometry, materials, material properties, layer order,
  thicknesses, dimensions, units, symbols, spatial relationships and repetitions.
- Describe feeds, grounds, ports, vias, connections and surrounding structures
  when supported.
- Distinguish added material from removed material, including slots and holes.
- Preserve the meaning of dimensional symbols. Do not rename a parameter as a
  physical length or width unless the evidence supports that interpretation.
- Include source-supported equations or derivations needed to determine geometry.
- Do not invent coordinates, conductor properties, feed details, solver settings
  or conventional defaults.
- Do not extract a performance-results inventory. Mention results only when
  necessary to establish the selected design or its validation status.

Evidence:
- Ground factual claims in the supplied document or visual assets actually
  received through the tool.
- Cite a document section, table or equation label with a short source-faithful
  excerpt where useful. Do not invent page numbers.
- For visual observations, cite the exact received asset identifier and the
  relevant panel or visible feature.
- A caption is textual evidence. Reading a caption does not mean that you
  inspected the image.
- Image alt descriptions in the converted Markdown may have been generated
  during conversion. Do not treat them as original paper statements or as
  evidence that you inspected an image.
- Do not estimate exact dimensions from drawing proportions or pixels.
- Preserve conflicts between sources. Do not silently choose a convenient value.
- For a derivation, state the premises, the relation used and the evidence for
  the premises. Do not present the derived value as directly reported.

Report format:
- Return only the Markdown report, without enclosing code fences.
- Use the five exact second-level headings listed below, in that order.
- Each section must contain substantive content or an explicit statement that
  the relevant information is unavailable or not applicable.
- Define each relevant technical claim as a top-level bullet using this form:
  - A001 [Reported] Claim text.
    Evidence: Source reference.
- Use unique claim identifiers, starting at A001.
- Use only these claim classifications:
  Reported: information explicitly stated in the paper.
  Visual: an observation from an image actually received.
  Derived: a conclusion calculated or inferred from stated premises.
- Put a non-empty, indented Evidence: line within each claim.
- Tables and additional paragraphs may appear within a claim when they share
  its classification and evidence. Split claims when their sources or
  classifications differ.
- Refer back to an existing claim by its identifier without defining it again.
- Describe missing information, ambiguity and unresolved conflicts in ordinary
  prose or ordinary bullets. Do not turn these into unsupported factual claims.
- Do not propose engineering choices to fill gaps. If the paper proposes an
  unapplied change, identify it as unapplied and keep it separate from the design.
- Avoid repetition, but do not omit reconstruction-critical detail to make the
  report shorter.
- An honest incomplete report is acceptable. If no supported architecture claims
  can be extracted, explain that limitation instead of inventing claims.

Required sections:
""" + "\n".join(REPORT_SECTIONS)

_SECTION_PATTERN = re.compile(r"^##[ \t]+[^\n]+$", re.MULTILINE)
_CLAIM_PATTERN = re.compile(r"^- (A[0-9]{3,})\b([^\n]*)$", re.MULTILINE)
_CLASSIFICATION_PATTERN = re.compile(r"^\s+\[(Reported|Visual|Derived)\]\s+\S")
_EVIDENCE_PATTERN = re.compile(
    r"^[ \t]+Evidence:[ \t]*(\S[^\n]*)$",
    re.MULTILINE,
)
_CODE_FENCE_PATTERN = re.compile(
    r"^[ \t]*(?:`{3,}|~{3,})",
    re.MULTILINE,
)


def validate_architecture_report(report: str) -> tuple[str, ...]:
    """Check report structure without judging scientific correctness."""
    if not report.strip():
        return ("The architecture report is empty.",)

    errors: list[str] = []

    if _CODE_FENCE_PATTERN.search(report):
        errors.append("The report must not contain fenced code blocks.")

    sections = list(_SECTION_PATTERN.finditer(report))
    actual_headings = tuple(section.group().strip() for section in sections)

    if actual_headings != REPORT_SECTIONS:
        errors.append("The report must contain the five required sections in order.")
        return tuple(errors)

    for index, section in enumerate(sections):
        end = sections[index + 1].start() if index + 1 < len(sections) else len(report)

        if not report[section.end() : end].strip():
            errors.append(f"Section is empty: {REPORT_SECTIONS[index]}")

    claims = list(_CLAIM_PATTERN.finditer(report))
    seen_ids: set[str] = set()

    for index, claim in enumerate(claims):
        claim_id = claim.group(1)
        claim_text = claim.group(2)

        if claim_id in seen_ids:
            errors.append(f"Duplicate claim identifier: {claim_id}")

        seen_ids.add(claim_id)

        if claim.start() < sections[0].start():
            errors.append(f"Claim appears before the report sections: {claim_id}")

        if not _CLASSIFICATION_PATTERN.match(claim_text):
            errors.append(
                f"{claim_id} must have a supported classification and claim text."
            )

        next_claim = (
            claims[index + 1].start() if index + 1 < len(claims) else len(report)
        )
        next_section = next(
            (
                section.start()
                for section in sections
                if section.start() > claim.start()
            ),
            len(report),
        )
        claim_end = min(next_claim, next_section)
        claim_body = report[claim.end() : claim_end]

        if not _EVIDENCE_PATTERN.search(claim_body):
            errors.append(f"{claim_id} has no non-empty Evidence line.")

    return tuple(errors)
