# EPSR execution master

## Outcome

The target paper is an applied method paper: a transformed power-system model can pass task-agnostic checks yet alter the assets and semantics required by N-1, OPF, or SCOPF. PCC v2 binds task scope and transformation evidence to a fail-closed solver launch, so harmful inputs are rejected or left unresolved before computation while lawful transformations remain executable.

Working title: *Task-semantic proof-carrying validation prevents unsafe execution of transformed power-system models*.

## Frozen paper logic

1. Problem: structural/profile validation does not establish preservation of a downstream study's task-relevant identities, relations, endpoints, parameters, and snapshot.
2. Gap: provenance signatures and task-agnostic conservation checks can authenticate the wrong transformed semantics.
3. Method: a three-state PCC v2 verifier checks the task footprint, relation cardinality and independence, endpoint/parameter semantics, source/target hashes, trace, nonce, and Ed25519 signature.
4. Operational mechanism: only `accept` launches the solver; `reject` and `unresolved` fail closed; every launch produces a receipt bound to the verified inputs.
5. Evidence: controlled semantic attacks establish mechanism, AC N-1/OPF/DC-SCOPF quantify avoided consequences, official CGMES tests establish orthogonality, and a second solver stack tests portability.
6. Value: the result is prevented false-secure or economically distorted execution, not a catalogue of failed data conversions.

## Evidence layers

- Layer A — immutable raw evidence: public inputs, downloaded standard artifacts, per-run rows, failure records, hashes, licenses, and environment captures.
- Layer B — deterministic derived evidence: summaries, exact statistics, figures, tables, and the readiness dashboard.
- Layer C — manuscript claims: statements admitted only when the corresponding machine-readable gate passes.

## Current audit baseline

- Repository regression: 71 tests pass and 3 environment-conditioned tests skip under the final Python 3.12 clean-room audit with `PYTHONPATH=cgmes`.
- Semantic lock: protocol, PCC implementation, execution gate, evidence schema, repair logic, semantic runner, and three semantic outputs still match the 2026-08-06 hashes.
- DC lock warning: `dc_scopf_protocol_v1.yaml` and the DC runner changed after the old lock to implement transformer-explicit loader revision v2. The old lock is historical and must not authenticate the new DC campaign.
- Semantic baselines: across 1,320 harmful transformations, harmful accepts fall 1,320 -> 880 -> 440 -> 220 -> 0 as global identity, task footprint, attribute invariants, and full signed snapshot binding are added; all six baselines accept 660/660 lawful transformations. Exact paired McNemar tests use Holm correction.
- Application confirmation: N-1 has 53 paired-valid states across eight positive network medians (network sign p=0.00390625). AC-OPF has 25 paired-valid states across five positive network medians after the preregistered case9 extension (network sign p=0.03125); ten nonconvergent pairs remain in the denominator.
- DC confirmation: all five networks are 10/10 under transformer-explicit loader v2 and the frozen case500 v11 precision amendment. The final aggregate contains 50/50 terminal states and 12,340 rows; 369 strictly paired false-secure dispatches were all prevented with zero selected terminal failures and zero harmful solver starts. All five network medians are positive for hidden loading, load shedding, and cost understatement (one-sided exact sign p=0.03125 for each).
- Official separation: ENTSO-E CAS 3.0.3 Svedala EQBD is APL 1.1.1 SHACL-conforming with zero results; a byte-identical target with incomplete proof for one of eight PF task assets is PCC-rejected before solver launch.
- QoCDC scope: the CGMES 2.4.15 development control passes all 15 locally implemented Level 1-4 subset checks and both targeted negative controls are detected; Levels 5-8 remain explicitly unimplemented and full QoCDC compliance is not claimed.
- Holdout: the PowSyBl core commit `4e8024e...c4ffb` was frozen before tree inspection; mechanical selection produced a 10-file CGMES3 MicroGrid bundle with zero byte-identical members in the prior corpus. PCC lawful/missing-proof controls and pypowsybl 1.15.0 native import are complete; the raw merged APL result is retained separately.
- Environment/portability: official Julia 1.12.6 is installed under its fixed SHA-256. The frozen WSL stack contains PowerModels 0.21.6, JuMP 1.31.1, Ipopt 1.15.0, and HiGHS 1.24.1. The transformer-aware DCMPPowerModel correction passes all nine status pairs and all eight mutually optimal objective/generation comparisons, with maxima 4.70e-12 and 8.29e-15 respectively. The unaligned DCP result is retained as a negative formulation control.
- Untouched holdout: PowSyBl core commit `4e8024e` was frozen before inspection and mechanically yielded a 10-file CGMES3 bundle. PCC passes the complete eight-asset proof and fail-closes the missing-proof control; pypowsybl 1.15.0 imports 59 network elements. The raw merged APL 1.1.1 run is nonconforming (761 violations, four infos) and is reported separately with profile-scope/RDFS diagnostics; no global-conformance claim is made.
- Submission readiness: all 9/9 machine evidence families are ready; the semantic and DC locks verify, the deterministic rebuild passes, and the final clean-room audit passes. Remaining work is figure production, final archive freeze, and author-supplied submission metadata; no scientific evidence gate remains open.
- Competitive reconnaissance and the same-tier experimental bar are frozen in `EPSR_COMPETITIVE_LANDSCAPE_20260807.md`; its central recommendation is to frame PCC as a task-semantic, fail-closed operational safety gate rather than as another CGMES converter or a failure audit.

## Execution order

1. Version control: create a new DC execution lock containing protocol, runner, environment, input-case hashes, and per-state terminal-record hashes. Preserve the old semantic lock unchanged.
2. Standards: archive APL 1.1.1 and QoCDC 4.1.4 with checksums/licenses; implement the applicable validation ladder and explicit exclusions.
3. Orthogonality: establish one official conforming positive control and one standard-pass/PCC-reject task-semantic transformation.
4. Semantic statistics: execute the full fair baseline ladder and component ablations; generate exact paired inference and clustered uncertainty.
5. Physical confirmation: re-audit N-1 and OPF statistics; finish the frozen 5×10 DC-SCOPF grid using one case-state per process and bounded memory.
6. Portability: install and freeze the WSL Julia/PowerModels stack, then run paired cases without changing the PCC decision logic.
7. Holdout: freeze an untouched public CGMES set before inspection and retain every terminal outcome.
8. Paper: regenerate five figures and four tables from Layer B only; aggressively remove legacy GridSFM/LUMINA material from the main narrative.
9. Release: clean-room reproduction, source-data archive, data-availability statement, author checklist, and final evidence-to-claim audit.

## Terminology ledger

| Preferred term | Meaning | Avoid |
|---|---|---|
| task-semantic preservation | preservation of the identities and relations required by a declared study | generic semantic correctness |
| harmful transformation | controlled transformation that violates the frozen task contract | attack prevalence in field data |
| unsafe release | a harmful input admitted to solver execution | solver failure |
| prevented false-secure dispatch | a false-secure DC-SCOPF result that would have run without the gate but was stopped before launch | improved solver accuracy |
| unresolved | insufficient evidence; fail closed | reject, unless a violation is proven |
| official standard check | a separately reported applicable RDFS/SHACL/QoCDC decision | PCC baseline replacement |

## Stop conditions for submission

Submission is prohibited while any of the following holds: fewer than 50 DC terminal records; DC comparable fraction below 90%; any harmful solver start; no official conforming control; no standard-pass/PCC-reject orthogonal case; no second-solver result; no untouched holdout; unresolved numeric conflict between the manuscript and generated dashboard; or a failed clean-room reproduction.
