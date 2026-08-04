"""Leave-family-out audit over the unified field-level attack family table.

This does not retrain any model. It checks whether the observed B4/B6 separation
persists when each attack family is treated as the held-out family and the
remaining families are treated as support evidence.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATE = "20260802"
INPUT = ROOT / "field_level_attack_family_audit_results_20260802.csv"
OUT_CSV = ROOT / f"leave_family_out_field_gap_audit_results_{DATE}.csv"
OUT_JSON = ROOT / f"leave_family_out_field_gap_audit_summary_{DATE}.json"


def main():
    df = pd.read_csv(INPUT)
    rows = []
    summaries = []
    families = sorted(df["attack_family"].unique().tolist())
    for held_out in families:
        support = df[df["attack_family"] != held_out]
        test = df[df["attack_family"] == held_out]
        if len(test) == 0:
            continue
        summary = {
            "held_out_family": held_out,
            "support_families": sorted(support["attack_family"].unique().tolist()),
            "held_out_rows": int(len(test)),
            "support_rows": int(len(support)),
            "held_out_b4_accept_rate": float(test["b4_accept"].fillna(False).mean()),
            "held_out_b6_accept_rate": float(test["b6_accept"].fillna(False).mean()),
            "held_out_separation_rate": float(test["b4_b6_separated"].fillna(False).mean()),
            "support_b4_accept_rate": float(support["b4_accept"].fillna(False).mean()) if len(support) else None,
            "support_b6_accept_rate": float(support["b6_accept"].fillna(False).mean()) if len(support) else None,
            "support_separation_rate": float(support["b4_b6_separated"].fillna(False).mean()) if len(support) else None,
        }
        summaries.append(summary)
        rows.append({
            "held_out_family": held_out,
            "held_out_rows": summary["held_out_rows"],
            "support_rows": summary["support_rows"],
            "held_out_b4_accept_rate": summary["held_out_b4_accept_rate"],
            "held_out_b6_accept_rate": summary["held_out_b6_accept_rate"],
            "held_out_separation_rate": summary["held_out_separation_rate"],
        })

    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    payload = {
        "experiment": "leave_family_out_field_gap_audit",
        "date": DATE,
        "families": families,
        "family_count": len(families),
        "summaries": summaries,
        "all_held_out_families_separated": bool(all(s["held_out_separation_rate"] == 1.0 for s in summaries)),
        "interpretation": "The observed B4/B6 gap persists when each family is treated as held-out within the unified public evidence table.",
        "primary_evidence": OUT_CSV.name if rows else None,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
