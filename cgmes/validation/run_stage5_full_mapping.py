from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation.run_stage2_full_mapping import _load_or_extract, map_frames  # noqa: E402


REGISTRY = ROOT / "corpus" / "validation_model_registry.csv"
MATRIX = ROOT / "results" / "stage5_roundtrip_matrix_results.csv"
ASSETS = ROOT / "results" / "stage5_full_mapping_assets"
OUTPUT = ROOT / "results" / "stage5_full_roundtrip_asset_mapping.csv"
ROUTES = ROOT / "results" / "stage5_full_roundtrip_mapping_routes.csv"
SUMMARY_CSV = ROOT / "results" / "stage5_full_roundtrip_mapping_summary.csv"
SUMMARY_JSON = ROOT / "results" / "stage5_full_roundtrip_mapping_summary.json"


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
    if len(exports) != 40 or exports.case_id.nunique() != 20:
        raise RuntimeError("Stage 5 export-route denominator is incomplete")

    mapping_rows: list[dict[str, object]] = []
    route_rows: list[dict[str, object]] = []
    for index, raw in enumerate(exports.to_dict("records"), 1):
        case_id = str(raw["case_id"])
        exporter = str(raw["exporter"])
        model = registry[case_id]
        source_path = ROOT / model["package_relative_path"]
        route = {
            "case_id": case_id,
            "family": model["family"],
            "representation": model["split"],
            "cgmes_version": model["cgmes_version"],
            "evidence_role": "internal_validation_not_untouched_final_holdout",
            "exporter": exporter,
            "route": f"official_cgmes3->{exporter}->cgmes3",
            "source_path": source_path.relative_to(ROOT).as_posix(),
            "source_sha256": model["package_sha256"],
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
                    "source_assets": "",
                    "target_assets": "",
                    "error_type": raw["error_type"],
                    "error_message": raw["error_message"],
                }
            )
            continue

        source_cache = ASSETS / f"{case_id}__source.csv"
        target_cache = ASSETS / f"{case_id}__{exporter}__target.csv"
        source = _load_or_extract(source_path, None, case_id, source_cache)
        target_path = ROOT / str(raw["export_path"])
        target = _load_or_extract(target_path, None, case_id, target_cache)
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
    by_route_status.to_csv(SUMMARY_CSV, index=False)
    categories = ["exact", "renamed", "split", "merge", "dropped", "created", "ambiguous"]
    totals = {
        category: int(mapping.mapping_status.eq(category).sum())
        for category in categories
    }
    summary = {
        "evidence_role": "internal_validation_not_untouched_final_holdout",
        "cgmes_version": "3.0.0",
        "expected_routes": 40,
        "recorded_routes": len(routes),
        "complete_route_denominator": len(routes) == 40,
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
            "split and merge labels are structural candidates, not automatic "
            "identity-equivalence proofs"
        ),
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
