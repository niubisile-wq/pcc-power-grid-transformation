from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def main() -> None:
    gate1 = load("roundtrip_asset_mapping_summary.json")
    gate2 = load("full_pcc_identity_only_task_scope_summary.json")
    gate3 = load("natural_roundtrip_operational_replay_summary.json")
    baseline = load("baseline_comparison_summary.json")
    report = f"""# Development Gates 1–3 report

## Outcome

- **Gate 1 — positive:** {gate1['gate1_qualifying_rows']} non-injected, task-relevant
  identity anomaly is frozen in `{gate1['gate1_case_ids'][0]}`. VeraGrid conversion removes
  official branch L3_a while same-parameter peer L3_b remains and no lawful relation is exported.
- **Gate 2 — positive with a bounded task claim:** {gate2['natural_semantic_mutation_cases']}
  natural same-mRID motor-to-generator class mutations are accepted by identity-only and rejected
  by payload-aware full PCC. They create {gate2['misclassified_generator_candidates_avoided_by_pcc']}
  extra generator-N−1 candidates; all corresponding converted-model outage calculations converged.
  This is candidate misclassification, not a demonstrated safety reversal.
- **Gate 3 — positive with an explicit reconstruction limit:** the converted T1 model loses one of
  seven branch contingencies, so named L3_a is not executable and the candidate count falls from
  {gate3['nminus1_reference_candidate_count']} to {gate3['nminus1_converted_candidate_count']}.
  Across {gate3['pf_reference_vs_converted']['aligned_bus_count']} aligned interior buses, the
  official-source-backed reconstruction and converted arms differ by
  {gate3['pf_reference_vs_converted']['max_vm_delta_pu']:.6g} p.u.; the PCC-repaired and parallel
  oracle controls return to {gate3['pf_reference_vs_repaired']['max_vm_delta_pu']:.6g} p.u.

## Evidence boundary

No tested raw-source solver preserved L3_a and completed the comparison. The source arm is therefore
a deterministic reconstruction: it restores official L3_a from its frozen mRID, endpoints and
parameters by copying the independently present, identical L3_b branch. It is not described as a
raw-source solver result. AC-OPF was attempted on all three main arms, but all three attempts were
non-convergent and remain in the denominator; there is no new AC-OPF consequence claim.

The CGMES 2.4.15 package has no applicable official SHACL constraint set in the acquired official
resources. Consequently B2 `cgmes_shacl` is reported as unresolved, not replaced with the local
schema-derived RDFS diagnostic. Natural converter outputs did not natively emit PCC certificates;
the B7 natural decisions use a disclosed post-conversion adapter sidecar.

## Development positioning

The development evidence supports a public-software interoperability claim and a task-aware PCC
claim. It does not establish industry prevalence, field-operation risk, production performance or
independent external replication. Final positioning remains conditional on Stage 5 version,
network-family, toolchain and cross-environment confirmation.

Machine-readable sources: `roundtrip_asset_mapping_summary.json`,
`full_pcc_identity_only_task_scope_results.csv`, `natural_roundtrip_operational_replay.csv`,
`natural_roundtrip_nminus1_contingencies.csv`, and `baseline_comparison_results.csv`.
"""
    (RESULTS / "DEVELOPMENT_GATES_1_3_REPORT.md").write_text(report, encoding="utf-8")
    summary = {
        "gate1_met": bool(gate1["gate1_met"]),
        "gate2_met": bool(gate2["gate2_met"]),
        "gate3_met_with_reconstruction_limit": bool(gate3["gate3_evidence_ready"]),
        "gate3_raw_source_solver_evidence": bool(gate3["gate3_raw_source_solver_evidence"]),
        "acopf_new_evidence": False,
        "holdout_confirmation_complete": False,
        "baseline_cases": baseline["case_count"],
        "positioning": "development-positive; confirmation and cross-environment reproduction pending",
    }
    (RESULTS / "development_gate_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
