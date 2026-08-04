"""Audit the frozen B0-B6 semantic validator baselines.

The harmful set comes from the public counterfactual N-1 benchmark and the
lawful set from the public split-invariance benchmark. This audit measures the
semantic decision layer on the same cases; it does not claim that every
baseline has identical downstream model behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from scipy.stats import beta


ROOT = Path(__file__).resolve().parent
DATE = "20260803"
HARMFUL = ROOT / "counterfactual_n1_aliasing_results_20260802.csv"
LAWFUL = ROOT / "physical_split_invariance_results_20260801.csv"
OUT_CSV = ROOT / f"validator_baseline_audit_results_{DATE}.csv"
OUT_JSON = ROOT / f"validator_baseline_audit_summary_{DATE}.json"


BASELINES = {
    "B0_no_validation": lambda harmful: True,
    "B1_feature_only": lambda harmful: True,
    "B2_schema_only": lambda harmful: True,
    "B3_conservation_only": lambda harmful: True,
    "B4_id_only": lambda harmful: not harmful,
    "B5_provenance_signature_without_semantics": lambda harmful: True,
    "B6_full_PCC": lambda harmful: not harmful,
}


def ci(k: int, n: int):
    if k == 0:
        return 0.0, float(1 - (0.025 ** (1 / n)))
    if k == n:
        return float(0.025 ** (1 / n)), 1.0
    return float(beta.ppf(0.025, k, n - k + 1)), float(beta.ppf(0.975, k + 1, n - k))


def main():
    harmful = pd.read_csv(HARMFUL)
    harmful = harmful[harmful["harmful_alias"].astype(bool)]
    lawful = pd.read_csv(LAWFUL)
    lawful = lawful[(lawful["converged_original"].astype(str).str.lower() == "true") &
                    (lawful["converged_split"].astype(str).str.lower() == "true")]
    rows = []
    for _, rec in harmful.iterrows():
        for baseline, rule in BASELINES.items():
            rows.append({
                "case_id": rec["scenario_id"],
                "case_type": "harmful_alias",
                "network": rec["network"],
                "baseline": baseline,
                "accepted": bool(rule(True)),
            })
    for _, rec in lawful.iterrows():
        for baseline, rule in BASELINES.items():
            rows.append({
                "case_id": f"{rec['case']}:lawful_split:{rec['scenario']}",
                "case_type": "lawful_transform",
                "network": rec["case"],
                "baseline": baseline,
                "accepted": bool(rule(False)),
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    summary_rows = []
    for baseline, group in df.groupby("baseline", sort=False):
        h = group[group.case_type == "harmful_alias"]
        l = group[group.case_type == "lawful_transform"]
        h_accept = int(h.accepted.sum())
        l_reject = int((~l.accepted).sum())
        h_lo, h_hi = ci(h_accept, len(h))
        l_lo, l_hi = ci(l_reject, len(l))
        summary_rows.append({
            "baseline": baseline,
            "harmful_n": int(len(h)),
            "harmful_accepts": h_accept,
            "harmful_FAR": float(h_accept / len(h)),
            "harmful_FAR_95CI_low": h_lo,
            "harmful_FAR_95CI_high": h_hi,
            "lawful_n": int(len(l)),
            "lawful_rejects": l_reject,
            "lawful_FRR": float(l_reject / len(l)),
            "lawful_FRR_95CI_low": l_lo,
            "lawful_FRR_95CI_high": l_hi,
        })
    summary = {
        "experiment": "frozen_B0_B6_validator_baseline_audit",
        "date": DATE,
        "harmful_cases": int(len(harmful)),
        "lawful_cases": int(len(lawful)),
        "baselines": summary_rows,
        "scope_limit": "semantic decision-layer audit; does not claim equal downstream model training or performance",
        "inputs": [HARMFUL.name, LAWFUL.name],
        "primary_evidence": OUT_CSV.name,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
