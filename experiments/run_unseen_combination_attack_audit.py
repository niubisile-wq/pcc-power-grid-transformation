"""Unseen combination-attack audit for the fail-closed certificate verifier."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

from scipy.stats import beta

from h39_contract_reference import make_fixture, reference_signature, verify_certificate
from run_protocol_audit import mutate


ROOT = Path(__file__).resolve().parent
DATE = "20260803"
OUT_CSV = ROOT / f"unseen_combination_attack_results_{DATE}.csv"
OUT_JSON = ROOT / f"unseen_combination_attack_summary_{DATE}.json"
N_PER = 1000

ATTACKS = [
    ("combo_provenance_task_version", ["provenance_forge", "task_escalation", "version_downgrade"]),
    ("combo_id_chain", ["source_id_collision", "chain_digest_tamper"]),
    ("combo_signature_target", ["signature_strip", "target_rewrite"]),
    ("combo_empty_relation", ["empty_target", "relation_type_replacement"]),
    ("combo_unknown_provenance", ["unknown_source", "provenance_forge"]),
    ("combo_chain_signature", ["chain_append", "signature_tamper"]),
    ("combo_authorization_signature", ["missing_authorization", "signature_tamper"]),
    ("combo_version_task_id", ["version_downgrade", "task_escalation", "source_id_collision"]),
]


def checker(cert):
    return cert.get("signature") == reference_signature(cert)


def ci_upper_zero(n):
    return 1.0 - 0.025 ** (1 / n)


def main():
    snapshot, base = make_fixture()
    rows = []
    for index, (name, mutations) in enumerate(ATTACKS, start=1):
        for repeat in range(N_PER):
            cert = copy.deepcopy(base)
            for mutation in mutations:
                cert = mutate(cert, mutation)
            result = verify_certificate(snapshot, cert, expected_version="h39-v1", requested_task="PF", signature_checker=checker)
            accepted = int(result.decision == "ACCEPT")
            rows.append({
                "attack_id": f"U{index:02d}",
                "run_id": f"U{index:02d}-{repeat:04d}",
                "attack_class": name,
                "mutation_chain": "+".join(mutations),
                "actual_decision": result.decision,
                "attack_success": accepted,
                "reasons": ";".join(result.reasons),
                "status": "PASS" if not accepted else "FAIL",
            })
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_attack = []
    for name, mutations in ATTACKS:
        subset = [r for r in rows if r["attack_class"] == name]
        accepted = sum(r["attack_success"] for r in subset)
        by_attack.append({"attack_class": name, "mutation_chain": "+".join(mutations),
                          "n": len(subset), "accepted": accepted,
                          "upper_95_if_zero": ci_upper_zero(len(subset)) if accepted == 0 else None})
    summary = {
        "experiment": "unseen_combination_attacks",
        "date": DATE,
        "attack_classes": len(ATTACKS),
        "trials_per_class": N_PER,
        "total_trials": len(rows),
        "total_accepts": sum(r["attack_success"] for r in rows),
        "by_attack": by_attack,
        "scope_limit": "protocol-level unseen combination audit; not power-grid downstream validation",
        "primary_evidence": OUT_CSV.name,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
