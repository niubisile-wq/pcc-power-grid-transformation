"""Run the signed production-style canonicalizer over the public 3,000 lockbox."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from h39_canonicalizer import ACCEPT, REJECT_INCONSISTENT, CanonicalizationRejected, Canonicalizer, digest

ROOT = Path(__file__).resolve().parent
def main():
    rows = []
    # Reuse the already generated lockbox manifest.  No network reconstruction
    # is needed for a certificate-property test, which keeps this layer fast
    # and prevents PF construction cost from hiding verifier behavior.
    with (ROOT / "public_3000_lockbox_results_20260801.csv").open(encoding="utf-8", newline="") as f:
        scenarios = list(csv.DictReader(f))
    for r in scenarios:
            case = r["case"]; j = int(r["scenario_id"].split("-")[-1]); total = float(r["load_min"])
            assets = {f"{case}:load:0": {"asset_type": "load", "p_mw": total * .4, "q_mvar": total * .1, "bus": 0}, f"{case}:load:1": {"asset_type": "load", "p_mw": total * .6, "q_mvar": total * .15, "bus": 1}}
            snapshot = {"schema": "public-ieee-lockbox-v1", "scenario_id": r["scenario_id"], "assets": assets}
            c = Canonicalizer(snapshot)
            source = next(iter(assets)); target_a = source + ":a"; target_b = source + ":b"
            source_asset = assets[source]
            split_values = {target_a: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2}, target_b: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2}}
            legal = c.issue_split(source, [target_a, target_b], values=split_values)
            legal_decision = c.verify(legal)
            tampered = dict(legal); tampered["target_ids"] = [target_a, target_b, source + ":tampered"]
            tampered_decision = c.verify(tampered)
            try:
                c.issue_merge(list(assets)[:2], source + ":merged", values={"p_mw": 0.0, "q_mvar": 0.0})
                merge_rejected = False
            except CanonicalizationRejected:
                merge_rejected = True
            source_ids = list(assets)[:2]; target_id = source + ":lawful_merged"
            proof = digest({"snapshot": c.snapshot_hash, "source_ids": sorted(source_ids), "target_id": target_id})
            merged = c.issue_merge(source_ids, target_id, values={"p_mw": sum(assets[s]["p_mw"] for s in source_ids), "q_mvar": sum(assets[s]["q_mvar"] for s in source_ids)}, identity_equivalence_proof=proof)
            valid_merge_decision = c.verify(merged)
            rows.append({"case": case, "scenario": j, "legal_split": legal_decision.status, "tampered_signature_rejected": tampered_decision.status == REJECT_INCONSISTENT, "feature_only_merge_rejected": merge_rejected, "lawful_merge": valid_merge_decision.status})
    out = ROOT / "canonicalizer_3000_property_results_20260801.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {"n": len(rows), "legal_split_accepts": sum(r["legal_split"] == ACCEPT for r in rows), "lawful_merge_accepts": sum(r["lawful_merge"] == ACCEPT for r in rows), "tampered_signature_rejects": sum(r["tampered_signature_rejected"] for r in rows), "feature_only_merge_rejects": sum(r["feature_only_merge_rejected"] for r in rows), "signed_ed25519": True, "limitations": ["public substitute lockbox", "asset-level property audit, not downstream model inference"]}
    (ROOT / "canonicalizer_3000_property_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
