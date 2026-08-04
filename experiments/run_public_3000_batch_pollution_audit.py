"""Audit batch pollution on the public 3,000 lockbox substitute."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandapower as pp

from h39_canonicalizer import ACCEPT, Canonicalizer, canonical_json, digest

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "public_3000_batch_pollution_audit_results_20260803.csv"
SUMMARY = ROOT / "public_3000_batch_pollution_audit_summary_20260803.json"

CASES = [
    ("case14", pp.networks.case14()),
    ("case30", pp.networks.case30()),
    ("case57", pp.networks.case57()),
]
N_PER_CASE = 1000
SEED = 20260801


def build_snapshot(case_name: str, base, base_loads, scenario_index: int, case_offset: int):
    rng = np.random.default_rng(SEED + case_offset * 1_000_000 + scenario_index)
    net = copy.deepcopy(base)
    if len(net.load):
        multipliers = rng.uniform(0.80, 1.20, len(net.load))
        net.load["p_mw"] = base_loads["p_mw"].to_numpy() * multipliers
        net.load["q_mvar"] = base_loads["q_mvar"].to_numpy() * multipliers
    assets = {}
    for i, item in net.load.iterrows():
        assets[f"{case_name}:load:{i}"] = {
            "asset_type": "load",
            "bus": int(item.bus),
            "p_mw": float(item.p_mw),
            "q_mvar": float(item.q_mvar),
            "identity": f"public-{case_name}-{scenario_index:04d}:load:{i}",
        }
    snapshot = {"schema": "public-ieee-lockbox-v1", "scenario_id": f"public-{case_name}-{scenario_index:04d}", "assets": assets}
    return snapshot, Canonicalizer(snapshot), assets


def make_split(canon: Canonicalizer, assets: dict, source_id: str, suffix: str = "") -> dict:
    source_asset = assets[source_id]
    target_ids = [f"{source_id}:part0{suffix}", f"{source_id}:part1{suffix}"]
    split_values = {
        target_ids[0]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
        target_ids[1]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
    }
    return canon.issue_split(source_id, target_ids, values=split_values)


def make_merge(canon: Canonicalizer, assets: dict, source_ids: list[str], suffix: str = "") -> dict:
    target_id = source_ids[0] + f":merged{suffix}"
    proof = digest({"snapshot": canon.snapshot_hash, "source_ids": sorted(source_ids), "target_id": target_id})
    merge_values = {
        "p_mw": sum(assets[s]["p_mw"] for s in source_ids),
        "q_mvar": sum(assets[s]["q_mvar"] for s in source_ids),
    }
    return canon.issue_merge(source_ids, target_id, values=merge_values, identity_equivalence_proof=proof)


def batch_verify(certs: list[dict], canon: Canonicalizer) -> tuple[bool, str]:
    if not certs:
        return False, "empty_batch"
    seen_digests = set()
    provenance = None
    contract_version = None
    signer = None
    source_union = set()
    for cert in certs:
        decision = canon.verify(cert, requested_task="PF")
        if decision.status != ACCEPT:
            return False, "individual:" + decision.status + ":" + ";".join(decision.reasons)
        cert_digest = digest(cert)
        if cert_digest in seen_digests:
            return False, "duplicate_certificate"
        seen_digests.add(cert_digest)
        if provenance is None:
            provenance = cert["provenance_hash"]
            contract_version = cert["contract_version"]
            signer = cert["signer_public_key"]
        else:
            if cert["provenance_hash"] != provenance:
                return False, "mixed_provenance"
            if cert["contract_version"] != contract_version:
                return False, "mixed_version"
            if cert["signer_public_key"] != signer:
                return False, "mixed_signer"
        current_sources = tuple(cert["source_ids"])
        if any(s in source_union for s in current_sources):
            return False, "source_collision"
        source_union.update(current_sources)
    return True, "batch_accept"


def main() -> None:
    rows = []
    timings = {"clean_pair": [], "duplicate_replay": [], "mixed_polluted": [], "mixed_snapshot": []}
    for case_offset, (case_name, base) in enumerate(CASES):
        base_loads = base.load[["bus", "p_mw", "q_mvar"]].copy()
        for j in range(N_PER_CASE):
            snapshot, canon, assets = build_snapshot(case_name, base, base_loads, j, case_offset)
            ids = list(assets)
            if len(ids) < 2:
                continue
            split_a = make_split(canon, assets, ids[0], suffix="")
            split_b = make_split(canon, assets, ids[1], suffix="")
            clean_batch = [split_a, split_b]

            duplicate_batch = [split_a, split_a]

            polluted_cert = canon.issue_merge(
                ids[:2],
                ids[0] + ":polluted_merge",
                values={"p_mw": assets[ids[0]]["p_mw"] + assets[ids[1]]["p_mw"], "q_mvar": assets[ids[0]]["q_mvar"] + assets[ids[1]]["q_mvar"]},
                identity_equivalence_proof=digest({"snapshot": canon.snapshot_hash, "source_ids": sorted(ids[:2]), "target_id": ids[0] + ":polluted_merge"}),
            )
            polluted_cert["relation_type"] = "feature_only_merge"
            polluted_cert["signature"] = canon.private_key.sign(canonical_json({k: v for k, v in polluted_cert.items() if k != "signature"}).encode("utf-8")).hex()
            polluted_batch = [split_a, polluted_cert]

            other_case_index = (case_offset + 1) % len(CASES)
            other_case_name, other_base = CASES[other_case_index]
            other_base_loads = other_base.load[["bus", "p_mw", "q_mvar"]].copy()
            other_snapshot, other_canon, other_assets = build_snapshot(other_case_name, other_base, other_base_loads, j, other_case_index)
            other_ids = list(other_assets)
            other_split = make_split(other_canon, other_assets, other_ids[0], suffix="")
            mixed_snapshot_batch = [split_a, other_split]

            for batch_name, batch in [
                ("clean_pair", clean_batch),
                ("duplicate_replay", duplicate_batch),
                ("mixed_polluted", polluted_batch),
                ("mixed_snapshot", mixed_snapshot_batch),
            ]:
                t0 = time.perf_counter()
                accepted, reason = batch_verify(batch, canon if batch_name != "mixed_snapshot" else canon)
                elapsed = time.perf_counter() - t0
                timings[batch_name].append(elapsed)
                rows.append({
                    "scenario_id": f"public-{case_name}-{j:04d}",
                    "case": case_name,
                    "batch_name": batch_name,
                    "accepted": int(accepted),
                    "reason": reason,
                    "batch_size": len(batch),
                    "elapsed_ms": elapsed * 1000.0,
                    "batch_signature_digest": hashlib.sha256(canonical_json([digest(c) for c in batch]).encode("utf-8")).hexdigest(),
                })

    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "audit_type": "public_3000_batch_pollution_audit",
        "verifier": "batch_verify(public wrapper over h39_canonicalizer)",
        "scenario_count": len(rows) // 4,
        "case_counts": {case: sum(r["case"] == case for r in rows if r["batch_name"] == "clean_pair") for case, _ in CASES},
        "batch_results": {
            name: {
                "n": sum(r["batch_name"] == name for r in rows),
                "accepted": sum(r["batch_name"] == name and r["accepted"] == 1 for r in rows),
                "rejected": sum(r["batch_name"] == name and r["accepted"] == 0 for r in rows),
            }
            for name in ["clean_pair", "duplicate_replay", "mixed_polluted", "mixed_snapshot"]
        },
        "batch_acceptance_rate": {
            name: sum(r["batch_name"] == name and r["accepted"] == 1 for r in rows) / sum(r["batch_name"] == name for r in rows)
            for name in ["clean_pair", "duplicate_replay", "mixed_polluted", "mixed_snapshot"]
        },
        "latency_ms": {
            name: {
                "p50": float(np.percentile(np.asarray(timings[name], dtype=float), 50) * 1000.0),
                "p95": float(np.percentile(np.asarray(timings[name], dtype=float), 95) * 1000.0),
                "p99": float(np.percentile(np.asarray(timings[name], dtype=float), 99) * 1000.0),
            }
            for name in timings
        },
        "limitations": [
            "public IEEE/pandapower substitute, not H39 original lockbox",
            "batch wrapper is an explicit audit harness, not a production batch protocol",
            "mixed_snapshot uses public substitute scenarios from different cases",
        ],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
