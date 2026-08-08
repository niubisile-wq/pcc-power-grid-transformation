# EPSR submission checklist

Machine-checkable items are rebuilt by `experiments/run_epsr_evidence_audit.ps1`.
No item below may be marked complete from an interim result.

## Scientific evidence

- [x] Semantic ladder: 22 networks, 1,320 harmful and 660 lawful transformations.
- [x] AC N-1: failures retained, clustered interval, network-level sign test.
- [x] AC-OPF: nonconvergent pairs retained, clustered interval, network-level sign test.
- [x] DC-SCOPF: exact 5 x 10 terminal coverage under the frozen revision chain.
- [x] Independent transformer-aligned solver reproduction.
- [x] Official APL positive control and separately bounded QoCDC subset.
- [x] Untouched CGMES holdout with separate SHACL, PCC, and import reports.
- [x] Scaling through 13,659 assets.
- [x] Final immutable DC lock and clean-room audit.

## Reporting discipline

- [x] Strict false-secure definition requires a valid optimal full/alias pair,
  full loading <=1.0001, and alias loading >1.0001.
- [x] Legacy alias-overlimit labels and invalid solver outcomes are retained and
  reported separately.
- [x] Network is the confirmatory unit; candidate/state rows are repeated measures.
- [x] APL, QoCDC subset, PCC, and PowSyBl import claims remain separate.
- [x] Superseded case500 v2-v10 failures, timeouts, and amendments remain visible.
- [x] Replace every final DC value only from the final machine summaries.
- [x] Freeze five final figures and verify every plotted value against a JSON/CSV source.

## Elsevier package

- [x] Abstract below 250 words.
- [x] Five highlights, each <=85 characters.
- [x] No more than seven keywords.
- [x] Final title page: author names, affiliations, corresponding-author email.
- [x] Author-confirmed CRediT statement.
- [x] Author-confirmed funding statement.
- [x] Author-confirmed competing-interest declaration.
- [x] Data/code availability statement with the final immutable archive DOI/version.
- [x] Main manuscript, editable figures, source-data manifest, and supplement prepared; graphical abstract only if requested by the journal.
- [x] Cover letter stating problem, method, successful solution, and practical value.
