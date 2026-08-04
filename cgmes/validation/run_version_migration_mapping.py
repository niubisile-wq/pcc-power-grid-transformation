from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation.run_stage2_full_mapping import _load_or_extract, map_frames  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig"
REGISTRY = ROOT / "corpus" / "development_model_registry.csv"
MATRIX = ROOT / "results" / "version_migration_matrix_results.csv"
ASSETS = ROOT / "results" / "version_migration_mapping_assets"
OUTPUT = ROOT / "results" / "version_migration_asset_mapping.csv"
ROUTES = ROOT / "results" / "version_migration_mapping_routes.csv"
SUMMARY_JSON = ROOT / "results" / "version_migration_mapping_summary.json"


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
    if len(exports) != 32 or exports.case_id.nunique() != 32:
        raise RuntimeError("Version-migration export denominator is incomplete")
    mapping_rows: list[dict[str, object]] = []
    route_rows: list[dict[str, object]] = []
    for index, raw in enumerate(exports.to_dict("records"), 1):
        case_id = str(raw["case_id"])
        model = registry[case_id]
        source_path = BASE / model["relative_path"]
        route = {
            "case_id": case_id,
            "family": model["family"],
            "representation": model["representation"],
            "source_cgmes_version": "2.4.15",
            "target_cgmes_version": "3.0.0",
            "evidence_role": "development_version_migration_not_final_holdout",
            "exporter": "pypowsybl",
            "route": "official_cgmes_2.4.15->pypowsybl->cgmes_3.0.0",
            "source_path": source_path.relative_to(ROOT).as_posix(),
            "source_sha256": model["sha256"],
            "target_path": raw["export_path"],
            "target_sha256": raw["export_sha256"],
        }
        print(f"[{index}/{len(exports)}] {case_id}", flush=True)
        if raw["status"] != "success":
            route_rows.append(
                {
                    **route,
                    "export_status": raw["status"],
                    "mapping_status": "not_attempted_export_failed",
                    "mapping_rows": 0,
                    "source_assets": "",
                    "target_assets": "",
                    "error_type": raw["error_type"],
                    "error_message": raw["error_message"],
                }
            )
            continue
        source = _load_or_extract(
            source_path, None, case_id, ASSETS / f"{case_id}__source.csv"
        )
        target_path = ROOT / str(raw["export_path"])
        target = _load_or_extract(
            target_path,
            None,
            case_id,
            ASSETS / f"{case_id}__target.csv",
        )
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
    categories = ["exact", "renamed", "split", "merge", "dropped", "created", "ambiguous"]
    summary = {
        "evidence_role": "development_version_migration_not_final_holdout",
        "source_cgmes_version": "2.4.15",
        "target_cgmes_version": "3.0.0",
        "expected_routes": 32,
        "recorded_routes": len(routes),
        "complete_route_denominator": len(routes) == 32,
        "successful_mapped_routes": int(routes.mapping_status.eq("complete").sum()),
        "failed_unmapped_routes": int(
            routes.mapping_status.eq("not_attempted_export_failed").sum()
        ),
        "asset_relation_rows": len(mapping),
        "mapping_status_counts_including_zeros": {
            category: int(mapping.mapping_status.eq(category).sum())
            for category in categories
        },
        "pending_candidate_rows": int(
            mapping.adjudication_status.astype(str).str.startswith("pending").sum()
        ),
        "split_merge_claim_limit": (
            "split and merge labels are structural candidates, not automatic "
            "identity-equivalence proofs"
        ),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
