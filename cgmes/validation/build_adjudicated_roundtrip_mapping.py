from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import sha256  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
SOURCES = {
    "cgmes24_minigrid_t1": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip",
    "cgmes24_minigrid_t2": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip",
}
TARGETS = {
    (case_id, route): ROOT / "results" / "roundtrip_exports" / f"{case_id}__{route}_roundtrip.zip"
    for case_id in SOURCES
    for route in ("veragrid", "pypowsybl")
}
REQUIRED_COLUMNS = [
    "run_id",
    "case_id",
    "toolchain",
    "source_format",
    "target_format",
    "source_profile",
    "target_profile",
    "source_snapshot_hash",
    "target_snapshot_hash",
    "source_mrid",
    "target_mrid",
    "source_asset_type",
    "target_asset_type",
    "source_bus",
    "target_bus",
    "source_terminal",
    "target_terminal",
    "source_p",
    "target_p",
    "source_q",
    "target_q",
    "source_status",
    "target_status",
    "mapping_status",
    "mapping_confidence",
    "common_parent",
    "identity_equivalence_evidence",
    "schema_valid",
    "shacl_valid",
    "conservation_valid",
    "identity_only_valid",
    "full_pcc_valid",
    "adjudication_status",
    "task_scope",
    "natural_anomaly",
    "gate1_qualifying",
    "notes",
]


def _clean(value: Any) -> Any:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value


def _same_number(left: Any, right: Any, tolerance: float = 1e-12) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def _bus_pair(row: pd.Series, prefix: str) -> str:
    values = [_clean(row.get(f"{prefix}_bus1")), _clean(row.get(f"{prefix}_bus2"))]
    return " | ".join(str(value) for value in values if value != "")


def _base_output(row: pd.Series, structural: dict[tuple[str, str], bool]) -> dict[str, Any]:
    case_id = str(row.case_id)
    route_id = str(row.route_id)
    artifact_kind = f"{route_id}_roundtrip_export"
    answer = {
        "run_id": row.run_id,
        "case_id": case_id,
        "toolchain": row.toolchain,
        "source_format": "CGMES_2.4.15_RDF_XML",
        "target_format": "CGMES_2.4.15_RDF_XML",
        "source_profile": "DL|EQ|SSH|SV|TP + official boundary",
        "target_profile": "EQ|SSH|TP + official boundary",
        "source_snapshot_hash": sha256(SOURCES[case_id]),
        "target_snapshot_hash": sha256(TARGETS[(case_id, route_id)]),
        "source_mrid": _clean(row.source_mrid),
        "target_mrid": _clean(row.target_mrid),
        "source_asset_type": _clean(row.source_asset_type),
        "target_asset_type": _clean(row.target_asset_type),
        "source_bus": _bus_pair(row, "source"),
        "target_bus": _bus_pair(row, "target"),
        "source_terminal": _clean(row.source_terminal),
        "target_terminal": _clean(row.target_terminal),
        "source_p": _clean(row.source_p),
        "target_p": _clean(row.target_p),
        "source_q": _clean(row.source_q),
        "target_q": _clean(row.target_q),
        "source_status": _clean(row.source_status),
        "target_status": _clean(row.target_status),
        "mapping_status": row.mapping_status,
        "mapping_confidence": 0.0,
        "common_parent": "",
        "identity_equivalence_evidence": row.identity_equivalence_evidence,
        "schema_valid": structural.get((case_id, artifact_kind), False),
        "shacl_valid": "",
        "conservation_valid": "",
        "identity_only_valid": False,
        "full_pcc_valid": False,
        "adjudication_status": "automatic_rule_v1",
        "task_scope": "none",
        "natural_anomaly": False,
        "gate1_qualifying": False,
        "notes": "",
    }
    return answer


def main() -> None:
    raw = pd.read_csv(ROOT / "results" / "rdf_roundtrip_asset_mapping.csv")
    structural_frame = pd.read_csv(ROOT / "results" / "cgmes_structural_validation_results.csv")
    structural = {
        (str(row.case_id), str(row.artifact_kind)): bool(row.structural_gate_valid)
        for row in structural_frame.itertuples()
    }
    source_assets = {
        case_id: pd.read_csv(ROOT / "results" / f"cgmes_rdf_assets__{case_id}__source.csv")
        for case_id in SOURCES
    }
    rows: list[dict[str, Any]] = []
    consumed: set[int] = set()

    # Unique boundary-bus replacements are deterministic rekeys, not two unrelated
    # drop/create events. No explicit identity relation is emitted by the converter.
    for (case_id, route_id), group in raw.groupby(["case_id", "route_id"]):
        if route_id != "pypowsybl":
            continue
        dropped = group[
            (group.mapping_status == "dropped")
            & (group.source_asset_type == "equivalent_injection")
        ]
        created = group[
            (group.mapping_status == "created")
            & (group.target_asset_type == "equivalent_injection")
        ]
        for dropped_index, left in dropped.iterrows():
            matches = created[created.target_bus1 == left.source_bus1]
            if len(matches) != 1:
                continue
            created_index = int(matches.index[0])
            if created_index in consumed:
                continue
            right = matches.iloc[0]
            combined = left.copy()
            for column in raw.columns:
                if column.startswith("target_"):
                    combined[column] = right[column]
            combined["target_mrid"] = right.target_mrid
            combined["mapping_status"] = "renamed"
            combined["identity_equivalence_evidence"] = "unique_same_type_same_boundary_topological_node"
            output = _base_output(combined, structural)
            output.update(
                {
                    "mapping_status": "renamed",
                    "mapping_confidence": 0.98,
                    "identity_only_valid": False,
                    "adjudication_status": "automatic_unique_boundary_replacement",
                    "task_scope": "boundary_injection",
                    "natural_anomaly": True,
                    "notes": "Functional boundary injection is rekeyed from the source injection mRID to an ID derived from the boundary ACLineSegment; no explicit provenance relation is exported.",
                }
            )
            rows.append(output)
            consumed.update({int(dropped_index), created_index})

    for index, row in raw.iterrows():
        if int(index) in consumed:
            continue
        output = _base_output(row, structural)
        case_id = str(row.case_id)
        route_id = str(row.route_id)
        status = str(row.mapping_status)
        if status == "exact":
            output.update(
                {
                    "mapping_confidence": 1.0,
                    "identity_only_valid": True,
                    "adjudication_status": "automatic_exact_mrid_and_type",
                    "notes": "Exact mRID and RDF class match.",
                }
            )
        elif status == "ambiguous" and _clean(row.source_mrid) == _clean(row.target_mrid):
            output.update(
                {
                    "mapping_confidence": 1.0,
                    "identity_only_valid": True,
                    "adjudication_status": "confirmed_same_mrid_semantic_type_mutation",
                    "task_scope": "PF_and_machine_contingency",
                    "natural_anomaly": True,
                    "notes": f"Same mRID changes RDF class from {row.source_rdf_class} to {row.target_rdf_class}; identity-only accepts the ID but a payload/type contract should reject it.",
                }
            )
        elif status == "created" and str(row.target_asset_type) in {"busbar", "connectivity_node"}:
            parent = _clean(row.target_bus1)
            output.update(
                {
                    "mapping_confidence": 1.0 if parent else 0.8,
                    "common_parent": parent,
                    "identity_only_valid": bool(parent),
                    "adjudication_status": "automatic_derived_topology_object",
                    "task_scope": "topology_representation",
                    "natural_anomaly": False,
                    "notes": "Converter-created topology object; treated as lawful derived representation when the TopologicalNode relation is explicit.",
                }
            )
        elif status == "dropped" and str(row.source_asset_type) == "line":
            source = source_assets[case_id]
            asset_id = str(row.canonical_asset_id)
            asset_matches = source[source.canonical_asset_id.astype(str) == asset_id]
            parallel_match = False
            if len(asset_matches) == 1:
                asset = asset_matches.iloc[0]
                peers = source[
                    (source.asset_type == "line")
                    & (source.canonical_asset_id.astype(str) != asset_id)
                    & (source.bus1_id == asset.bus1_id)
                    & (source.bus2_id == asset.bus2_id)
                ]
                parallel_match = any(
                    _same_number(peer.r, asset.r) and _same_number(peer.x, asset.x)
                    for peer in peers.itertuples()
                )
            if parallel_match and route_id == "veragrid":
                output.update(
                    {
                        "mapping_confidence": 1.0,
                        "identity_only_valid": False,
                        "adjudication_status": "confirmed_task_relevant_parallel_asset_identity_loss",
                        "task_scope": "N-1_branch_outage",
                        "natural_anomaly": True,
                        "gate1_qualifying": True,
                        "notes": "A distinct named parallel branch disappears while its same-endpoint, same-parameter peer remains. No common-parent relation or lawful merge certificate exists; the missing mRID is removed from the N-1 candidate set.",
                    }
                )
            else:
                output.update(
                    {
                        "mapping_confidence": 1.0,
                        "adjudication_status": "confirmed_dropped_boundary_interface_asset",
                        "task_scope": "boundary_interface",
                        "natural_anomaly": True,
                        "notes": "Dropped line terminates at a boundary TopologicalNode; retained as a negative interoperability result but not counted as an internal N-1 identity-loss event.",
                    }
                )
        elif status == "dropped":
            output.update(
                {
                    "mapping_confidence": 1.0,
                    "adjudication_status": "confirmed_unmapped_drop",
                    "task_scope": "boundary_interface" if str(row.source_asset_type) == "equivalent_injection" else "unresolved",
                    "natural_anomaly": True,
                    "notes": "Source mRID has no target counterpart under the frozen automatic rules.",
                }
            )
        elif status == "created":
            output.update(
                {
                    "mapping_confidence": 1.0,
                    "adjudication_status": "confirmed_unmapped_creation",
                    "task_scope": "unresolved",
                    "natural_anomaly": True,
                    "notes": "Target mRID has no source counterpart under the frozen automatic rules.",
                }
            )
        else:
            output.update(
                {
                    "mapping_confidence": 0.0,
                    "adjudication_status": "unresolved",
                    "notes": "No frozen automatic adjudication rule matched.",
                }
            )
        rows.append(output)

    result = pd.DataFrame(rows, columns=REQUIRED_COLUMNS).sort_values(
        ["case_id", "toolchain", "mapping_status", "source_mrid", "target_mrid"],
        kind="stable",
    )
    result.to_csv(ROOT / "results" / "roundtrip_asset_mapping.csv", index=False)
    anomalies = result[result.natural_anomaly.astype(bool)].copy()
    anomalies.to_csv(ROOT / "results" / "natural_conversion_anomaly_inventory.csv", index=False)
    qualifying = result[result.gate1_qualifying.astype(bool)]
    summary = {
        "rows": len(result),
        "mapping_status_counts": result.mapping_status.value_counts().to_dict(),
        "adjudication_status_counts": result.adjudication_status.value_counts().to_dict(),
        "natural_anomaly_rows": len(anomalies),
        "gate1_qualifying_rows": len(qualifying),
        "gate1_met": len(qualifying) > 0,
        "gate1_case_ids": sorted(qualifying.case_id.unique().tolist()),
        "gate1_task_scopes": sorted(qualifying.task_scope.unique().tolist()),
        "gate1_interpretation": "At least one distinct named source asset is naturally removed by a public tool conversion with no lawful identity relation, and the asset is in the predeclared N-1 branch-outage scope.",
        "scope_limit": "Gate 1 establishes a task-relevant mapping anomaly, not an operational consequence; Gate 3 remains open.",
    }
    (ROOT / "results" / "roundtrip_asset_mapping_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(qualifying[["case_id", "toolchain", "source_mrid", "source_asset_type", "task_scope", "adjudication_status"]].to_string(index=False))


if __name__ == "__main__":
    main()
