"""Run the protocol-level E0/E1/E5 audit for the reference verifier.

This audit is deliberately labelled synthetic/protocol-level. It does not
replace the missing power-grid, PF/OPF, GridSFM or LUMINA-2M experiments.
"""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

from h39_contract_reference import (
    ACCEPT,
    REJECT_INCOMPLETE,
    REJECT_INCONSISTENT,
    make_fixture,
    reference_signature,
    verify_certificate,
)


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "protocol_audit_results_20260801.csv"
SUMMARY = ROOT / "protocol_audit_summary_20260801.json"
N_PER_ATTACK = 10_000


def signed(cert: dict) -> dict:
    cert["signature"] = reference_signature(cert)
    return cert


def mutate(base: dict, attack_class: str) -> dict:
    cert = copy.deepcopy(base)
    if attack_class == "missing_provenance":
        cert.pop("provenance_hash")
    elif attack_class == "missing_authorization":
        cert.pop("authorized_tasks")
    elif attack_class == "relation_type_replacement":
        cert["relation_type"] = "unauthorized_relation"
    elif attack_class == "version_downgrade":
        cert["contract_version"] = "h39-v0"
    elif attack_class == "provenance_forge":
        cert["provenance_hash"] = "0" * 64
    elif attack_class == "source_id_collision":
        cert["source_ids"] = ["a1", "a1"]
    elif attack_class == "signature_strip":
        cert.pop("signature")
    elif attack_class == "signature_tamper":
        cert["signature"] = "tampered"
    elif attack_class == "chain_digest_tamper":
        cert["chain_digest"] = "0" * 64
    elif attack_class == "task_escalation":
        cert["authorized_tasks"] = ["OPF"]
    elif attack_class == "unknown_source":
        cert["source_ids"] = ["unknown"]
    elif attack_class == "empty_target":
        cert["target_ids"] = []
    elif attack_class == "chain_append":
        cert["composition_chain"].append("attacker-node")
    elif attack_class == "target_rewrite":
        cert["target_ids"] = ["attacker-target"]
    else:
        raise ValueError(attack_class)
    return cert


def checker(cert: dict) -> bool:
    return cert.get("signature") == reference_signature(cert)


def main() -> None:
    snapshot, base = make_fixture()
    attacks = [
        "missing_provenance",
        "missing_authorization",
        "relation_type_replacement",
        "version_downgrade",
        "provenance_forge",
        "source_id_collision",
        "signature_strip",
        "signature_tamper",
        "chain_digest_tamper",
        "task_escalation",
        "unknown_source",
        "empty_target",
        "chain_append",
        "target_rewrite",
    ]
    fields = [
        "attack_id", "run_id", "seed", "attack_class", "expected_decision",
        "actual_decision", "attack_success", "reasons", "requested_task",
        "contract_version", "signature_valid", "verifier_version", "status",
    ]
    rows = []
    clean_accepts = 0
    for seed in range(1000):
        result = verify_certificate(
            snapshot, base, expected_version="h39-v1", requested_task="PF",
            signature_checker=checker,
        )
        if result.decision == ACCEPT:
            clean_accepts += 1

    attack_successes = 0
    for attack_index, attack_class in enumerate(attacks):
        for repeat in range(N_PER_ATTACK):
            seed = attack_index * N_PER_ATTACK + repeat
            cert = mutate(base, attack_class)
            result = verify_certificate(
                snapshot, cert, expected_version="h39-v1", requested_task="OPF"
                if attack_class == "task_escalation" else "PF",
                signature_checker=checker,
            )
            success = result.decision == ACCEPT
            attack_successes += int(success)
            rows.append({
                "attack_id": f"A{attack_index + 1:02d}",
                "run_id": f"A{attack_index + 1:02d}-{repeat:05d}",
                "seed": seed,
                "attack_class": attack_class,
                "expected_decision": "REJECT",
                "actual_decision": result.decision,
                "attack_success": int(success),
                "reasons": ";".join(result.reasons),
                "requested_task": "OPF" if attack_class == "task_escalation" else "PF",
                "contract_version": cert.get("contract_version", "<missing>"),
                "signature_valid": int(checker(cert)),
                "verifier_version": "reference-20260801",
                "status": "PASS" if not success else "FAIL",
            })

    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    by_attack = {}
    for attack_class in attacks:
        subset = [r for r in rows if r["attack_class"] == attack_class]
        by_attack[attack_class] = {
            "n": len(subset),
            "accepted": sum(r["attack_success"] for r in subset),
            "rejected": sum(r["attack_success"] == 0 for r in subset),
        }
    summary = {
        "audit_type": "synthetic_protocol_level",
        "verifier_version": "reference-20260801",
        "clean_trials": 1000,
        "clean_accepts": clean_accepts,
        "attack_classes": len(attacks),
        "trials_per_attack_class": N_PER_ATTACK,
        "attack_trials": len(rows),
        "attack_successes": attack_successes,
        "attack_success_rate": attack_successes / len(rows),
        "by_attack_class": by_attack,
        "not_a_power_grid_result": True,
        "missing_h39_experiments": ["H39 PF/OPF lockbox", "H39 GridSFM/LUMINA paired views", "CGMES/SimBench lockbox", "H39 OOD networks", "H39 runtime scale registry"],
        "public_substitute_audits_available": ["GridSFM-Open", "LUMINA-2M", "pandapower IEEE", "SimBench"],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
