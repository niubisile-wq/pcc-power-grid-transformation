"""Audit the frozen B0-B6 semantic validator baselines with explicit gap reporting.

The current public inputs can show the decision-layer behavior on harmful and
lawful cases, but this v2 audit also reports whether the inputs are rich enough
to separate ID-only gating from full PCC on the evidence provided.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from scipy.stats import beta


ROOT = Path(__file__).resolve().parent
DATE = "20260802"
HARMFUL = ROOT / "counterfactual_n1_aliasing_results_20260802.csv"
LAWFUL = ROOT / "physical_split_invariance_results_20260801.csv"
OUT_CSV = ROOT / f"validator_baseline_audit_v2_results_{DATE}.csv"
OUT_JSON = ROOT / f"validator_baseline_audit_v2_summary_{DATE}.json"


BASELINES = {
    "B0_no_validation": lambda record: True,
    "B1_feature_only": lambda record: True,
    "B2_schema_only": lambda record: True,
    "B3_conservation_only": lambda record: True,
    "B4_id_only": lambda record: bool(record.get("identity_match", False)),
    "B5_provenance_signature_without_semantics": lambda record: True,
    "B6_full_PCC": lambda record: bool(record.get("pcc_pass", False)),
}


def ci(k: int, n: int):
    if n == 0:
        return 0.0, 1.0
    if k == 0:
        return 0.0, float(1 - (0.025 ** (1 / n)))
    if k == n:
        return float(0.025 ** (1 / n)), 1.0
    return float(beta.ppf(0.025, k, n - k + 1)), float(beta.ppf(0.975, k + 1, n - k))


def load_harmful_cases(path: Path):
    df = pd.read_csv(path)
    df = df[df["harmful_alias"].astype(bool)].copy()
    df["identity_match"] = df.get("identity_match", False)
    df["pcc_pass"] = df.get("pcc_pass", False)
    return df


def load_lawful_cases(path: Path):
    df = pd.read_csv(path)
    df = df[(df["converged_original"].astype(str).str.lower() == "true") &
            (df["converged_split"].astype(str).str.lower() == "true")].copy()
    df["identity_match"] = df.get("identity_match", False)
    df["pcc_pass"] = df.get("pcc_pass", False)
    return df


def main():
    harmful = load_harmful_cases(HARMFUL)
    lawful = load_lawful_cases(LAWFUL)

    rows = []
    for _, rec in harmful.iterrows():
        record = rec.to_dict()
        record.setdefault("identity_match", False)
        record.setdefault("pcc_pass", False)
        for baseline, rule in BASELINES.items():
            rows.append({
                "case_id": rec["scenario_id"],
                "case_type": "harmful_alias",
                "network": rec["network"],
                "baseline": baseline,
                "accepted": bool(rule(record)),
            })
    for _, rec in lawful.iterrows():
        record = rec.to_dict()
        record.setdefault("identity_match", True)
        record.setdefault("pcc_pass", True)
        for baseline, rule in BASELINES.items():
            rows.append({
                "case_id": f"{rec['case']}:lawful_split:{rec['scenario']}",
                "case_type": "lawful_transform",
                "network": rec["case"],
                "baseline": baseline,
                "accepted": bool(rule(record)),
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
            "harmful_FAR": float(h_accept / len(h)) if len(h) else 0.0,
            "harmful_FAR_95CI_low": h_lo,
            "harmful_FAR_95CI_high": h_hi,
            "lawful_n": int(len(l)),
            "lawful_rejects": l_reject,
            "lawful_FRR": float(l_reject / len(l)) if len(l) else 0.0,
            "lawful_FRR_95CI_low": l_lo,
            "lawful_FRR_95CI_high": l_hi,
        })

    capability = {
        "has_identity_match_field": "identity_match" in harmful.columns or "identity_match" in lawful.columns,
        "has_pcc_pass_field": "pcc_pass" in harmful.columns or "pcc_pass" in lawful.columns,
        "separates_b4_from_b6_on_current_inputs": False,
        "required_missing_fields": [
            field
            for field in [
                "attack_family",
                "identity_relation",
                "certificate_status",
                "graph_signature_hash",
                "semantic_target",
            ]
            if field not in harmful.columns and field not in lawful.columns
        ],
    }

    claim_status = "insufficient_to_separate_id_only_from_full_PCC"
    if capability["separates_b4_from_b6_on_current_inputs"]:
        claim_status = "separable"

    summary = {
        "experiment": "frozen_B0_B6_validator_baseline_audit_v2",
        "date": DATE,
        "harmful_cases": int(len(harmful)),
        "lawful_cases": int(len(lawful)),
        "baselines": summary_rows,
        "capability": capability,
        "claim_status": claim_status,
        "scope_limit": "semantic decision-layer audit; current inputs do not yet prove B4/B6 separability",
        "inputs": [HARMFUL.name, LAWFUL.name],
        "primary_evidence": OUT_CSV.name,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
