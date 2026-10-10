# Baseline architecture report excerpt

Source paper: Lara Fernandez et al., *Design of a Deployable Helix Antenna at
L-Band for a 1-Unit CubeSat: From Theoretical Analysis to Flight Model Results*,
*Sensors* 22 (2022), 3633. [DOI: 10.3390/s22103633](https://doi.org/10.3390/s22103633).
The title and DOI are present in the run's converted document.

- Workflow: baseline, with prepared Markdown and a single visual-asset request.
- Execution: `run_20260921T162507+0100_16771d1e`, architecture stage on
  21 September 2026.
- Original artefact: `architecture/architecture_evidence_report.md` within that
  run. The matching execution record reports `succeeded` and passing structural
  diagnostics; neither establishes scientific correctness.
- Producing code revision: unverified. See the [trace summary](trace-summary.md#provenance)
  for recorded identities, hashes and the limited Git-history correspondence.

This is an **excerpt**, retaining claims A001, A011, A018, A022 and A026 and the
**complete original reconstruction-gaps section**. Text below "Published excerpt"
is copied verbatim, including punctuation, classifications and claim
identifiers. Other claims are omitted; references to their identifiers still
refer to the complete original report. The original run remains local and is
not included in this repository.

`Reported`, `Visual` and `Derived` are the model's labels. They distinguish
source statements, model-generated image observations and inferred conclusions;
they are not independent verification. A026 is labelled `Reported` but includes
a suggested typo interpretation. A011 explicitly infers continuity between
stages. A022 preserves an unidentified part and an unconfirmed interpretation.
No new engineering assumptions or corrections have been added to the output.
The gaps preserve what the agent considered missing, ambiguous or unresolved.

Textual evidence refers to the converted paper's section and table labels.
The trace confirms retrieval of `figure_12`, cited in A022; its manifest associates
that crop with physical PDF page 14. These references document evidence access,
not the accuracy of the generated visual observations.

## Published excerpt

## 1. Selected antenna

- A001 [Reported] The final design supported by the paper is the Flight Model (FM) of the L-Band Helix Antenna (LHA), a single deployable monofilar helical antenna element (not an array) with an integrated ground plane (GP), operating for 1227.6–1575.42 MHz (GPS L2, radiometry 1400–1427 MHz, GPS L1/Galileo E1) with left-hand circular polarization (LHCP). It is part of the Nadir Antenna and Deployment Subsystem (NADS) of the FMPL-1 payload on the ³Cat-4 1U CubeSat. The companion uplooking RHCP antenna of FMPL-1 is outside the paper's scope.
  Evidence: Abstract ("a downlooking Left Hand Circular Polarization (LHCP) L-Band Helix Antenna (LHA)... included in the Nadir Antenna and Deployment Subsystem (NADS)"); Section 6.1 ("The Flight Model of the LHA is included within the Nadir Antenna and Deployment Subsystem (NADS)"); Section 2 (Table 1 requirements, incl. R006 LHCP).

## 2. Components, materials and layers

- A011 [Derived] Material discontinuity between stages: the FM helix is tin-plated spring steel (vs. Steel 1008 assumed in simulation) and the FM GP is aluminum 7075 with Surtec 650 Alodine (vs. 35 μm copper in simulation; vs. aluminum plate or FR-4/copper in the EM). Geometric continuity with the Section 3 design is inferred, not re-stated in Section 6 (see A012, A017 and the gaps in Section 5).
  Evidence: Section 4.1 vs. Section 6.1 and Table 13 (inference combining both).

## 3. Geometry, dimensions and feeding

- A018 [Reported] In the FM, "the GP had to be slightly reduced, since it was not possible to integrate the 94 by 98 mm GP." The exact final GP (aluminum shield) footprint and cup depth are not given (see A026 and Section 5).
  Evidence: Section 6.1.

- A022 [Visual] figure_12 (extruded/exploded view of the NADS) shows the spatial arrangement in deployed state: at the near end, the aluminum shield (a cup/box-shaped machined structure) with brass fingers (thin spring-like strips) projecting from it; a gold-colored deployment-board PCB mounted on the front face of the shield; beyond it, the helix antenna enclosed in a translucent cylindrical fabric sheath (helix turns visible through the sheath); a small cross-shaped stage board located at mid-length inside the sheath; at the far end, a white cylindrical gravity boom with an internal cross structure; a small disc-shaped boom holder beyond the boom. A circular flange-like part is visible on the front face of the shield; it is not labeled in the figure and does not appear in the part list (identity not established — possibly the feed connector or an interface, not confirmed).
  Evidence: figure_12 (received asset), labeled arrows and visible geometry.

## 4. Derivations and conflicts

- A026 [Reported] Conflict on the pre-reduction FM GP size: Sections 4.2 and 5.4 give the CubeSat/cubic-cup GP as 94 mm × 90 mm, while Section 6.1 says the unintegrable GP was "94 by 98 mm." One of the two dimension pairs is likely a typo; under either reading the FM GP is slightly smaller than the simulated 94 × 90 mm cup, and the exact final dimensions are not reported.
  Evidence: Section 4.2 ("94 mm by 90 mm GP"); Section 5.4 ("94 mm by 90 mm and a height of 20 mm"); Section 6.1 ("not possible to integrate the 94 by 98 mm GP").

## 5. Reconstruction gaps

- The exact shape and dimensions of the FM ground plane (aluminum shield) are not given: no cup depth, opening size, or shield drawing is provided; only the statement that the GP was "slightly reduced" (A018, A026) and the subsystem envelopes (A004). Whether the FM shield geometrically equals the EM cubic cup (94 × 90 × 20 mm) is not stated.
- Section 6 does not restate the FM helix diameter d, turn spacing S, turn count N, or coil cross-section Ø; continuity with Table 3 (d = 61.8 mm, S = 46 mm, N = 11, Ø = 1 mm) is inferred from the design lineage and from the deployed subsystem height (515 mm vs. A = 506 mm), not explicitly confirmed. The FM wire cross-section is therefore not directly evidenced.
- Feed details are incomplete: connector type, feed position along the shield, and the transition from soldered wire to the deployment board/RF path are not described; only the tin plating for soldering to an "output connector" (A019) and the simulation feed model (A009) are given. The unlabeled circular flange on the shield front in figure_12 (A022) may be related but is unidentified.
- Deployment-mechanism geometry (brass finger dimensions and kinematics, stage-board location/dimensions, gravity boom and boom holder dimensions, PTFE dielectric constant of the boom) is not quantified in this paper; the mechanism is deferred to references [34] and [35], which are not part of the supplied material. The gravity boom's "slight" directivity contribution is qualitative only.
- The FM twist handedness (left-hand) is not restated in Section 6; it is carried over from the theoretical stage (Section 3) and is consistent with the LHCP requirement and measured AR (A016), but the paper does not explicitly state the FM winding direction.
- Minor labeling gaps: Figure 15(d) is captioned "Radiation at 1575 MHz" while Table 14 uses 1575.42 MHz; the Table 14 column is labeled "Directivity (dB)" for a chamber measurement that also reports gain, without specifying how directivity was obtained.
- No image or text defines the FM in the stowed configuration (only dimensions); the stowed-state geometry (coil winding, finger engagement, sheath state) is not visually documented in the received assets.
- Requirement R007 (≥ 12 dB reflection loss in 1400–1427 MHz) is met only marginally in the FM (S11 ≈ −12.0/−12.1 dB at 1.400/1.427 GHz, A020); this is a performance boundary, not an architecture gap, but it should be preserved when canonicalizing the validation status.
