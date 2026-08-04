from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.cgmes_rdf_adapter import load_and_extract, load_and_extract_xml  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
BOUNDARY = BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_Boundary_v3.zip"
CASES = {
    "cgmes24_minigrid_t1": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip",
    "cgmes24_minigrid_t2": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip",
}
EXPORTS = ROOT / "results" / "roundtrip_exports"
ROUTES = {
    "veragrid": {
        "toolchain": "official_cgmes->veragrid->cgmes",
        "artifact_kind": "veragrid_roundtrip_export",
        "filename": "{case_id}__veragrid_roundtrip.zip",
    },
    "pypowsybl": {
        "toolchain": "official_cgmes->pypowsybl->cgmes",
        "artifact_kind": "pypowsybl_roundtrip_export",
        "filename": "{case_id}__pypowsybl_roundtrip.zip",
    },
}


def main() -> None:
    mapping_rows: list[dict[str, object]] = []
    for case_id, source_path in CASES.items():
        source = load_and_extract(source_path, BOUNDARY, case_id, "official_cgmes_rdf")
        source.to_csv(ROOT / "results" / f"cgmes_rdf_assets__{case_id}__source.csv", index=False)
        source_by_id = {str(row.canonical_asset_id): row for row in source.itertuples()}
        for route_id, route in ROUTES.items():
            target_path = EXPORTS / str(route["filename"]).format(case_id=case_id)
            loader = load_and_extract_xml if route_id == "pypowsybl" else load_and_extract
            target = loader(target_path, BOUNDARY, case_id, f"{route_id}_roundtrip_cgmes_rdf")
            target.to_csv(ROOT / "results" / f"cgmes_rdf_assets__{case_id}__target_{route_id}.csv", index=False)
            target_by_id = {str(row.canonical_asset_id): row for row in target.itertuples()}
            for asset_id in sorted(set(source_by_id) | set(target_by_id)):
                left = source_by_id.get(asset_id)
                right = target_by_id.get(asset_id)
                if left is None:
                    status = "created"
                    evidence = "target_only_mrid"
                    adjudication = "pending"
                elif right is None:
                    status = "dropped"
                    evidence = "source_only_mrid"
                    adjudication = "pending"
                elif left.asset_type == right.asset_type:
                    status = "exact"
                    evidence = "same_mrid_and_rdf_asset_type"
                    adjudication = "automatic"
                else:
                    status = "ambiguous"
                    evidence = f"same_mrid_type_change:{left.code}->{right.code}"
                    adjudication = "pending"
                mapping_rows.append(
                    {
                        "run_id": f"rdf_roundtrip__{route_id}__{case_id}",
                        "case_id": case_id,
                        "route_id": route_id,
                        "toolchain": route["toolchain"],
                        "source_mrid": None if left is None else left.asset_id,
                        "target_mrid": None if right is None else right.asset_id,
                        "canonical_asset_id": asset_id,
                        "source_asset_type": None if left is None else left.asset_type,
                        "target_asset_type": None if right is None else right.asset_type,
                        "source_rdf_class": None if left is None else left.code,
                        "target_rdf_class": None if right is None else right.code,
                        "source_name": None if left is None else left.name,
                        "target_name": None if right is None else right.name,
                        "source_bus1": None if left is None else left.bus1_id,
                        "target_bus1": None if right is None else right.bus1_id,
                        "source_bus2": None if left is None else left.bus2_id,
                        "target_bus2": None if right is None else right.bus2_id,
                        "source_terminal": None if left is None else left.terminal_ids,
                        "target_terminal": None if right is None else right.terminal_ids,
                        "source_p": None if left is None else left.p_mw,
                        "target_p": None if right is None else right.p_mw,
                        "source_q": None if left is None else left.q_mvar,
                        "target_q": None if right is None else right.q_mvar,
                        "source_status": None if left is None else left.in_service,
                        "target_status": None if right is None else right.in_service,
                        "mapping_status": status,
                        "identity_equivalence_evidence": evidence,
                        "adjudication_status": adjudication,
                        "structural_valid": None,
                        "operational_replay_status": "not_run",
                    }
                )
    result = pd.DataFrame(mapping_rows)
    structural = pd.read_csv(ROOT / "results" / "cgmes_structural_validation_results.csv")
    target_valid = {
        (row.case_id, row.artifact_kind): bool(row.structural_gate_valid)
        for row in structural.itertuples()
        if row.artifact_kind in {route["artifact_kind"] for route in ROUTES.values()}
    }
    artifact_kind_by_route = {route_id: route["artifact_kind"] for route_id, route in ROUTES.items()}
    result["structural_valid"] = [
        target_valid.get((row.case_id, artifact_kind_by_route[row.route_id]), False)
        for row in result.itertuples()
    ]
    result.to_csv(ROOT / "results" / "rdf_roundtrip_asset_mapping.csv", index=False)
    summary_table = (
        result.groupby(["route_id", "case_id", "mapping_status", "source_rdf_class", "target_rdf_class"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    summary_table.to_csv(ROOT / "results" / "rdf_roundtrip_asset_mapping_summary.csv", index=False)
    summary = {
        "rows": len(result),
        "status_counts": result["mapping_status"].value_counts().to_dict(),
        "structurally_valid_targets": int(result.groupby(["route_id", "case_id"])["structural_valid"].first().sum()),
        "pending_adjudication": int((result["adjudication_status"] == "pending").sum()),
        "gate1_met": False,
        "reason": "The routes show non-injected RDF identity/type changes, but Gate 1 requires adjudicated task-relevant identity anomalies plus a paired-valid downstream replay rather than any schema conversion difference.",
    }
    (ROOT / "results" / "rdf_roundtrip_asset_mapping_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(summary_table.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
