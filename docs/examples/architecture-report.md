# Experimental MCP architecture report excerpt

Source paper: Matthias John and Max J. Ammann, *Optimization of Impedance
Bandwidth for the Printed Rectangular Monopole Antenna*, *Microwave and Optical
Technology Letters* 47(2), 153-154 (2005).
[DOI: 10.1002/mop.21109](https://doi.org/10.1002/mop.21109).
The title and DOI appear on the preserved PDF's cover pages, as extracted in
the run's server store; the paper body and overview use "Optimisation".

- Workflow: experimental MCP workflow, with progressive text reads and
  server-side visual inspections.
- Execution: `run_20261007T111320+0100_e4875a37`, MCP architecture stage on
  7 October 2026.
- Original artefact: `mcp/architecture/architecture_evidence_report.md` within
  that run. Its execution record reports `succeeded`, `final_answer` and passing
  structural diagnostics. These states do not certify scientific validity.
- Producing client and server revisions: unverified. The
  [trace summary](trace-summary.md#provenance) records hashes and the specific
  prompt correspondences found in Git history.

This is an **excerpt**: the complete selected-antenna, semantic-interpretation
and reconstruction-gaps sections; the closing unresolved-details paragraphs of
section 6; and evidence claims A002, A006, A008, A012 and A013. Text below
"Published excerpt" is copied verbatim, including punctuation, claim labels and
all three completion assumptions. Other sections and claims are omitted;
references to their identifiers remain references to the complete local report.
No corrections or additional assumptions have been inserted into the output.

`Reported` claims refer to source text. `Visual` claims are model-generated
observations from server inspections, not independently verified measurements.
Section 4 adopts semantic interpretations; H001-H003 are the agent's proposed
choices for the unspecified metal, SMA mounting and feedline face. They are not
reported construction facts. The "no blocking gaps" conclusion is the model's
assessment of that assumed configuration, not validation of the authors' build.

There are material evidence limits. The page-7 inspection describes centering
as approximate and cannot confirm exact alignment from the drawing. Its A013
claim is stronger, although interpretation prose preserves a not-to-scale caveat.
The inspection also leaves the physical meaning of `hgap` uncertain between a
height separation and an in-plane offset; section 4 adopts the in-plane reading.
These differences are preserved rather than silently reconciled. The existing
[one-paper evaluation](../../PLAN.md#task-2---bounded-prompt-evaluation-2026-10-07)
also flags the stronger centering claim and pending owner review.

Evidence uses physical PDF page numbers, including two cover pages. The text
references physical page 4; A012 and A013 cite `page:7` and inspection
`38f41a3b7ae541988db4f4f10cb7e4d7`. The [trace](trace-summary.md#recorded-execution)
explains the preceding inspection of a caption-only page and the explicit
request for the page containing the drawing. Full runs, images and execution
JSON are retained locally and are not published here.

## Published excerpt

## 1. Selected antenna

**Target:** The printed rectangular-plate monopole antenna, fed by a microstrip line and an SMA connector, as described in the "Antenna Geometry" section (p.4) and depicted in Figure 1 (p.7). This is the final design: it carries the optimized parameter values (plate width wp = 20 mm, feed gap hgap = 2 mm) that the paper identifies as yielding the widest bandwidth (Conclusions, p.5).

**Implementation status:** Fabricated and measured. The paper reports a *measured* return loss alongside the simulated one for this antenna (p.4, "Figure 2 shows the measured and simulated return loss"), establishing that the described geometry was built and measured. (Specific bandwidth/frequency figures are excluded here as performance results.)

**Working configuration:** One consistent configuration is adopted below. It requires three minor completion assumptions (H001 metal identity, H002 SMA connector model, H003 feedline face). No essential unresolved detail prevents sizing, placing or connecting the required components.

## 4. Semantic interpretations and conflicts

- **Meaning of hgap / "above the groundplane."** The text says the plate is "located hgap = 2 mm above the groundplane" [A006] and "printed on one side … with the groundplane located on the other side" [A002]. "Above" could suggest a vertical (z) stand-off, but Figure 1 draws hgap as an *in-plane* arrow between the plate's feed-side edge and the ground-plane edge, with no stand-off posts or physical z-clearance [A011, A012], and "printed" implies coplanar with the substrate face. Adopted reading: the plate and ground are on **opposite faces** (z-separation = substrate thickness, 1.52 mm), and hgap = 2 mm is the **in-plane offset** that keeps the plate from overlapping the ground. This resolves, rather than conflicts with, the sources.
- **Feedline face.** The text does not state which face the feedline is on; a via-free direct feed to the plate places it on the plate's (front) face (H003). No via is reported, consistent with this.
- **Lateral centering.** The text does not state the feedline/plate width position; Figure 1 shows both centered on the width centerline [A013]. The drawing is not to scale, so this is a figure-supported reading, adopted as the working choice.
- **Symbol correspondence.** The text names the substrate length "l = 90 mm"; Figure 1 labels the same substrate length dimension "h". These are the same 90 mm dimension. "hg" (50 mm) is the ground-plane length, distinct from the substrate length "h/l".

## 5. Reconstruction gaps

**Not reported (non-blocking; left to implementation / material library):**
- Exact feedline length and the plate's absolute longitudinal position / far-edge clearance — set by the reported layout (hg, hgap, hp, substrate length); not given as standalone numbers.
- FR4 dielectric constant / loss — not stated (material-library selection).
- Metallization metal identity — only "35 μm metallization" is reported → H001.
- SMA connector model / mechanical mounting → H002.
- Lateral centering is figure-derived, not text-stated → adopted centered [A013]; not-to-scale caveat.
- Figure 1 has no dedicated region crop in the catalog (region_available: false); the full page 7 was inspected instead.

### Proposed completion assumptions

| ID | Missing or ambiguous detail | Working choice | Basis and uncertainty | Affected component or relationship |
|---|---|---|---|---|
| H001 | Metallization metal not named (only "35 μm metallization") | Copper foil, 35 μm thick, for plate, ground plane and feedline | 35 μm is the standard 1-oz copper PCB foil, conventional for FR4 printed antennas; paper does not name the metal | Plate, ground plane, feedline |
| H002 | SMA connector model/mounting not specified (only "using an SMA connector") | Standard coaxial SMA, center conductor bonded to the microstrip end and outer conductor to the ground, mounted at the feedpoint on the substrate feed edge | Conventional feed for printed microstrip antennas; supplies the external excitation at the feedpoint; paper does not establish the specific connector/mounting | Feed / external excitation |
| H003 | Feedline face not explicitly stated | Feedline printed on the same face as the radiating plate (front face), directly bonded to the plate's feed edge (no via) | A via-free direct feed to the plate requires the feedline on the plate's face; no via is reported; strongly implied, low uncertainty | Feedline placement / plate feed connection |

## 6. Final architecture

**Remaining unresolved details.** No detail prevents sizing, placing, or connecting the required components in this working configuration: the feedline length, the plate's absolute longitudinal position and far-edge clearance are determined by the reported layout values (hg, hgap, hp, substrate length) and are left to the implementation agent; FR4 dielectric properties are left to material-library selection; and H001–H003 supply the metal identity, the SMA connector model, and the feedline face. The adopted configuration is a defensible reading of the reported architecture but is not guaranteed to reproduce every incidental detail of the authors' physical build (e.g., exact SMA mounting, not-to-scale centering).

No blocking reconstruction gaps identified for this working configuration.

**Evidence claims**

- A002 [Reported] A rectangular monopole is printed on one side of an FR4 substrate, with the ground plane on the other side.
  Evidence: p.4, "Antenna Geometry" ("A rectangular monopole is printed on one side of an FR4 substrate with the groundplane located on the other side").
- A006 [Reported] The plate is located hgap = 2 mm above the ground plane.
  Evidence: p.4, "Antenna Geometry" ("It is located hgap=2 mm above the groundplane, as shown in Figure 1").
- A008 [Reported] The metallization thickness is 35 μm.
  Evidence: p.4, "Antenna Geometry" ("the metallization thickness is 35 μm").
- A012 [Visual] In Figure 1, hgap is drawn as an in-plane arrow between the plate's feed-side edge and the ground-plane edge; no stand-off posts or physical z-clearance are depicted.
  Evidence: get_asset asset_id "page:7", inspection_id 38f41a3b7ae541988db4f4f10cb7e4d7, physical page 7.
- A013 [Visual] In Figure 1, the feedline enters at the substrate width center from the feed edge and the plate is centered over it on the width centerline (drawing not to scale).
  Evidence: get_asset asset_id "page:7", inspection_id 38f41a3b7ae541988db4f4f10cb7e4d7, physical page 7.
