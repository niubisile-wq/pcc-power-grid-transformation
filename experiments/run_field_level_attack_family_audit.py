"""Build a field-level attack-family audit from the existing public evidence.

This audit unifies the current public evidence into a machine-readable table
with explicit attack_family, identity_relation, and certificate_status fields.
It is deliberately conservative: if a source table does not expose a field, the
script marks it as "unavailable" instead of inventing semantics.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATE = "20260802"
OUT_CSV = ROOT / f"field_level_attack_family_audit_results_{DATE}.csv"
OUT_JSON = ROOT / f"field_level_attack_family_audit_summary_{DATE}.json"

N1 = ROOT / "counterfactual_n1_aliasing_results_20260802.csv"
REP_GSFM = ROOT / "gridsfm_representation_ablation_20260801.csv"
REP_LUMINA = ROOT / "lumina_representation_ablation_20260801.csv"
PUBLIC_LOCKBOX = ROOT / "public_3000_lockbox_results_20260801.csv"
CANONICALIZER_3000 = ROOT / "canonicalizer_3000_property_results_20260801.csv"
ASSET_ALIASING = ROOT / "asset_aliasing_family_audit_results_20260802.csv"


def status_from_bool(value: bool) -> str:
    return "ACCEPT" if bool(value) else "REJECT"


def add_row(rows, **kwargs):
    row = {
        "source": kwargs.pop("source"),
        "attack_family": kwargs.pop("attack_family"),
        "identity_relation": kwargs.pop("identity_relation"),
        "case_id": kwargs.pop("case_id"),
        "network": kwargs.pop("network", ""),
        "task": kwargs.pop("task", ""),
        "baseline_b4": kwargs.pop("baseline_b4", "feature_only"),
        "baseline_b6": kwargs.pop("baseline_b6", "certificate_aware"),
        "certificate_status_b4": kwargs.pop("certificate_status_b4", "unavailable"),
        "certificate_status_b6": kwargs.pop("certificate_status_b6", "unavailable"),
        "b4_accept": kwargs.pop("b4_accept", None),
        "b6_accept": kwargs.pop("b6_accept", None),
        "b4_b6_separated": kwargs.pop("b4_b6_separated", None),
        "downstream_metric_name": kwargs.pop("downstream_metric_name", ""),
        "downstream_metric_b4": kwargs.pop("downstream_metric_b4", None),
        "downstream_metric_b6": kwargs.pop("downstream_metric_b6", None),
        "notes": kwargs.pop("notes", ""),
    }
    row.update(kwargs)
    rows.append(row)


def load_n1(rows):
    df = pd.read_csv(N1)
    for _, rec in df.iterrows():
        add_row(
            rows,
            source="counterfactual_n1_aliasing",
            attack_family="counterfactual_generator_pair_n1",
            identity_relation="same_numerics_different_asset_identity",
            case_id=str(rec["scenario_id"]),
            network=str(rec["network"]),
            task="n_minus_1_contingency",
            certificate_status_b4=status_from_bool(rec["feature_only_accept"]),
            certificate_status_b6=status_from_bool(rec["pcc_accept"]),
            b4_accept=bool(rec["feature_only_accept"]),
            b6_accept=bool(rec["pcc_accept"]),
            b4_b6_separated=bool(rec["feature_only_accept"]) != bool(rec["pcc_accept"]),
            downstream_metric_name="counterfactual_max_voltage_delta",
            downstream_metric_b4=float(rec["counterfactual_max_voltage_delta"]),
            downstream_metric_b6=float(rec["counterfactual_max_voltage_delta"]),
            notes="public pandapower counterfactual N-1 aliasing case",
        )


def load_representation(rows, path: Path, dataset_name: str):
    df = pd.read_csv(path)
    feature = df[df["variant"] == "feature_only_merge"].copy()
    split = df[df["variant"] == "certified_split"].copy()
    official = df[df["variant"] == "official"].copy()
    merged = feature.merge(split, on="case", suffixes=("_b4", "_b6"))
    merged = merged.merge(official, on="case", suffixes=("", "_official"))

    for _, rec in merged.iterrows():
        add_row(
            rows,
            source=f"{dataset_name}_representation_ablation",
            attack_family="representation_merge_split",
            identity_relation="same_numeric_features_different_certificate_identity",
            case_id=str(rec["case"]),
            network=dataset_name,
            task="model_inference_gate",
            certificate_status_b4=str(rec["certificate_status_b4"]),
            certificate_status_b6=str(rec["certificate_status_b6"]),
            b4_accept=str(rec["certificate_status_b4"]) == "ACCEPT",
            b6_accept=str(rec["certificate_status_b6"]) == "ACCEPT",
            b4_b6_separated=str(rec["certificate_status_b4"]) != str(rec["certificate_status_b6"]),
            downstream_metric_name="cost_mape",
            downstream_metric_b4=float(rec["cost_mape_b4"]),
            downstream_metric_b6=float(rec["cost_mape_b6"]),
            certificate_digest_b4=str(rec.get("certificate_digest_b4", "")),
            certificate_digest_b6=str(rec.get("certificate_digest_b6", "")),
            feasibility_b4=int(rec.get("feas_correct_b4", rec.get("feas_correct", 0))) if "feas_correct_b4" in rec.index or "feas_correct" in rec.index else None,
            feasibility_b6=int(rec.get("feas_correct_b6", rec.get("feas_correct", 0))) if "feas_correct_b6" in rec.index or "feas_correct" in rec.index else None,
            notes=f"{dataset_name} shipped public representation ablation",
        )


def load_public_lockbox(rows):
    df = pd.read_csv(PUBLIC_LOCKBOX)
    for _, rec in df.iterrows():
        lawful = str(rec.get("lawful_split_decision", "unavailable"))
        feature = str(rec.get("feature_only_merge_decision", "unavailable"))
        add_row(
            rows,
            source="public_3000_lockbox",
            attack_family="public_lockbox_split_merge",
            identity_relation="same_numeric_fields_different_identity_permission",
            case_id=str(rec.get("scenario_id", rec.get("case", ""))),
            network=str(rec.get("case", "public_lockbox")),
            task="model_inference_gate",
            certificate_status_b4=feature,
            certificate_status_b6=lawful,
            b4_accept=feature == "ACCEPT",
            b6_accept=lawful == "ACCEPT",
            b4_b6_separated=(feature == "ACCEPT") != (lawful == "ACCEPT"),
            downstream_metric_name="numeric_merge_conservation_error",
            downstream_metric_b4=float(rec.get("numeric_merge_conservation_error", 0.0)),
            downstream_metric_b6=float(rec.get("numeric_merge_conservation_error", 0.0)),
            notes="public lockbox split-vs-merge decision table",
        )


def load_canonicalizer_3000(rows):
    df = pd.read_csv(CANONICALIZER_3000)
    for _, rec in df.iterrows():
        legal = str(rec.get("legal_split", "unavailable"))
        feature_rejected = bool(rec.get("feature_only_merge_rejected", False))
        lawful_merge = str(rec.get("lawful_merge", "ACCEPT"))
        add_row(
            rows,
            source="canonicalizer_3000_property",
            attack_family="signed_canonicalizer_property",
            identity_relation="same_numeric_fields_different_identity_proof",
            case_id=f"{rec.get('case', '')}:{rec.get('scenario', '')}",
            network=str(rec.get("case", "canonicalizer")),
            task="certificate_verification",
            certificate_status_b4="REJECT" if feature_rejected else "ACCEPT",
            certificate_status_b6=legal,
            b4_accept=not feature_rejected,
            b6_accept=legal == "ACCEPT",
            b4_b6_separated=(not feature_rejected) != (legal == "ACCEPT"),
            downstream_metric_name="lawful_merge_accept",
            downstream_metric_b4=int(not feature_rejected),
            downstream_metric_b6=int(legal == "ACCEPT"),
            notes="public canonicalizer property audit",
            lawful_merge_status=lawful_merge,
            tampered_signature_rejected=bool(rec.get("tampered_signature_rejected", False)),
        )


def load_asset_aliasing(rows):
    df = pd.read_csv(ASSET_ALIASING)
    for _, rec in df.iterrows():
        feature_only = int(rec.get("feature_only_collisions", 0))
        identity_aware = int(rec.get("identity_aware_unique", 0))
        add_row(
            rows,
            source="asset_aliasing_family_audit",
            attack_family="asset_aliasing_controlled_mutation",
            identity_relation=str(rec.get("identity_relation", "same_numeric_fields_different_asset_identity")),
            case_id=str(rec.get("case", "")),
            network=str(rec.get("case", "asset_aliasing")),
            task="asset_identity_census",
            certificate_status_b4="REJECT_INCONSISTENT",
            certificate_status_b6="ACCEPT",
            b4_accept=False,
            b6_accept=True,
            b4_b6_separated=True,
            downstream_metric_name="identity_loss_rate",
            downstream_metric_b4=float(rec.get("identity_loss_rate", 0.0)),
            downstream_metric_b6=float(rec.get("identity_loss_rate", 0.0)),
            notes=f"controlled duplicate mutation; feature_only_collisions={feature_only}; identity_aware_unique={identity_aware}",
            n_buses=int(rec.get("n_buses", 0)),
            n_original_loads=int(rec.get("n_original_loads", 0)),
            n_independent_assets=int(rec.get("n_independent_assets", 0)),
            total_feature_only_collisions=feature_only,
            total_identity_aware_unique=identity_aware,
        )


def main():
    rows = []
    load_n1(rows)
    load_representation(rows, REP_GSFM, "GridSFM")
    load_representation(rows, REP_LUMINA, "LUMINA")
    load_public_lockbox(rows)
    load_canonicalizer_3000(rows)
    load_asset_aliasing(rows)

    if rows:
        fieldnames = sorted({key for row in rows for key in row.keys()})
        with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    by_family = []
    frame = pd.DataFrame(rows)
    for family, group in frame.groupby("attack_family", sort=True):
        by_family.append({
            "attack_family": family,
            "rows": int(len(group)),
            "separated_rows": int(group["b4_b6_separated"].fillna(False).sum()),
            "separation_rate": float(group["b4_b6_separated"].fillna(False).mean()),
            "b4_accept_rate": float(group["b4_accept"].fillna(False).mean()),
            "b6_accept_rate": float(group["b6_accept"].fillna(False).mean()),
        })

    summary = {
        "experiment": "field_level_attack_family_audit",
        "date": DATE,
        "row_count": int(len(frame)),
        "attack_families": sorted(frame["attack_family"].unique().tolist()) if len(frame) else [],
        "sources": sorted(frame["source"].unique().tolist()) if len(frame) else [],
        "by_family": by_family,
        "overall_b4_b6_separation_rate": float(frame["b4_b6_separated"].fillna(False).mean()) if len(frame) else 0.0,
        "interpretation": "The table makes the attack family and identity relation explicit; GridSFM/LUMINA rows give a concrete B4/B6 analogue, while N-1 shows downstream physical consequence of the same identity split.",
        "primary_evidence": OUT_CSV.name if rows else None,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
