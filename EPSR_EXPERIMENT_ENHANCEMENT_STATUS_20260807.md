# EPSR Experiment Enhancement Status

Date: 2026-08-07

Scope: paper experiments only.

## Status

The core EPSR evidence package remains submission-ready: `outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json` reports 9/9 ready core gates and `submission_ready=true`.

Two high-impact enhancements are complete and audited:

- DC-SCOPF mechanism atlas
- PCC decision reason taxonomy
- Six-figure manuscript package with Fig. 4 mechanism atlas and Fig. 6 external blind control

The external-tool blind roundtrip challenge is complete as a retained control experiment, including real pypowsybl and VeraGridEngine route attempts. It is valid as external lawfulness/portability control evidence, but it is not ready for the manuscript central claim because it did not produce an external-tool-generated task-relevant anomaly and the post-receipt N-1 consequence adjudication produced zero paired-valid source-target evaluations.

## Enhancement Results

| Enhancement | Status | Evidence |
| --- | --- | --- |
| DC-SCOPF mechanism atlas | Ready | 12,340 rows; 369 strict false-secure dispatches; 477 legacy alias-overlimit rows; 38 invalid solver pairs retained; 50 exacerbated rows; 369/369 strict cases prevented; 0 harmful solver starts |
| PCC decision reason taxonomy | Ready | 14,447 rows seen; 13,660 rows with reasons; 11 unique reasons; reject/unresolved reasons mapped to operator-facing repair actions |
| External-tool blind roundtrip | Not ready for central claim | 9 selected bundles; 18 route attempts; 7 successful pypowsybl route artifacts; VeraGridEngine 6.4.3 importable with 1 retained target-import-failure artifact; 127 receipts; lawful exact acceptance rate 1.0; harmful solver starts 0; external task anomalies 0; N-1 consequence attempted true; paired-valid consequence evaluated 0 |

## Files Added or Updated

- `experiments/run_external_tool_blind_roundtrip.py`
- `experiments/run_external_tool_consequence_adjudication.py`
- `experiments/build_dc_scopf_mechanism_atlas.py`
- `experiments/build_pcc_decision_reason_taxonomy.py`
- `experiments/select_external_tool_blind_corpus.py`
- `experiments/build_epsr_evidence_dashboard.py`
- `experiments/build_epsr_figures.py`
- `experiments/qa_epsr_figures.py`
- `experiments/run_epsr_evidence_audit.ps1`
- `experiments/manage_dc_scopf_confirmatory_lock_v2.py`
- `experiments/build_epsr_manuscript_tables.py`
- `experiments/build_epsr_submission_manifest.py`
- `experiments/build_epsr_final_archive_candidate.py`
- `outputs/external_tool_blind_roundtrip/`
- `outputs/dc_scopf_mechanism_atlas/`
- `outputs/pcc_decision_reason_taxonomy/`
- `manuscript/figures/fig6_external_tool_blind_roundtrip.*`
- `manuscript/figures/figure_source_manifest.json`
- `cgmes/corpus/external_blind_roundtrip_v1/`
- `protocols/dc_scopf_confirmatory_lock_v2.json`

## Audit

Command:

```powershell
powershell -ExecutionPolicy Bypass -File experiments/run_epsr_evidence_audit.ps1 -RequireSubmissionReady
```

Result: pass.

- Regression suite: 71 tests run, 3 skipped
- DC-SCOPF mechanism atlas rebuild: pass
- PCC decision reason taxonomy rebuild: pass
- External-tool consequence adjudication rebuild: pass
- Evidence dashboard rebuild: pass
- Manuscript tables rebuild: pass
- DC-SCOPF confirmatory lock v2: 313 files checked, all matched

Figure QA:

- `py -3.12 experiments/qa_epsr_figures.py`: pass
- 6 figure stems; 18 SVG/PDF/PNG exports
- 20 source CSV tables
- SVG editable text, PDF embedded fonts, PNG resolution, grayscale contrast, and source assertions all pass

Submission/Archive science package:

- `py -3.12 experiments/build_epsr_submission_manifest.py`: `scientific_package_ready=true`, `figures_ready=true`, `complete_figure_stems=6`
- `submission_package_ready=false` only because author metadata/declarations and final DOI/release tag are intentionally outside this experiment-only scope
- `py -3.12 experiments/build_epsr_final_archive_candidate.py`: `missing=[]`; archive candidate hash `bb2748df986d72ddd98a059cceb0b93654bcbb8e0b3c8f3bb64a9614a37ccb12`

## External Route Detail

VeraGridEngine is no longer a dependency-missing route. `VeraGridEngine 6.4.3` imports in the current Python 3.12 environment, and the route was attempted against the frozen external corpus. The retained route distribution is:

- 7 successful pypowsybl roundtrip artifacts
- 1 VeraGridEngine `target_import_failure` with retained artifact: `outputs/external_tool_blind_roundtrip/route_artifacts/ext05_CGMES_v2.4.15_RealGridTestConfiguration_v2_veragrid_roundtrip.zip`
- 7 VeraGridEngine export failures
- 2 source import failures
- 0 dependency failures

## Claim Boundary

The manuscript can use the completed DC-SCOPF atlas and PCC taxonomy to strengthen mechanism and deployment-facing interpretation.

The external-tool blind roundtrip result should not be promoted to the main operational-consequence claim unless a real external route produces at least one task-relevant anomaly and post-receipt consequence adjudication yields paired-valid operational evidence.
