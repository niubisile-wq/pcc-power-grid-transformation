from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.cgmes_rdf_adapter import load_and_extract_xml  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig"
REGISTRY = ROOT / "corpus" / "development_model_registry.csv"
MATRIX = ROOT / "results" / "stage2_roundtrip_matrix_results.csv"
ASSETS = ROOT / "results" / "stage2_full_mapping_assets"
OUTPUT = ROOT / "results" / "stage2_full_roundtrip_asset_mapping.csv"
ROUTES = ROOT / "results" / "stage2_full_roundtrip_mapping_routes.csv"


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _name(value: object) -> str:
    return re.sub(r"\s+", " ", _clean(value)).casefold()


def _endpoints(row: pd.Series) -> tuple[str, ...]:
    return tuple(sorted(value for value in (_clean(row.bus1_id), _clean(row.bus2_id)) if value))


def _structural_key(row: pd.Series) -> tuple[str, str, tuple[str, ...]] | None:
    endpoints = _endpoints(row)
    name = _name(row.get("name"))
    asset_type = _clean(row.get("asset_type"))
    if not asset_type or not name or not endpoints:
        return None
    return asset_type, name, endpoints


def _by_id(frame: pd.DataFrame) -> dict[str, list[pd.Series]]:
    output: dict[str, list[pd.Series]] = {}
    for _, row in frame.iterrows():
        output.setdefault(_clean(row.canonical_asset_id), []).append(row)
    return output


def _row(
    route: dict[str, object],
    source: pd.Series | None,
    target: pd.Series | None,
    status: str,
    evidence: str,
    adjudication: str,
    confidence: float,
) -> dict[str, object]:
    def value(side: pd.Series | None, field: str) -> object:
        if side is None:
            return ""
        candidate = side.get(field, "")
        return "" if pd.isna(candidate) else candidate

    return {
        **route,
        "source_mrid": value(source, "asset_id"),
        "target_mrid": value(target, "asset_id"),
        "source_canonical_asset_id": value(source, "canonical_asset_id"),
        "target_canonical_asset_id": value(target, "canonical_asset_id"),
        "source_asset_type": value(source, "asset_type"),
        "target_asset_type": value(target, "asset_type"),
        "source_rdf_class": value(source, "code"),
        "target_rdf_class": value(target, "code"),
        "source_name": value(source, "name"),
        "target_name": value(target, "name"),
        "source_bus1": value(source, "bus1_id"),
        "target_bus1": value(target, "bus1_id"),
        "source_bus2": value(source, "bus2_id"),
        "target_bus2": value(target, "bus2_id"),
        "source_terminal_ids": value(source, "terminal_ids"),
        "target_terminal_ids": value(target, "terminal_ids"),
        "source_p_mw": value(source, "p_mw"),
        "target_p_mw": value(target, "p_mw"),
        "source_q_mvar": value(source, "q_mvar"),
        "target_q_mvar": value(target, "q_mvar"),
        "source_in_service": value(source, "in_service"),
        "target_in_service": value(target, "in_service"),
        "source_r": value(source, "r"),
        "target_r": value(target, "r"),
        "source_x": value(source, "x"),
        "target_x": value(target, "x"),
        "mapping_status": status,
        "identity_equivalence_evidence": evidence,
        "mapping_confidence": confidence,
        "adjudication_status": adjudication,
        "claim_scope": (
            "asset census; split/merge labels are conservative structural candidates "
            "until independently adjudicated"
        ),
    }


def map_frames(
    route: dict[str, object], source: pd.DataFrame, target: pd.DataFrame
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    source_by_id = _by_id(source)
    target_by_id = _by_id(target)
    for asset_id in sorted(set(source_by_id) & set(target_by_id)):
        left = source_by_id[asset_id]
        right = target_by_id[asset_id]
        if len(left) != 1 or len(right) != 1:
            for source_row in left or [None]:
                for target_row in right or [None]:
                    rows.append(
                        _row(
                            route,
                            source_row,
                            target_row,
                            "ambiguous",
                            "same_mrid_nonunique_in_source_or_target",
                            "pending",
                            0.0,
                        )
                    )
            continue
        source_row, target_row = left[0], right[0]
        if _clean(source_row.asset_type) != _clean(target_row.asset_type):
            status = "ambiguous"
            evidence = "same_mrid_but_normalized_asset_type_changed"
            adjudication = "pending"
            confidence = 0.0
        elif _clean(source_row.code) != _clean(target_row.code):
            status = "ambiguous"
            evidence = "same_mrid_but_rdf_class_changed"
            adjudication = "pending"
            confidence = 0.0
        elif _name(source_row.get("name")) != _name(target_row.get("name")):
            status = "renamed"
            evidence = "same_mrid_and_rdf_class_name_changed"
            adjudication = "automatic_identity_preserved"
            confidence = 1.0
        else:
            status = "exact"
            evidence = "same_mrid_rdf_class_and_normalized_name"
            adjudication = "automatic"
            confidence = 1.0
        rows.append(
            _row(
                route,
                source_row,
                target_row,
                status,
                evidence,
                adjudication,
                confidence,
            )
        )

    shared_ids = set(source_by_id) & set(target_by_id)
    source_unmatched = [
        row for _, row in source.iterrows() if _clean(row.canonical_asset_id) not in shared_ids
    ]
    target_unmatched = [
        row for _, row in target.iterrows() if _clean(row.canonical_asset_id) not in shared_ids
    ]

    source_groups: dict[tuple[str, str, tuple[str, ...]], list[pd.Series]] = {}
    target_groups: dict[tuple[str, str, tuple[str, ...]], list[pd.Series]] = {}
    for row in source_unmatched:
        key = _structural_key(row)
        if key is not None:
            source_groups.setdefault(key, []).append(row)
    for row in target_unmatched:
        key = _structural_key(row)
        if key is not None:
            target_groups.setdefault(key, []).append(row)

    consumed_source: set[str] = set()
    consumed_target: set[str] = set()
    for key in sorted(set(source_groups) & set(target_groups), key=str):
        left = source_groups[key]
        right = target_groups[key]
        consumed_source.update(_clean(row.canonical_asset_id) for row in left)
        consumed_target.update(_clean(row.canonical_asset_id) for row in right)
        if len(left) == len(right) == 1:
            rows.append(
                _row(
                    route,
                    left[0],
                    right[0],
                    "renamed",
                    "changed_mrid_unique_same_type_normalized_name_and_endpoints",
                    "automatic_conservative",
                    0.9,
                )
            )
        elif len(left) == 1 and len(right) > 1:
            for target_row in right:
                rows.append(
                    _row(
                        route,
                        left[0],
                        target_row,
                        "split",
                        "one_source_to_multiple_targets_same_type_name_and_endpoints",
                        "pending_candidate",
                        0.5,
                    )
                )
        elif len(left) > 1 and len(right) == 1:
            for source_row in left:
                rows.append(
                    _row(
                        route,
                        source_row,
                        right[0],
                        "merge",
                        "multiple_sources_to_one_target_same_type_name_and_endpoints",
                        "pending_candidate",
                        0.5,
                    )
                )
        else:
            for source_row in left:
                for target_row in right:
                    rows.append(
                        _row(
                            route,
                            source_row,
                            target_row,
                            "ambiguous",
                            "many_to_many_same_structural_key",
                            "pending",
                            0.0,
                        )
                    )

    for source_row in source_unmatched:
        if _clean(source_row.canonical_asset_id) not in consumed_source:
            rows.append(
                _row(
                    route,
                    source_row,
                    None,
                    "dropped",
                    "source_only_after_conservative_structural_matching",
                    "pending",
                    0.0,
                )
            )
    for target_row in target_unmatched:
        if _clean(target_row.canonical_asset_id) not in consumed_target:
            rows.append(
                _row(
                    route,
                    None,
                    target_row,
                    "created",
                    "target_only_after_conservative_structural_matching",
                    "pending",
                    0.0,
                )
            )
    return rows


def _load_or_extract(
    path: Path, boundary: Path | None, case_id: str, cache: Path
) -> pd.DataFrame:
    if cache.is_file():
        return pd.read_csv(cache, keep_default_na=False)
    frame = load_and_extract_xml(path, boundary, case_id, "cgmes_raw_xml_asset_census")
    frame.to_csv(cache, index=False)
    return frame


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        registry = {
            row["case_id"]: row
            for row in csv.DictReader(stream)
            if row["included"].lower() == "true"
        }
    matrix = pd.read_csv(MATRIX, keep_default_na=False)
    exports = matrix[matrix.stage == "export"].copy()
    mapping_rows: list[dict[str, object]] = []
    route_rows: list[dict[str, object]] = []
    for index, raw in enumerate(exports.to_dict("records"), 1):
        case_id = str(raw["case_id"])
        exporter = str(raw["exporter"])
        model = registry[case_id]
        source_path = BASE / model["relative_path"]
        boundary = (
            BASE / model["boundary_relative_path"]
            if model["boundary_relative_path"]
            else None
        )
        route = {
            "case_id": case_id,
            "family": model["family"],
            "representation": model["representation"],
            "exporter": exporter,
            "route": f"official_cgmes->{exporter}->cgmes",
            "source_path": source_path.relative_to(ROOT).as_posix(),
            "source_sha256": model["sha256"],
            "target_path": raw["export_path"],
            "target_sha256": raw["export_sha256"],
        }
        print(f"[{index}/{len(exports)}] {case_id} {exporter}", flush=True)
        if raw["status"] != "success":
            route_rows.append(
                {
                    **route,
                    "export_status": raw["status"],
                    "mapping_status": "not_attempted_export_failed",
                    "mapping_rows": 0,
                    "error_type": raw["error_type"],
                    "error_message": raw["error_message"],
                }
            )
            continue
        source_cache = ASSETS / f"{case_id}__source.csv"
        target_cache = ASSETS / f"{case_id}__{exporter}__target.csv"
        source = _load_or_extract(source_path, boundary, case_id, source_cache)
        target_path = ROOT / str(raw["export_path"])
        target = _load_or_extract(target_path, boundary, case_id, target_cache)
        rows = map_frames(route, source, target)
        mapping_rows.extend(rows)
        route_rows.append(
            {
                **route,
                "export_status": "success",
                "mapping_status": "complete",
                "mapping_rows": len(rows),
                "source_assets": len(source),
                "target_assets": len(target),
                "error_type": "",
                "error_message": "",
            }
        )
        pd.DataFrame(mapping_rows).to_csv(OUTPUT, index=False)
        pd.DataFrame(route_rows).to_csv(ROUTES, index=False)
    mapping = pd.DataFrame(mapping_rows)
    routes = pd.DataFrame(route_rows)
    mapping.to_csv(OUTPUT, index=False)
    routes.to_csv(ROUTES, index=False)
    by_route_status = (
        mapping.groupby(["exporter", "family", "mapping_status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    # Preserve zero-count categories so a missing split/merge is an explicit
    # result rather than an omitted category.
    categories = ["exact", "renamed", "split", "merge", "dropped", "created", "ambiguous"]
    totals = {category: int((mapping.mapping_status == category).sum()) for category in categories}
    by_route_status.to_csv(
        ROOT / "results" / "stage2_full_roundtrip_mapping_summary.csv", index=False
    )
    summary = {
        "expected_routes": len(exports),
        "recorded_routes": len(routes),
        "complete_route_denominator": len(routes) == len(exports),
        "successful_mapped_routes": int(routes.mapping_status.eq("complete").sum()),
        "failed_unmapped_routes": int(
            routes.mapping_status.eq("not_attempted_export_failed").sum()
        ),
        "asset_relation_rows": len(mapping),
        "mapping_status_counts_including_zeros": totals,
        "pending_candidate_rows": int(
            mapping.adjudication_status.astype(str).str.startswith("pending").sum()
        ),
        "strict_rdf_validity_checked_separately": True,
        "split_merge_claim_limit": (
            "split and merge labels are structural candidates, not automatic identity-equivalence proofs"
        ),
    }
    (ROOT / "results" / "stage2_full_roundtrip_mapping_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
