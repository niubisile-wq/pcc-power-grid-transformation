"""End-to-end PCC v2 admission experiment around an actual AC N-1 workflow."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

import pandapower.networks as pn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
CGMES = ROOT / "cgmes"
EXPERIMENTS = ROOT / "experiments"
for path in (CGMES, EXPERIMENTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_counterfactual_n1_aliasing import make_pair  # noqa: E402
from validation.execution_gate import ExecutionGate  # noqa: E402
from validation.pcc_v2 import PCCV2Verifier, TaskContract, issue_v2_certificate  # noqa: E402


OUTPUT = ROOT / "outputs" / "pcc_v2_n1_gate"


def snapshot(asset_ids):
    return {
        "assets": {
            asset_id: {
                "asset_type": "generator",
                "p_mw": 1.0,
                "outage_capable": True,
            }
            for asset_id in asset_ids
        }
    }


def relation(source_id, target_id):
    return {
        "source_ids": [source_id],
        "target_ids": [target_id],
        "relation_type": "rename",
        "authoritative_evidence": {"kind": "signed_converter_trace"},
        "intervention_map": {source_id: [target_id]},
    }


def trace(source_id, target_id):
    return {
        "source_id": source_id,
        "target_ids": [target_id],
        "relation_type": "rename",
        "authoritative": True,
        "evidence_kind": "signed_converter_trace",
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ("case9", pn.case9),
        ("case14", pn.case14),
        ("case24_ieee_rts", pn.case24_ieee_rts),
        ("case30", pn.case30),
        ("case39", pn.case39),
        ("case57", pn.case57),
        ("case118", pn.case118),
        ("case300", pn.case300),
    ]
    factors = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10]
    key = Ed25519PrivateKey.generate()
    rows = []

    for case_name, factory in cases:
        for factor in factors:
            try:
                consequence = make_pair(factory, case_name, factor)
            except Exception as exc:
                rows.append({
                    "network": case_name,
                    "stress_factor": factor,
                    "stage": "reference_consequence",
                    "completed": False,
                    "error": type(exc).__name__ + ": " + str(exc)[:300],
                })
                continue
            consequence["completed"] = True
            consequence["error"] = ""
            scenario = consequence["scenario_id"]
            source = snapshot(["asset-A", "asset-B"])

            lawful_target = snapshot(["asset-A-prime", "asset-B-prime"])
            lawful_task = TaskContract(
                task_id=scenario,
                task_kind="N1_AC",
                source_assets=("asset-A", "asset-B"),
                target_assets=("asset-A-prime", "asset-B-prime"),
                intervention_type="outage",
                required_attributes=("asset_type", "p_mw"),
                tolerances={"p_mw": 1e-12},
            )
            lawful_relations = [
                relation("asset-A", "asset-A-prime"),
                relation("asset-B", "asset-B-prime"),
            ]
            lawful_trace = [
                trace("asset-A", "asset-A-prime"),
                trace("asset-B", "asset-B-prime"),
            ]
            lawful_cert = issue_v2_certificate(
                source,
                lawful_target,
                task_contract=lawful_task,
                relations=lawful_relations,
                converter_trace=lawful_trace,
                issuer="n1-adapter",
                private_key=key,
                certificate_id="lawful:" + scenario,
                transformation_id="lawful:" + scenario,
                issued_at="2026-08-06T00:00:00Z",
                nonce="lawful:" + scenario,
            )
            lawful_solver_calls = []

            def lawful_solver(_snapshot):
                lawful_solver_calls.append(scenario)
                return {
                    "correct_contingency_feasible": consequence["correct_contingency_feasible"],
                    "correct_min_voltage": consequence["correct_min_voltage"],
                    "correct_max_loading_percent": consequence["correct_max_loading_percent"],
                }

            lawful_gate = ExecutionGate(
                PCCV2Verifier(trusted_issuers={"n1-adapter": key.public_key()})
            ).execute(
                source,
                lawful_target,
                lawful_cert,
                requested_task="N1_AC",
                converter_trace=lawful_trace,
                solver=lawful_solver,
            )

            harmful_target = snapshot(["asset-AB"])
            harmful_task = TaskContract(
                task_id=scenario,
                task_kind="N1_AC",
                source_assets=("asset-A", "asset-B"),
                target_assets=("asset-AB",),
                intervention_type="outage",
                required_attributes=("asset_type",),
            )
            harmful_relations = [{
                "source_ids": ["asset-A", "asset-B"],
                "target_ids": ["asset-AB"],
                "relation_type": "merge",
                "authoritative_evidence": {"kind": "signed_converter_trace"},
                "intervention_map": {"asset-A": ["asset-AB"], "asset-B": ["asset-AB"]},
            }]
            harmful_trace = [{
                "source_id": "asset-A",
                "target_ids": ["asset-AB"],
                "relation_type": "merge",
                "authoritative": True,
                "evidence_kind": "signed_converter_trace",
            }]
            harmful_cert = issue_v2_certificate(
                source,
                harmful_target,
                task_contract=harmful_task,
                relations=harmful_relations,
                converter_trace=harmful_trace,
                issuer="n1-adapter",
                private_key=key,
                certificate_id="harmful:" + scenario,
                transformation_id="harmful:" + scenario,
                issued_at="2026-08-06T00:00:00Z",
                nonce="harmful:" + scenario,
            )
            harmful_solver_calls = []

            def harmful_solver(_snapshot):
                harmful_solver_calls.append(scenario)
                return {
                    "alias_contingency_feasible": consequence["alias_contingency_feasible"],
                    "alias_min_voltage": consequence["alias_min_voltage"],
                    "alias_max_loading_percent": consequence["alias_max_loading_percent"],
                }

            harmful_gate = ExecutionGate(
                PCCV2Verifier(trusted_issuers={"n1-adapter": key.public_key()})
            ).execute(
                source,
                harmful_target,
                harmful_cert,
                requested_task="N1_AC",
                converter_trace=harmful_trace,
                solver=harmful_solver,
            )
            rows.append({
                **consequence,
                "lawful_gate_decision": lawful_gate.receipt.decision,
                "lawful_solver_status": lawful_gate.receipt.solver_status,
                "lawful_solver_calls": len(lawful_solver_calls),
                "harmful_gate_decision": harmful_gate.receipt.decision,
                "harmful_gate_reasons": ";".join(harmful_gate.receipt.reasons),
                "harmful_solver_status": harmful_gate.receipt.solver_status,
                "harmful_solver_calls": len(harmful_solver_calls),
                "unsafe_result_prevented": bool(
                    consequence["harmful_alias"]
                    and harmful_gate.receipt.solver_status == "not_started"
                ),
            })

    fields = sorted({key for row in rows for key in row})
    with (OUTPUT / "pcc_v2_n1_gate_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    completed = [row for row in rows if row.get("completed")]
    harmful = [row for row in completed if row["harmful_alias"]]
    summary = {
        "experiment": "pcc_v2_end_to_end_n1_gate",
        "attempted": len(rows),
        "completed": len(completed),
        "failed": len(rows) - len(completed),
        "harmful_aliases": len(harmful),
        "lawful_completed": sum(row["lawful_solver_status"] == "completed" for row in completed),
        "harmful_solver_starts": sum(row["harmful_solver_calls"] for row in completed),
        "unsafe_results_prevented": sum(row["unsafe_result_prevented"] for row in completed),
        "prevention_rate_among_harmful": (
            sum(row["unsafe_result_prevented"] for row in completed) / len(harmful) if harmful else None
        ),
        "all_harmful_reasons_include_independent_merge": all(
            "independent_task_assets_merged" in row["harmful_gate_reasons"] for row in completed
        ),
        "failures": [
            {"network": row["network"], "stress_factor": row["stress_factor"], "error": row["error"]}
            for row in rows if not row.get("completed")
        ],
        "scope": "actual public-network AC power-flow consequence plus runtime admission gate",
    }
    (OUTPUT / "pcc_v2_n1_gate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
