from __future__ import annotations

import itertools
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CASES = ["cgmes24_minigrid_t1", "cgmes24_minigrid_t2"]
TOOLS = ["pandapower", "pypowsybl", "veragrid"]


def scalar(row: pd.Series | None, key: str) -> object:
    if row is None:
        return None
    value = row.get(key)
    return None if pd.isna(value) else value


def rows_by_id(data: pd.DataFrame) -> dict[str, list[pd.Series]]:
    output: dict[str, list[pd.Series]] = {}
    for _, row in data.iterrows():
        output.setdefault(str(row["canonical_asset_id"]), []).append(row)
    return output


def classify(source_rows: list[pd.Series], target_rows: list[pd.Series]) -> tuple[str, str]:
    if not source_rows:
        return "created", "canonical mRID present only in target tool representation"
    if not target_rows:
        return "dropped", "canonical mRID present only in source tool representation"
    if len(source_rows) != 1 or len(target_rows) != 1:
        return "ambiguous", "canonical mRID is non-unique in at least one tool representation"
    source_type = str(source_rows[0]["asset_type"])
    target_type = str(target_rows[0]["asset_type"])
    if source_type == target_type:
        return "exact", "canonical mRID and normalized asset type agree"
    compatible = {source_type, target_type} <= {"generator", "static_generator", "external_grid"}
    if compatible:
        return "renamed", "canonical mRID agrees; generator subtype differs across tool schemas"
    return "ambiguous", f"canonical mRID agrees but asset types differ: {source_type} vs {target_type}"


def main() -> None:
    output_rows: list[dict[str, object]] = []
    for case_id in CASES:
        data = {
            tool: pd.read_csv(
                RESULTS / f"common_assets__{case_id}__{tool}.csv", dtype=str
            ).fillna("")
            for tool in TOOLS
        }
        for source_tool, target_tool in itertools.permutations(TOOLS, 2):
            source = rows_by_id(data[source_tool])
            target = rows_by_id(data[target_tool])
            for canonical_asset_id in sorted(set(source) | set(target)):
                source_rows = source.get(canonical_asset_id, [])
                target_rows = target.get(canonical_asset_id, [])
                status, notes = classify(source_rows, target_rows)
                source_row = source_rows[0] if source_rows else None
                target_row = target_rows[0] if target_rows else None
                output_rows.append(
                    {
                        "run_id": f"smoke__{case_id}__{source_tool}__{target_tool}",
                        "case_id": case_id,
                        "toolchain": f"{source_tool}->{target_tool}",
                        "source_format": source_tool,
                        "target_format": target_tool,
                        "source_profile": "CGMES_2.4.15",
                        "target_profile": "tool_internal_common_schema_v1",
                        "source_snapshot_hash": scalar(source_row, "source_sha256") or scalar(target_row, "source_sha256"),
                        "target_snapshot_hash": scalar(target_row, "source_sha256") or scalar(source_row, "source_sha256"),
                        "source_mrid": scalar(source_row, "asset_id"),
                        "target_mrid": scalar(target_row, "asset_id"),
                        "canonical_asset_id": canonical_asset_id,
                        "source_asset_type": scalar(source_row, "asset_type"),
                        "target_asset_type": scalar(target_row, "asset_type"),
                        "source_bus": scalar(source_row, "bus1_id"),
                        "target_bus": scalar(target_row, "bus1_id"),
                        "source_terminal": scalar(source_row, "terminal_ids"),
                        "target_terminal": scalar(target_row, "terminal_ids"),
                        "source_p": scalar(source_row, "p_mw"),
                        "target_p": scalar(target_row, "p_mw"),
                        "source_q": scalar(source_row, "q_mvar"),
                        "target_q": scalar(target_row, "q_mvar"),
                        "source_status": scalar(source_row, "in_service"),
                        "target_status": scalar(target_row, "in_service"),
                        "mapping_status": status,
                        "mapping_confidence": "1.0" if status in {"exact", "renamed"} else "0.0",
                        "common_parent": None,
                        "identity_equivalence_evidence": "canonical_mrid" if source_rows and target_rows else None,
                        "schema_valid": None,
                        "shacl_valid": None,
                        "conservation_valid": None,
                        "identity_only_valid": status in {"exact", "renamed"},
                        "full_pcc_valid": None,
                        "adjudication_status": "pending" if status in {"dropped", "created", "ambiguous"} else "automatic",
                        "notes": notes,
                    }
                )
    result = pd.DataFrame(output_rows)
    result.to_csv(RESULTS / "roundtrip_asset_mapping.csv", index=False)
    summary_table = (
        result.groupby(["case_id", "toolchain", "mapping_status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    summary_table.to_csv(RESULTS / "roundtrip_asset_mapping_summary.csv", index=False)
    summary = {
        "rows": len(result),
        "status_counts": result["mapping_status"].value_counts().to_dict(),
        "unadjudicated_rows": int((result["adjudication_status"] == "pending").sum()),
        "natural_anomaly_claim_ready": False,
        "reason": "Smoke-stage tool-schema discrepancies require source-profile and converter-log adjudication before they can be called natural identity anomalies.",
    }
    (RESULTS / "roundtrip_asset_mapping_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

