# EPSR figure QA report

Status: **pass**  
Backend: **Python only**  
Reviewed outputs: five 600-dpi PNG previews and five Python-generated grayscale previews.  
Automated evidence: `figure_qa.json`.

## Export and integrity checks

- Five expected figure stems are present in SVG, PDF, and PNG formats (15 exports).
- SVG files retain editable `<text>` nodes and contain no replacement-character glyphs.
- PDF font records are embedded; Matplotlib used `pdf.fonttype = 42`.
- PNG dimensions exceed the automated minimum of 3,000 × 1,800 pixels.
- Fifteen clean CSV source-data tables are present and content-hashed in `figure_source_manifest.json`.
- Hashes of every figure export match the source manifest.
- Numeric assertions pass: full PCC harmful acceptance is zero, lawful acceptance is one, the DC heatmap sums to 369, and untouched-import element counts sum to 59.

## Visual review

- **Figure 1:** Workflow direction, semantic-change boundary, trusted obligations, three-state decision, solver boundary, and receipt are legible. No arrows or labels are clipped. Grayscale remains interpretable through labels, shape, and topology rather than colour alone.
- **Figure 2:** Heatmap counts, baseline labels, Wilson intervals, zero-event annotation, and Holm-adjusted paired evidence are legible. Harmful and lawful series retain distinct marker shapes and line styles in grayscale.
- **Figure 3:** Paired-valid and retained outcomes remain distinct through hatching. Network labels, clustered intervals, medians, exact sign-test text, prevention counts, and zero-start markers do not overlap after revision.
- **Figure 4:** All 50 heatmap cells are visible and sum to the strict denominator. Loading, shedding, and cost panels preserve their distinct units; the symmetric-log load-shedding axis retains the near-zero case73 value. The first draft’s bottom-caption collision was removed.
- **Figure 5:** Structural/PCC decisions use different marker shapes; DCP is hatched and DCMP solid; imported-element counts are annotated; p50/p95 use both marker shape and line identity. The maximum-error annotation and scaling endpoint remain inside their panels after revision.

## Claim and scope checks

- No panel presents controlled mutations as field prevalence.
- No panel labels legacy alias-overlimit rows as strict false-secure rows.
- No panel claims full QoCDC compliance or APL conformance for the untouched holdout.
- Cross-solver agreement is explicitly conditioned on transformer-aware equation alignment.
- Figure 1 retains the conditional trust boundary and does not claim protection against issuer compromise, incomplete contracts, verifier defects, or gate bypass.
