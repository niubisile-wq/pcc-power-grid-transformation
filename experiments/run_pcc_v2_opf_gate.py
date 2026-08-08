"""PCC v2 runtime admission around public-network AC-OPF scenarios."""

from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path
import statistics
import sys

import pandapower.networks as pn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_counterfactual_opf_aliasing import build_pair, solve_opp  # noqa: E402
from validation.execution_gate import ExecutionGate  # noqa: E402
from validation.pcc_v2 import PCCV2Verifier, TaskContract, issue_v2_certificate  # noqa: E402


OUTPUT = ROOT / "outputs" / "pcc_v2_opf_gate"
CASE_FACTORIES = {
    "case5": pn.case5,
    "case9": pn.case9,
    "case14": pn.case14,
    "case24_ieee_rts": pn.case24_ieee_rts,
    "case30": pn.case30,
    "case39": pn.case39,
    "case57": pn.case57,
    "case118": pn.case118,
    "case145": pn.case145,
    "case300": pn.case300,
}


def semantic_snapshot(asset_ids):
    return {
        "assets": {
            asset_id: {
                "asset_type": "generator",
                "p_mw": 1.0,
                "outage_capable": True,
                "controllable": True,
            }
            for asset_id in asset_ids
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="+", choices=sorted(CASE_FACTORIES))
    parser.add_argument("--output-tag", default="")
    args = parser.parse_args()
    if args.output_tag and not all(character.isalnum() or character in "-_" for character in args.output_tag):
        raise ValueError("output tag must contain only letters, digits, hyphen, or underscore")
    output = OUTPUT if not args.output_tag else ROOT / "outputs" / f"pcc_v2_opf_gate_{args.output_tag}"
    output.mkdir(parents=True, exist_ok=True)
    selected = args.cases or [
        "case5",
        "case9",
        "case14",
        "case24_ieee_rts",
        "case30",
        "case39",
        "case57",
        "case118",
        "case145",
        "case300",
    ]
    cases = [(name, CASE_FACTORIES[name]) for name in selected]
    factors = [0.005, 0.01, 0.02, 0.03, 0.05]
    key = Ed25519PrivateKey.generate()
    rows = []

    for case_name, factory in cases:
        for factor in factors:
            scenario = f"{case_name}:generator-identity-opf:f{factor:g}"
            row = {
                "network": case_name,
                "stress_factor": factor,
                "scenario_id": scenario,
                "correct_converged": False,
                "alias_converged": False,
            }
            source = semantic_snapshot(["asset-A", "asset-B"])
            lawful_target = semantic_snapshot(["asset-A-prime", "asset-B-prime"])
            lawful_task = TaskContract(
                task_id=scenario,
                task_kind="AC_OPF",
                source_assets=("asset-A", "asset-B"),
                target_assets=("asset-A-prime", "asset-B-prime"),
                intervention_type="outage",
                required_attributes=("asset_type", "p_mw"),
                tolerances={"p_mw": 1e-12},
            )
            lawful_relations = []
            lawful_trace = []
            for source_id, target_id in (("asset-A", "asset-A-prime"), ("asset-B", "asset-B-prime")):
                lawful_relations.append({
                    "source_ids": [source_id],
                    "target_ids": [target_id],
                    "relation_type": "rename",
                    "authoritative_evidence": {"kind": "signed_converter_trace"},
                    "intervention_map": {source_id: [target_id]},
                })
                lawful_trace.append({
                    "source_id": source_id,
                    "target_ids": [target_id],
                    "relation_type": "rename",
                    "authoritative": True,
                    "evidence_kind": "signed_converter_trace",
                })
            lawful_cert = issue_v2_certificate(
                source,
                lawful_target,
                task_contract=lawful_task,
                relations=lawful_relations,
                converter_trace=lawful_trace,
                issuer="opf-adapter",
                private_key=key,
                certificate_id="lawful:" + scenario,
                transformation_id="lawful:" + scenario,
                issued_at="2026-08-06T00:00:00Z",
                nonce="lawful:" + scenario,
            )
            try:
                correct, g1, _g2, _bus, _p = build_pair(factory, factor)
                correct.gen.at[g1, "in_service"] = False
                correct_gate = ExecutionGate(
                    PCCV2Verifier(trusted_issuers={"opf-adapter": key.public_key()})
                ).execute(
                    source,
                    lawful_target,
                    lawful_cert,
                    requested_task="AC_OPF",
                    converter_trace=lawful_trace,
                    solver=lambda _snapshot, net=correct: solve_opp(net),
                )
                row["correct_gate_decision"] = correct_gate.receipt.decision
                row["correct_solver_status"] = correct_gate.receipt.solver_status
                if correct_gate.receipt.solver_status == "completed":
                    row["correct_converged"] = True
                    for key_name, value in correct_gate.result.items():
                        row["correct_" + key_name] = value
            except Exception as exc:
                row["correct_error"] = type(exc).__name__ + ": " + str(exc)[:240]

            try:
                alias, alias_g1, alias_g2, _bus, p = build_pair(factory, factor)
                alias.gen.at[alias_g1, "p_mw"] = 2 * p
                alias.gen.at[alias_g2, "in_service"] = False
                alias.gen.at[alias_g1, "in_service"] = False
                alias_result = solve_opp(alias)
                row["alias_converged"] = True
                for key_name, value in alias_result.items():
                    row["alias_" + key_name] = value
            except Exception as exc:
                row["alias_error"] = type(exc).__name__ + ": " + str(exc)[:240]
                alias = None

            harmful_target = semantic_snapshot(["asset-AB"])
            harmful_task = TaskContract(
                task_id=scenario,
                task_kind="AC_OPF",
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
                issuer="opf-adapter",
                private_key=key,
                certificate_id="harmful:" + scenario,
                transformation_id="harmful:" + scenario,
                issued_at="2026-08-06T00:00:00Z",
                nonce="harmful:" + scenario,
            )
            harmful_calls = []

            def gated_alias_solver(_snapshot):
                harmful_calls.append(scenario)
                if alias is None:
                    raise RuntimeError("alias_preparation_failed")
                return solve_opp(copy.deepcopy(alias))

            harmful_gate = ExecutionGate(
                PCCV2Verifier(trusted_issuers={"opf-adapter": key.public_key()})
            ).execute(
                source,
                harmful_target,
                harmful_cert,
                requested_task="AC_OPF",
                converter_trace=harmful_trace,
                solver=gated_alias_solver,
            )
            row["harmful_gate_decision"] = harmful_gate.receipt.decision
            row["harmful_gate_reasons"] = ";".join(harmful_gate.receipt.reasons)
            row["harmful_solver_status"] = harmful_gate.receipt.solver_status
            row["harmful_solver_calls"] = len(harmful_calls)
            if row["correct_converged"] and row["alias_converged"]:
                row["absolute_cost_regret"] = abs(row["correct_cost"] - row["alias_cost"])
                row["relative_cost_regret"] = row["absolute_cost_regret"] / max(abs(row["correct_cost"]), 1e-12)
                row["max_loading_delta"] = abs(row["correct_max_loading"] - row["alias_max_loading"])
                row["unsafe_result_prevented"] = bool(
                    (row["absolute_cost_regret"] > 1e-9 or row["max_loading_delta"] > 1e-6)
                    and harmful_gate.receipt.solver_status == "not_started"
                )
            rows.append(row)

    fields = sorted({key for row in rows for key in row})
    with (output / "pcc_v2_opf_gate_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    paired = [row for row in rows if row["correct_converged"] and row["alias_converged"]]
    consequential = [
        row for row in paired
        if row.get("absolute_cost_regret", 0.0) > 1e-9 or row.get("max_loading_delta", 0.0) > 1e-6
    ]
    summary = {
        "experiment": "pcc_v2_end_to_end_ac_opf_gate",
        "attempted": len(rows),
        "paired_valid": len(paired),
        "consequential_aliases": len(consequential),
        "harmful_solver_starts": sum(row["harmful_solver_calls"] for row in rows),
        "unsafe_results_prevented": sum(bool(row.get("unsafe_result_prevented")) for row in rows),
        "prevention_rate_among_consequential": (
            sum(bool(row.get("unsafe_result_prevented")) for row in rows) / len(consequential)
            if consequential else None
        ),
        "median_relative_cost_regret": (
            statistics.median(row["relative_cost_regret"] for row in paired) if paired else None
        ),
        "max_relative_cost_regret": max((row["relative_cost_regret"] for row in paired), default=None),
        "scope": "public-network AC-OPF consequence plus runtime admission gate",
    }
    (output / "pcc_v2_opf_gate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
