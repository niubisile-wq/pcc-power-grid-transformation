# EPSR figure contracts

## Figure 1

Core conclusion: A transformed model reaches the protected solver only when a signed, task-bound proof-obligation contract verifies the exact snapshots, relations, attributes, trace, and intervention semantics.

Figure archetype: schematic-led composite.  
Target journal/output: EPSR, double-column, editable SVG + PDF + 600-dpi PNG.  
Backend: Python.  
Final size: 183 × 112 mm.

Panel map:

- a: Shows how a parseable transformation can change the computational task before optimization.
- b: Shows the PCC certificate obligations and trusted boundary.
- c: Shows the three-state fail-closed gate and input-bound execution receipt.

Evidence hierarchy: the gate mechanism is the hero evidence; proof obligations validate the mechanism; explicit excluded threats bound the claim.  
Statistics needed: none.  
Source data needed: verifier/gate schema and manuscript Sections 3–4.  
Image-integrity notes: native vector primitives only; no adapted images.  
Reviewer risk: the diagram must not imply security against compromised issuers, incomplete task contracts, verifier defects, or bypass of the protected gate.

## Figure 2

Core conclusion: Conventional controls progressively reduce harmful acceptance but only full snapshot-bound PCC eliminates every controlled harmful release while retaining every lawful transformation.

Figure archetype: quantitative grid.  
Target journal/output: EPSR, double-column, editable SVG + PDF + 600-dpi PNG.  
Backend: Python.  
Final size: 183 × 116 mm.

Panel map:

- a: Attack-family × baseline acceptance heatmap identifies the residual semantic failure class at each layer.
- b: Aggregate harmful acceptance rates with Wilson intervals and lawful-acceptance reference show the monotone protection ladder.
- c: Adjacent absolute-risk reductions and exact paired-test evidence show which added obligations change release behavior.

Evidence hierarchy: aggregate harmful acceptance is primary; attack-family localization explains mechanism; paired inference is robustness evidence.  
Statistics needed: Wilson 95% intervals, exact paired McNemar tests, Holm correction, one-sided zero-event upper bound.  
Source data needed: frozen semantic-ladder summary JSON.  
Image-integrity notes: all values exported to source CSV; no raster manipulation.  
Reviewer risk: controlled mutation results must not be presented as natural field prevalence.

## Figure 3

Core conclusion: PCC prevents every observed consequential AC N-1 and AC-OPF computation, and the counterfactual physical and economic effects replicate directionally across networks.

Figure archetype: asymmetric quantitative composite.  
Target journal/output: EPSR, double-column, editable SVG + PDF + 600-dpi PNG.  
Backend: Python.  
Final size: 183 × 128 mm.

Panel map:

- a: Attempt accounting distinguishes paired-valid results from retained failures/nonconvergence.
- b: Network medians show N-1 loading effects across eight networks and the clustered overall interval.
- c: Network medians show AC-OPF relative cost effects across five networks and the clustered overall interval.
- d: Prevention summary contrasts consequential releases stopped with harmful protected-solver starts.

Evidence hierarchy: network-level physical/economic effects are primary; attempt accounting prevents denominator ambiguity; the solver-start endpoint closes the operational claim.  
Statistics needed: hierarchical network-cluster bootstrap, one-sided exact network sign tests.  
Source data needed: frozen application-statistics summary JSON.  
Image-integrity notes: all values exported to source CSV.  
Reviewer risk: failed/nonconvergent attempts must remain visible, and candidate states must not be treated as independent inference units.

## Figure 4

Core conclusion: Across the complete five-network, 50-state DC-SCOPF grid, false-secure dispatches are heterogeneous but recurrent, have positive physical/economic effects in every network, and are all stopped before execution.

Figure archetype: quantitative grid with heatmap hero.  
Target journal/output: EPSR, double-column, editable SVG + PDF + 600-dpi PNG.  
Backend: Python.  
Final size: 183 × 135 mm.

Panel map:

- a: Network × operating-state heatmap shows all 369 strict false-secure rows.
- b: Network medians show hidden post-contingency loading excess.
- c: Network medians show hidden load shedding on a symmetric-log scale to retain the near-zero case73 value.
- d: Network medians show relative cost understatement.

Evidence hierarchy: complete state-grid coverage is primary; the three effect panels demonstrate operational consequence; strict/legacy denominator accounting is a control.  
Statistics needed: hierarchical network-cluster bootstrap and one-sided exact network sign tests.  
Source data needed: frozen DC-SCOPF statistics summary JSON.  
Image-integrity notes: heatmap cells and effect values exported to source CSV.  
Reviewer risk: legacy alias-overlimit, invalid solver pairs, and already-overloaded baselines must not be relabelled as strict false-secure rows.

## Figure 5

Core conclusion: PCC supplies a task-semantic layer that is orthogonal to structural standards, reproduces across transformer-aligned solver stacks, works on an untouched CGMES import, and remains subsecond at the largest tested task size.

Figure archetype: asymmetric mixed-evidence composite.  
Target journal/output: EPSR, double-column, editable SVG + PDF + 600-dpi PNG.  
Backend: Python.  
Final size: 183 × 135 mm.

Panel map:

- a: Structural/PCC decision matrix separates the official Svedala control from the untouched holdout.
- b: Solver comparison contrasts the retained unaligned DCP negative control with transformer-aware DCMP reproduction.
- c: Untouched holdout import composition confirms native usability while keeping the raw APL outcome separate.
- d: Verifier p50/p95 latency scales with task-asset count.

Evidence hierarchy: standards orthogonality and formulation-aligned replication are primary validation; untouched import and scaling support practical deployment.  
Statistics needed: agreement fractions and recorded latency quantiles; no inferential test added.  
Source data needed: frozen APL separation, holdout, cross-solver, and scaling summaries.  
Image-integrity notes: vector plots and source CSV only.  
Reviewer risk: do not claim full QoCDC coverage, APL conformance of the holdout, or solver independence without matched transformer equations.

## Figure 4 update note

The revised Figure 4 uses the DC-SCOPF mechanism atlas as its primary figure-source family. The heatmap is generated from `outputs/dc_scopf_mechanism_atlas/false_secure_by_network_state.csv`, the component accounting from `outputs/dc_scopf_mechanism_atlas/false_secure_by_component.csv`, and the retained label accounting from `outputs/dc_scopf_mechanism_atlas/summary.json`. Network-median effect panels remain tied to the frozen DC-SCOPF statistics summary.

## Figure 6

Core conclusion: The external-tool blind roundtrip challenge strengthens external lawfulness and portability controls, but it does not support the central operational-consequence claim because no external-tool-generated task-relevant anomaly and no paired-valid operational consequence were observed.

Figure archetype: quantitative grid with claim-boundary panel.  
Target journal/output: EPSR, double-column, editable SVG + PDF + 600-dpi PNG.  
Backend: Python.  
Final size: 183 x 126 mm.

Panel map:

- a: Frozen challenge accounting shows selected bundles, source import successes, route attempts, successful route artifacts, and PCC receipts.
- b: Terminal route-status accounting shows successes, failures, source-import failures, target-import failures, and dependency failures without outcome-dependent filtering.
- c: PCC endpoint and success-criterion accounting separates lawful exact acceptance and zero harmful starts from unmet task-anomaly and operational-anomaly criteria.
- d: Post-receipt consequence reveal states the paired-valid denominator and the resulting claim boundary.

Evidence hierarchy: challenge and route accounting are primary for blind-protocol integrity; PCC endpoint counts are primary for lawfulness/control evidence; the consequence reveal bounds interpretation.  
Statistics needed: exact numerator/denominator reporting only; no inferential test is promoted because the success criteria were not met.  
Source data needed: frozen external blind summary, route artifact manifest, and consequence summary.  
Image-integrity notes: vector plots and source CSV only.  
Reviewer risk: do not imply that external-tool-generated operational anomalies were observed, and do not place this result in the abstract or central claim.
