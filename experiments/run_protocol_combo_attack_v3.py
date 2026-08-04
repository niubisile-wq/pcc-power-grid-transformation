"""Denser protocol-level combination attack audit.

This expands the unseen-combination set with more multi-field chains to keep
pressure on the verifier's fail-closed behavior.
"""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

from h39_contract_reference import make_fixture, reference_signature, verify_certificate
from run_protocol_audit import mutate

ROOT = Path(__file__).resolve().parent
DATE = "20260803"
OUT_CSV = ROOT / f"protocol_combo_attack_v3_results_{DATE}.csv"
OUT_JSON = ROOT / f"protocol_combo_attack_v3_summary_{DATE}.json"
N_PER = 500

ATTACKS = [
    ("combo1", ["missing_provenance", "signature_tamper", "task_escalation"]),
    ("combo2", ["missing_authorization", "chain_append", "source_id_collision"]),
    ("combo3", ["provenance_forge", "chain_digest_tamper", "target_rewrite"]),
    ("combo4", ["version_downgrade", "unknown_source", "signature_strip"]),
    ("combo5", ["relation_type_replacement", "empty_target", "signature_tamper"]),
    ("combo6", ["source_id_collision", "provenance_forge", "task_escalation"]),
    ("combo7", ["chain_append", "target_rewrite", "signature_strip"]),
    ("combo8", ["missing_authorization", "version_downgrade", "signature_tamper"]),
    ("combo9", ["unknown_source", "chain_digest_tamper", "relation_type_replacement"]),
    ("combo10", ["missing_provenance", "empty_target", "task_escalation"]),
    ("combo11", ["source_id_collision", "target_rewrite", "version_downgrade"]),
    ("combo12", ["provenance_forge", "missing_authorization", "signature_strip"]),
    ("combo13", ["chain_append", "relation_type_replacement", "version_downgrade"]),
    ("combo14", ["unknown_source", "signature_tamper", "empty_target"]),
    ("combo15", ["missing_provenance", "chain_digest_tamper", "source_id_collision"]),
    ("combo16", ["task_escalation", "target_rewrite", "signature_strip"]),
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
                "attack_id": f"C3{index:02d}",
                "run_id": f"C3{index:02d}-{repeat:04d}",
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
        by_attack.append({
            "attack_class": name,
            "mutation_chain": "+".join(mutations),
            "n": len(subset),
            "accepted": accepted,
            "upper_95_if_zero": ci_upper_zero(len(subset)) if accepted == 0 else None,
        })

    summary = {
        "experiment": "protocol_combo_attack_v3",
        "date": DATE,
        "attack_classes": len(ATTACKS),
        "trials_per_class": N_PER,
        "total_trials": len(rows),
        "total_accepts": sum(r["attack_success"] for r in rows),
        "by_attack": by_attack,
        "scope_limit": "protocol-level combination audit; not power-grid downstream validation",
        "primary_evidence": OUT_CSV.name,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
