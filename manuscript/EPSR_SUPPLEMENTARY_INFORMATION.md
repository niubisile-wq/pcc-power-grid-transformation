# Supplementary information

## S1. Evidence hierarchy and promotion rule

The study separates immutable inputs and per-run records (Layer A), deterministic summaries and tables (Layer B), and manuscript claims (Layer C). A Layer C claim is admitted only when its required gate in `protocols/epsr_submission_gate_v1.yaml` is ready. `reject` and `unresolved` decisions never launch the protected solver. Failed, timed-out, nonconvergent, and superseded attempts remain in the evidence archive and are not silently deleted from attempted denominators.

The final dashboard reports nine of nine evidence families ready. The clean-room workflow rebuilds the DC statistics, evidence dashboard, and manuscript tables; runs the regression suite; and verifies both content-addressed locks. The final audit passed 71 tests with three environment-conditioned skips.

## S2. Statistical analysis and denominator rules

The network is the confirmatory inference unit. Candidate-outage and operating-state rows within a network are treated as repeated descriptive measurements, not independent population replicates. Continuous effects are summarized by medians and interquartile ranges. Uncertainty intervals are obtained with a hierarchical network-cluster bootstrap using the frozen seed and repetition count recorded in each machine summary. Directional replication across networks is tested with a one-sided exact sign test. Binary paired baseline comparisons use exact McNemar tests with Holm multiplicity correction. Zero-event harmful-start bounds use one-sided exact binomial confidence limits.

For AC N-1, 53 of 56 attempts are paired-valid; three failed case300 attempts remain retained. For AC-OPF, 25 of 35 attempts are paired-valid; ten nonconvergent pairs remain retained. For DC-SCOPF, the strict false-secure definition requires a valid optimal full/alias pair, full-model loading no greater than 1.0001 p.u., and alias-model loading greater than 1.0001 p.u. The strict analysis contains 369 rows. The archive separately retains 38 invalid paired-solver rows, 50 rows that exacerbate an already overloaded baseline, and the broader legacy count of 477 reported alias-overlimit rows.

## S3. Case500 numerical amendment chain

The scientific design—networks, states, candidate outages, costs, network equations, PCC gate, activity threshold, and terminal all-candidate feasibility requirement—was not relaxed. Amendments v2–v11 addressed computational tractability and numerical certification for case500, while every unsuccessful or superseded attempt remained archived.

| Revision | Purpose | Outcome retained in final archive |
| --- | --- | --- |
| v2 | Active-screening amendment for the large case | Screening logic and amendment record |
| v3 | Exact constraint generation | Timeout attempts and checkpoint retained |
| v4 | Clarabel adjudication | Numerical-error attempt retained |
| v5 | Top-one constraint generation | Partial attempt and diagnostic retained |
| v6 | Clarabel/HiGHS optimal-face validation | Cross-solver validation records retained |
| v7 | Hybrid exact-solver route | Timeout attempt and checkpoint retained |
| v8 | Clarabel solver portfolio | Portfolio diagnostic retained |
| v9 | Clarabel base formulation | Parent for the full formulation |
| v10 | Full Clarabel SCOPF formulation | Exposed inactive-constraint dual noise at offset 7 |
| v11 | Tight-dual precision amendment | Final ten-state case500 protocol |

In v10 offset 7, a constraint with approximately 0.30 p.u. primal slack carried a dual magnitude of 3.43 × 10⁻⁷, exceeding the unchanged 10⁻⁷ activity threshold and conservatively classifying all 582 candidates as active. The preregistered v11 diagnostic tightened solver tolerances without changing the activity threshold. Inactive dual noise fell to 3.87 × 10⁻⁹, and 15 active candidates were independently supported by both dual magnitude and primal slack. The final case500 run evaluated 5,820 rows across ten states, identified 85 strict false-secure dispatches, prevented all 85, and required no last-resort fallback.

## S4. Semantic baseline ladder

All baselines receive the same 660 lawful and 1,320 harmful transformations across 22 public networks. Structural-only and signed-artifact baselines accept every harmful transformation. Adding global identity reduces harmful acceptance to 880; task-footprint coverage reduces it to 440; attribute invariants reduce it to 220; and full snapshot-bound PCC reduces it to zero. Every baseline accepts all 660 lawful controls. These ordered results isolate the incremental protection supplied by each evidence obligation.

This ladder is a decomposition of residual risk, not a claim that each component was measured by a fully orthogonal knock-out experiment. The interpretation is still strong because each added obligation removes a distinct family of harmful acceptance while preserving all lawful controls in the frozen scope.

| Ladder step | Added obligation | Harmful family removed | Remaining residual risk |
| --- | --- | --- | --- |
| B0 -> B1 | Signed artifact binding | None | Signature alone cannot prove semantics |
| B1 -> B2 | Global identity coverage | `wrong_one_to_many`, `target_id_reuse` | Wrong task coverage still passes |
| B2 -> B3 | Task-footprint coverage | `task_asset_drop`, `independent_merge` | Parameter drift and stale bindings remain |
| B3 -> B4 | Attribute invariants | `required_attribute_changed:*` except source-snapshot mismatch | Snapshot mismatch still passes |
| B4 -> B5 | Full snapshot / relation / trace / intervention binding | `source_snapshot_mismatch` | No observed harmful acceptance remains |

## S5. Operational effects

PCC prevented all 53 paired-valid consequential AC N-1 launches, all 25 paired-valid consequential AC-OPF launches, and all 369 strict DC false-secure launches. No harmful protected-solver start was observed. The corresponding conventional median effects were 3.879 percentage points of N-1 loading error, 5.96% relative AC-OPF objective effect, and 0.241 p.u. hidden DC post-contingency loading excess. DC false-secure rows additionally had a median 5.20 MW hidden load-shedding requirement and 1.04% relative cost understatement. All network-level median effects were positive in the declared analyses.

The operator-facing reason taxonomy is paired with this effect evidence to support repairability: the dominant DC reasons point directly to task-asset mapping and missing-target restoration, and the frozen semantic benchmark shows provenance-only repair restoring all 288 harmful cases before re-verification.

## S6. Standards, holdout, and solver portability boundaries

The official Svedala EQBD control conforms to the selected APL 1.1.1 SHACL shapes with zero validation results. A byte-identical target is nevertheless PCC-rejected when one of eight task assets lacks authoritative identity evidence. The QoCDC control covers only the 15 implemented Level 1–4 checks; Levels 5–8 and full QoCDC compliance are not claimed.

The untouched ten-file PowSyBl bundle is task-lawful under the bounded eight-asset PCC projection and imports in pypowsybl 1.15.0 as 59 reported network elements. Its raw APL 1.1.1 merged-graph result is separately nonconforming (761 violations and four information results); no global APL-conformance claim is made.

The unaligned PowerModels `DCPPowerModel` negative control agrees with PYPOWER on all nine statuses but only three of eight mutually optimal objectives at the frozen tolerance. After selecting transformer-aware `DCMPPowerModel`, the independent Julia/PowerModels/HiGHS stack agrees with Windows PYPOWER/PIPS on all nine statuses, all eight mutually optimal objectives, and all eight total-generation values. This correction changes the compared formulation, not the PCC decision logic, and the negative result remains archived.

## S7. Reason-to-repair closure

The frozen semantic benchmark is the repair-loop control. It contains 288 harmful and 288 lawful cases across 18 public networks. `ProofGuidedRepairer` repaired all 288 harmful cases from authoritative converter evidence, and the repaired certificates revalidated successfully. The tests `test_provenance_only_repair_then_gate_execution` and `test_ambiguous_repair_fails_closed` confirm that repair is provenance-only and fail-closed: unique evidence can restore a missing relation, but ambiguous evidence does not permit unsafe reconstruction.

| Reason family | Repair action | Outcome |
| --- | --- | --- |
| `task_selector_not_preserved` | Restore the missing task asset mapping | Repaired and revalidated |
| `task_target_missing` | Regenerate the target with the declared task target present | Repaired and revalidated |
| `independent_task_assets_merged` | Provide authorized aggregate evidence or avoid merge | Fail-closed unless authoritative evidence is unique |
| `target_identity_reused_across_independent_relations` | Reissue with unique target identity or valid many-source proof | Fail-closed unless unique evidence exists |
| `task_asset_unmapped` | Map every task-selected source asset | Repaired through provenance-only restoration |

## S8. Verifier scaling

The single-process, in-memory benchmark excludes solver and network-I/O time, uses five warm-up runs and 30 measured repetitions per size, and records Windows Python 3.12.5 as the environment.

| Task assets | p50 (ms) | p95 (ms) | Maximum (ms) |
| ---: | ---: | ---: | ---: |
| 118 | 1.611 | 1.800 | 2.019 |
| 300 | 3.954 | 4.242 | 4.280 |
| 571 | 7.437 | 8.473 | 11.456 |
| 1,354 | 17.419 | 20.320 | 20.455 |
| 2,869 | 37.965 | 41.759 | 43.507 |
| 9,241 | 129.125 | 142.958 | 143.721 |
| 13,659 | 197.632 | 215.089 | 217.495 |

## S9. Reproduction and source-data map

From the repository root on Windows PowerShell:

```powershell
$env:PYTHONPATH=(Resolve-Path cgmes).Path
py -3.12 experiments/run_dc_scopf_confirmatory_statistics.py
py -3.12 experiments/build_epsr_evidence_dashboard.py
py -3.12 experiments/build_epsr_manuscript_tables.py
powershell -ExecutionPolicy Bypass -File experiments/run_epsr_evidence_audit.ps1 -RequireSubmissionReady
```

The primary machine sources are:

- semantic ladder: `outputs/pcc_v2_semantic_baseline_ladder/summary.json`;
- AC N-1 and AC-OPF: `outputs/pcc_v2_n1_gate/pcc_v2_n1_gate_summary.json` and `outputs/pcc_v2_opf_gate/pcc_v2_opf_gate_summary.json`;
- DC-SCOPF: `outputs/pcc_v2_dc_scopf_statistics/summary.json`;
- scaling: `outputs/pcc_v2_scaling/pcc_v2_scaling_summary.json`;
- standards and holdout: `outputs/cgmes_apl111_pcc_separation/separation_summary.json`, `outputs/qocdc_414_applicable_subset/summary.json`, and `outputs/cgmes_untouched_holdout/holdout_summary.json`;
- cross-environment solver comparison: `outputs/cross_solver_dcmp_validation/cross_solver_dcmp_summary.json`;
- final readiness and audit: `outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json` and `outputs/epsr_clean_room_audit/audit_summary.json`.

Figure-specific source-data tables and hashes are frozen together with the plotting backend and the five final figures after visual and numerical QA.
