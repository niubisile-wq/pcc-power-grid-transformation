from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CASES = ["cgmes24_minigrid_t1", "cgmes24_minigrid_t2"]
COMPATIBLE_GENERATOR_TYPES = {"generator", "static_generator", "external_grid"}


def compatible_type(left: str, right: str) -> bool:
    return left == right or {left, right} <= COMPATIBLE_GENERATOR_TYPES


def main() -> None:
    rows: list[dict[str, object]] = []
    for case_id in CASES:
        source = pd.read_csv(RESULTS / f"common_assets__{case_id}__pandapower.csv", dtype=str).fillna("")
        target = pd.read_csv(
            RESULTS / f"common_assets__{case_id}__veragrid_roundtrip_to_pandapower.csv", dtype=str
        ).fillna("")
        unmatched_target = set(target.index)
        for source_index, source_row in source.iterrows():
            exact_candidates = [
                index
                for index in unmatched_target
                if target.at[index, "canonical_asset_id"] == source_row["canonical_asset_id"]
            ]
            if len(exact_candidates) == 1:
                target_index = exact_candidates[0]
                target_row = target.loc[target_index]
                if compatible_type(str(source_row["asset_type"]), str(target_row["asset_type"])):
                    status = "exact" if source_row["asset_type"] == target_row["asset_type"] else "renamed"
                    evidence = "canonical_mrid"
                    confidence = 1.0
                    adjudication = "automatic"
                else:
                    status = "ambiguous"
                    evidence = "canonical_mrid_with_type_change"
                    confidence = 0.5
                    adjudication = "pending"
            else:
                name_candidates = [
                    index
                    for index in unmatched_target
                    if target.at[index, "name"] == source_row["name"]
                    and compatible_type(str(source_row["asset_type"]), str(target.at[index, "asset_type"]))
                ]
                if len(name_candidates) == 1:
                    target_index = name_candidates[0]
                    target_row = target.loc[target_index]
                    status = "renamed"
                    evidence = "unique_name_and_compatible_tool_type"
                    confidence = 0.7
                    adjudication = "pending"
                else:
                    target_index = None
                    target_row = None
                    status = "dropped"
                    evidence = "no_unique_target_match"
                    confidence = 0.0
                    adjudication = "pending"
            if target_index is not None:
                unmatched_target.remove(target_index)
            rows.append(
                {
                    "run_id": f"minimum_roundtrip__{case_id}",
                    "case_id": case_id,
                    "toolchain": "official_cgmes->veragrid->cgmes->pandapower",
                    "source_mrid": source_row["asset_id"],
                    "target_mrid": None if target_row is None else target_row["asset_id"],
                    "source_asset_type": source_row["asset_type"],
                    "target_asset_type": None if target_row is None else target_row["asset_type"],
                    "source_name": source_row["name"],
                    "target_name": None if target_row is None else target_row["name"],
                    "source_bus": source_row["bus1_id"],
                    "target_bus": None if target_row is None else target_row["bus1_id"],
                    "mapping_status": status,
                    "mapping_confidence": confidence,
                    "identity_equivalence_evidence": evidence,
                    "adjudication_status": adjudication,
                    "notes": "Software round-trip result; pending rows are not yet labelled harmful or lawful.",
                }
            )
        for target_index in sorted(unmatched_target):
            target_row = target.loc[target_index]
            rows.append(
                {
                    "run_id": f"minimum_roundtrip__{case_id}",
                    "case_id": case_id,
                    "toolchain": "official_cgmes->veragrid->cgmes->pandapower",
                    "source_mrid": None,
                    "target_mrid": target_row["asset_id"],
                    "source_asset_type": None,
                    "target_asset_type": target_row["asset_type"],
                    "source_name": None,
                    "target_name": target_row["name"],
                    "source_bus": None,
                    "target_bus": target_row["bus1_id"],
                    "mapping_status": "created",
                    "mapping_confidence": 0.0,
                    "identity_equivalence_evidence": "no_unique_source_match",
                    "adjudication_status": "pending",
                    "notes": "Software round-trip result; pending rows are not yet labelled harmful or lawful.",
                }
            )
    result = pd.DataFrame(rows)
    result.to_csv(RESULTS / "minimum_roundtrip_asset_mapping.csv", index=False)
    summary_table = result.groupby(["case_id", "mapping_status"]).size().reset_index(name="count")
    summary_table.to_csv(RESULTS / "minimum_roundtrip_asset_mapping_summary.csv", index=False)
    summary = {
        "rows": len(result),
        "status_counts": result["mapping_status"].value_counts().to_dict(),
        "pending_adjudication": int((result["adjudication_status"] == "pending").sum()),
        "gate1_met": False,
        "reason": "Non-manual ID/type changes are present, but harmful identity loss is not established until structural and downstream adjudication is complete.",
    }
    (RESULTS / "minimum_roundtrip_asset_mapping_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(summary_table.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

