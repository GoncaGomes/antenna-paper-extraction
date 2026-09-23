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

The report will support later canonicalization. Preserve the information needed
to reconstruct the supported design, including uncertainty and missing details.
Do not produce the final architecture JSON or a CAD specification.

Target and scope:
- Identify the final design supported by the paper and its validation status.
  Prefer the final fabricated or measured design when identified. A final design
  may be simulated only; do not imply fabrication or measurement without evidence.
- If the paper presents multiple final designs, describe them separately. If the
  final design is ambiguous, explain the ambiguity without selecting arbitrarily.
- Distinguish individual elements from arrays or assemblies, and distinguish
  physical configurations or operating states when their geometry differs.
- Mention earlier iterations only to explain the final selection or a relevant
  design change. Do not reproduce their architectures or parameter inventories.
- Carry earlier information into the final design only with evidence of its
  applicability. State any inferred continuity alongside the affected claim.
- Describe the implemented design. Keep proposed but unapplied changes separate.
- Include performance results only when needed to establish design selection
  or validation status.

Architecture coverage:
- Preserve components, materials and their properties, layers, thicknesses,
  dimensions, units, symbols, spatial relationships and repetitions.
- Describe feeds, grounds, ports, vias, connections and surrounding structures
  when supported. Distinguish physical components from simulation constructs.
- Distinguish conducting regions, dielectric regions and removed material.
- Associate each parameter with its component, variant and geometric meaning.
  Preserve the source symbol when its meaning cannot be established.
- Keep values and their qualifications together. Distinguish nominal, optimized,
  simulated and measured values when the paper makes that distinction.
- Do not invent coordinates, material properties, connection details, solver
  settings or conventional defaults. Do not propose choices to fill gaps.

Visual interpretation:
- Use the text and captions to establish which design, panel and configuration
  an image represents before applying its contents to the selected design.
- Interpret a dimension using its arrows and extension lines: identify the
  feature, direction and both endpoints. Do not replace an unclear endpoint
  with a plausible centerline, edge or connection.
- Use clearly visible geometry even when the text does not define it verbally.
  If a label, endpoint or connection is unclear, preserve that specific uncertainty.
- Do not estimate exact dimensions from drawing proportions or pixels.
- Distinguish observation from inference: appearance alone does not establish
  material composition, and a visible line termination does not define a port.
- An inspected image supports only what it shows. A generic schematic or an
  earlier prototype does not automatically establish the final geometry.

Evidence and uncertainty:
- Ground claims in the supplied document or visual assets actually received.
  Cite a section, table or equation label, with a short faithful excerpt if useful.
  Do not invent page numbers.
- For visual observations, cite the exact received asset identifier and the
  relevant panel or feature.
- Captions are textual evidence, not proof of image inspection. Converted image
  alt descriptions may be generated; do not treat them as original paper
  statements or as evidence that you inspected an image.
- Distinguish information absent from the supplied material, an unavailable
  image, an unreadable feature and contradictory evidence.
- Lack of mention does not prove that a component or feature is absent.
- Report a conflict when sources make incompatible claims about the same
  property, design and conditions. First consider rounding, units, naming
  conventions and differences between variants or validation stages.
- Preserve unresolved alternatives and their sources. Do not silently select
  a preferred value, repair an equation or resolve an ambiguity by convention.
- Include equations and derivations only when needed to establish geometry
  or explain a reconstruction-relevant inconsistency. Do not reproduce the
  paper's general theory or audit every equation.
- For a derivation, state the supported premises, relation and result. Keep
  inferred conclusions distinct from directly reported or observed information.

Report format:
- Return only the Markdown report, without enclosing code fences.
- Use the five exact second-level headings listed below, in that order.
- Each section must contain relevant content or a brief statement that the
  information is unavailable or not applicable. Do not manufacture derivations
  or conflicts to fill a section.
- Define each relevant technical claim as a top-level bullet:
  - A001 [Reported] Claim text.
    Evidence: Source reference.
- Use unique claim identifiers, starting at A001, and only these classifications:
  Reported: explicitly stated in the source text, table, equation or caption.
  Visual: directly observed in an image actually received.
  Derived: calculated or inferred from identified, supported premises.
- Put a non-empty, indented Evidence: line within each claim.
- Split claims when their classifications or applicability differ. Tables may
  group parameters that share the same classification, applicability and evidence.
- Refer back to existing claim identifiers instead of repeating their content.
- Describe gaps, ambiguity and unresolved conflicts in ordinary prose or bullets,
  referring to the relevant claims where useful.
- Keep uncertainty beside the affected claim; do not assert a fact confidently
  and qualify it only in the final section.
- Prioritize reconstruction-critical detail. Avoid repeated results, background
  theory and earlier-design detail that does not establish the final architecture.
- An honest incomplete report is acceptable. If no supported architecture claims
  can be extracted, explain the limitation instead of inventing claims.

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
