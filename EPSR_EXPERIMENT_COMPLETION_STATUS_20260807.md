# EPSR Experiment Completion Status

Date: 2026-08-07

Scope: paper experiments only. Author declarations, submission-system metadata, final archive naming, and publishing logistics are intentionally excluded.

## Overall Status

Experiment status: COMPLETE for the current EPSR core claims.

Post-plan enhancement status: COMPLETE for the experiment-supported parts of the high-impact enhancement plan. The DC-SCOPF mechanism atlas, PCC decision reason taxonomy, external-tool blind roundtrip control, six-figure manuscript package, manuscript tables, and candidate scientific archive are generated and audited. The external-tool blind roundtrip challenge is retained as external lawfulness/portability control evidence only, not as a central operational-consequence claim.

The experiment-side evidence dashboard reports 9/9 ready gates and `submission_ready=true` for the experiment evidence package:

- Source: `outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json`
- Audit: `outputs/epsr_clean_room_audit/audit_summary.json`
- Claim map: `EPSR_CLAIM_EVIDENCE_MATRIX_20260807.md`

Fresh experiment audit command run:

```powershell
powershell -ExecutionPolicy Bypass -File experiments/run_epsr_evidence_audit.ps1 -RequireSubmissionReady
```

Audit result: PASS

- `semantic_confirmatory_lock_v2`: pass
- `regression_suite`: pass, 71 tests run, 3 skipped
- `dc_scopf_statistics_rebuild`: pass
- `dc_scopf_mechanism_atlas_rebuild`: pass
- `pcc_decision_reason_taxonomy_rebuild`: pass
- `external_tool_consequence_adjudication_rebuild`: pass
- `evidence_dashboard_rebuild`: pass
- `manuscript_tables_rebuild`: pass
- `dc_scopf_confirmatory_lock_v2`: pass, 313 locked files checked, all hashes matched

Figure and science-package checks:

- `py -3.12 experiments/build_epsr_figures.py`: 6 figures, 18 exports, 20 source tables
- `py -3.12 experiments/qa_epsr_figures.py`: pass
- `py -3.12 experiments/build_epsr_submission_manifest.py`: `scientific_package_ready=true`, `figures_ready=true`
- `py -3.12 experiments/build_epsr_final_archive_candidate.py`: `missing=[]`, archive candidate hash `bb2748df986d72ddd98a059cceb0b93654bcbb8e0b3c8f3bb64a9614a37ccb12`

## Experiment Gates

| Gate | Status | Main result | Source |
| --- | --- | --- | --- |
| Semantic confirmatory attack matrix | Ready | 660/660 lawful accepted; 1320 harmful cases; full PCC accepted 0 harmful; signed-artifact baseline accepted 1320 harmful | `outputs/pcc_v2_attack_matrix/attack_matrix_summary.json` |
| Semantic baseline ladder | Ready | Harmful acceptance falls from 1320/1320 in B0/B1 to 0/1320 in full PCC; lawful acceptance remains 660/660 | `outputs/pcc_v2_semantic_baseline_ladder/summary.json` |
| AC N-1 execution gate | Ready | 56 attempts; 53 paired-valid completions; 53/53 unsafe harmful runs prevented; 0 harmful solver starts; 3 case300 failures retained | `outputs/pcc_v2_application_statistics/summary.json` |
| AC-OPF execution gate | Ready | 35 attempts; 25 paired-valid pairs; 25/25 consequential harmful runs blocked; 0 harmful solver starts; median relative cost regret 0.0596365 | `outputs/pcc_v2_application_statistics/summary.json` |
| DC-SCOPF confirmatory | Ready | 5 networks x 10 states completed; 12,340 candidate rows; 369 strict false-secure dispatches; all prevented; 0 harmful solver starts | `outputs/pcc_v2_dc_scopf_statistics/summary.json` |
| Scaling | Ready | Largest case has 13,659 assets; p95 verification latency 215.089 ms; all declared targets met | `outputs/pcc_v2_scaling/pcc_v2_scaling_summary.json` |
| Official SHACL / PCC separation | Ready | Official SHACL and PCC are reported as separate evidence families; PCC rejects harmful missing-proof holdout with 0 solver starts | `outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json`, `outputs/cgmes_untouched_holdout/holdout_summary.json` |
| QoCDC 4.1.4 applicable subset | Ready | Implemented levels 1-4 only; 15 checks; positive control passed; negative controls detected; no full-QoCDC-compliance claim | `outputs/qocdc_414_applicable_subset/summary.json` |
| Dual solver cross-environment | Ready | 9 status pairs; 8 mutually optimal pairs; status and objective agreement both 1.0 where mutually optimal; unexplained differences 0 | `outputs/cross_solver_dcmp_validation/cross_solver_dcmp_summary.json` |
| Untouched CGMES holdout | Ready | 10 artifacts; frozen before inspection; PCC result reported separately from official SHACL diagnostics | `outputs/cgmes_untouched_holdout/holdout_summary.json` |

## Locked Evidence

- Semantic confirmatory lock v2 checked 9 files; all hashes matched.
- DC-SCOPF confirmatory lock v2 checked 313 files; all hashes matched.
- DC-SCOPF terminal coverage is complete for case39, case73, case118, case300, and case500, with 10 states per network.
- Superseded/failed DC-SCOPF attempts are retained and disclosed in the statistics output.

## Remaining Experiment Work

No additional experiment reruns are required for the current EPSR core claims.

Additional work remains only if the paper wants to promote the external-tool blind roundtrip challenge into a central high-impact operational-consequence claim:

- A real external route beyond pypowsybl has now been attempted with importable `VeraGridEngine 6.4.3`; it produced one retained target-import-failure artifact and several export failures, but no task-relevant anomaly.
- The frozen external challenge must produce at least one external-tool-generated task-relevant anomaly.
- External CGMES N-1 consequence adjudication must yield paired-valid source-target evaluations; the current post-receipt adjudicator ran but produced 0 paired-valid evaluations.
- The consequence reveal must show at least one operationally consequential external anomaly.

Until those conditions are met, the external blind roundtrip result should remain in Discussion, Limitations, or Supplementary Protocol as external lawfulness/portability control evidence.

The only experiment-side caveats that should remain visible in manuscript text are interpretive boundaries, not missing experiments:

- Semantic attacks are controlled attacks, not field-prevalence estimates.
- AC N-1 and AC-OPF retained nonconvergent/failure cases under the stated failure policy.
- DC-SCOPF row-level effects are descriptive repeated candidate-outage measurements; network is the confirmatory unit.
- QoCDC evidence is an applicable-subset check only, not a full QoCDC compliance assessment.
- Official SHACL diagnostics and PCC admission evidence are distinct and should not be conflated.
