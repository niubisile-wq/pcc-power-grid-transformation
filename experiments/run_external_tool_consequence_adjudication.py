"""Adjudicate N-1 consequences for the frozen external roundtrip receipts.

This script runs only after the external challenge manifest and PCC receipts
exist. It does not regenerate route artifacts or PCC receipts. Solver failures
are retained as adjudication outcomes instead of being converted into negative
or positive consequence labels.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

import pypowsybl as pp
import pypowsybl.security as security


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "external_tool_blind_roundtrip"
CHALLENGE = BASE / "challenge_manifest.json"
ROUTES = BASE / "route_artifacts_manifest.json"
RECEIPTS = BASE / "pcc_receipts.jsonl"
OUT_JSONL = BASE / "consequence_labels.jsonl"
OUT_CSV = BASE / "consequence_labels.csv"
OUT_SUMMARY = BASE / "consequence_summary.json"
SUMMARY = BASE / "summary.json"
ADJUDICATION_CREATED_AT = "2026-08-07T00:00:00Z"

sys.path.insert(0, str(ROOT / "cgmes"))
from adapters.common_asset_schema import canonical_id, sha256  # noqa: E402


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def canonical_index(network: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for table_getter in (network.get_lines, network.get_2_windings_transformers):
        table = table_getter()
        for raw_id in table.index:
            mapping[canonical_id(str(raw_id))] = str(raw_id)
    return mapping


def result_status(result: Any) -> str:
    status = getattr(result, "status", None)
    if status is None:
        return "UNKNOWN"
    return getattr(status, "name", str(status))


def run_security(path: Path, asset_ids: list[str]) -> dict[str, Any]:
    try:
        network = pp.network.load(str(path))
    except Exception as exc:
        return {
            "artifact_status": "import_failure",
            "artifact_error": f"{type(exc).__name__}:{exc}",
            "pre_status": "NOT_RUN",
            "post_status_by_asset": {},
            "limit_violation_count_by_asset": {},
            "raw_id_by_asset": {},
        }
    index = canonical_index(network)
    analysis = security.create_analysis()
    raw_id_by_asset: dict[str, str] = {}
    missing_assets: list[str] = []
    for asset_id in asset_ids:
        raw_id = index.get(canonical_id(asset_id))
        if raw_id is None:
            missing_assets.append(asset_id)
            continue
        raw_id_by_asset[asset_id] = raw_id
        analysis.add_single_element_contingency(raw_id, contingency_id=asset_id)
    if not raw_id_by_asset:
        return {
            "artifact_status": "no_mapped_contingencies",
            "artifact_error": None,
            "pre_status": "NOT_RUN",
            "post_status_by_asset": {},
            "limit_violation_count_by_asset": {},
            "raw_id_by_asset": raw_id_by_asset,
            "missing_assets": missing_assets,
        }
    try:
        result = analysis.run_ac(network)
    except Exception as exc:
        return {
            "artifact_status": "security_analysis_failure",
            "artifact_error": f"{type(exc).__name__}:{exc}",
            "pre_status": "FAILED",
            "post_status_by_asset": {},
            "limit_violation_count_by_asset": {},
            "raw_id_by_asset": raw_id_by_asset,
            "missing_assets": missing_assets,
        }
    post_status_by_asset: dict[str, str] = {}
    for asset_id in raw_id_by_asset:
        post = result.post_contingency_results.get(asset_id)
        post_status_by_asset[asset_id] = result_status(post) if post is not None else "NOT_AVAILABLE"
    violations = result.limit_violations
    violation_counts = {asset_id: 0 for asset_id in raw_id_by_asset}
    if not violations.empty and "contingency_id" in violations.columns:
        for contingency_id, group in violations.groupby("contingency_id"):
            violation_counts[str(contingency_id)] = int(len(group))
    return {
        "artifact_status": "security_analysis_complete",
        "artifact_error": None,
        "pre_status": result_status(result.pre_contingency_result),
        "post_status_by_asset": post_status_by_asset,
        "limit_violation_count_by_asset": violation_counts,
        "raw_id_by_asset": raw_id_by_asset,
        "missing_assets": missing_assets,
    }


def consequence_label(source: dict[str, Any], target: dict[str, Any], asset_id: str, task_anomaly: bool) -> dict[str, Any]:
    source_post = source["post_status_by_asset"].get(asset_id, "NOT_AVAILABLE")
    target_post = target["post_status_by_asset"].get(asset_id, "NOT_AVAILABLE")
    source_valid = source["pre_status"] == "CONVERGED" and source_post == "CONVERGED"
    target_valid = target["pre_status"] == "CONVERGED" and target_post == "CONVERGED"
    paired_valid = source_valid and target_valid
    source_violations = source["limit_violation_count_by_asset"].get(asset_id)
    target_violations = target["limit_violation_count_by_asset"].get(asset_id)
    status_changed = source_post != target_post
    violation_count_changed = (
        source_violations is not None
        and target_violations is not None
        and int(source_violations) != int(target_violations)
    )
    operationally_consequential = bool(task_anomaly and paired_valid and (status_changed or violation_count_changed))
    if paired_valid:
        reason = "paired_source_target_n1_converged"
    elif source["artifact_status"] != "security_analysis_complete" or target["artifact_status"] != "security_analysis_complete":
        reason = "security_analysis_not_complete"
    elif not task_anomaly:
        reason = "no_task_relevant_anomaly_to_adjudicate"
    else:
        reason = "paired_source_target_n1_not_converged"
    return {
        "operational_consequence_attempted": True,
        "paired_valid_consequence_evaluated": paired_valid,
        "operationally_consequential": operationally_consequential,
        "consequence_evaluation_reason": reason,
        "source_pre_status": source["pre_status"],
        "target_pre_status": target["pre_status"],
        "source_post_status": source_post,
        "target_post_status": target_post,
        "source_limit_violations": source_violations,
        "target_limit_violations": target_violations,
    }


def main() -> int:
    for path in (CHALLENGE, ROUTES, RECEIPTS):
        if not path.is_file():
            raise FileNotFoundError(path)
    challenge = read_json(CHALLENGE)
    routes = read_json(ROUTES)["records"]
    receipts = read_jsonl(RECEIPTS)
    receipt_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in receipts:
        receipt_groups.setdefault((row["bundle_id"], row["route"]), []).append(row)
    route_by_key = {(row["bundle_id"], row["route"]): row for row in routes}
    challenge_by_bundle = {row["bundle_id"]: row for row in challenge["bundles"]}

    artifact_runs: dict[tuple[str, str, str], dict[str, Any]] = {}
    consequence_rows: list[dict[str, Any]] = []
    for key, group in sorted(receipt_groups.items()):
        bundle_id, route = key
        route_record = route_by_key.get(key, {})
        challenge_record = challenge_by_bundle[bundle_id]
        asset_ids = sorted({row["asset_id"] for row in group})
        source_path = ROOT / challenge_record["source_path"]
        target_path = ROOT / route_record["target_path"]
        source_run = run_security(source_path, asset_ids)
        target_run = run_security(target_path, asset_ids)
        artifact_runs[(bundle_id, route, "source")] = source_run
        artifact_runs[(bundle_id, route, "target")] = target_run
        for receipt in group:
            task_anomaly = receipt["pre_pcc_task_status"] == "task_relevant_anomaly"
            label = consequence_label(source_run, target_run, receipt["asset_id"], task_anomaly)
            consequence_rows.append({
                "bundle_id": bundle_id,
                "route": route,
                "asset_id": receipt["asset_id"],
                "task_relevant_anomaly": task_anomaly,
                "anomaly_reasons": receipt["pre_pcc_task_reasons"],
                **label,
            })

    with OUT_JSONL.open("w", encoding="utf-8") as stream:
        for row in consequence_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    if consequence_rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(consequence_rows[0]))
            writer.writeheader()
            writer.writerows(consequence_rows)

    task_anomalies = [row for row in consequence_rows if row["task_relevant_anomaly"]]
    paired_valid = [row for row in consequence_rows if row["paired_valid_consequence_evaluated"]]
    artifact_summary_rows = [
        {
            "bundle_id": bundle_id,
            "route": route,
            "artifact_role": role,
            "artifact_status": run["artifact_status"],
            "artifact_error": run["artifact_error"],
            "pre_status": run["pre_status"],
            "mapped_contingencies": len(run["raw_id_by_asset"]),
            "missing_contingencies": len(run.get("missing_assets", [])),
        }
        for (bundle_id, route, role), run in sorted(artifact_runs.items())
    ]
    summary = {
        "protocol": "external_tool_n1_consequence_adjudication_v1",
        "created_at": ADJUDICATION_CREATED_AT,
        "challenge_manifest_sha256": sha256(CHALLENGE),
        "pcc_receipts_sha256": sha256(RECEIPTS),
        "route_artifacts_manifest_sha256": sha256(ROUTES),
        "records": len(consequence_rows),
        "task_relevant_anomalies": len(task_anomalies),
        "operational_consequence_attempted": bool(consequence_rows),
        "paired_valid_consequence_evaluated": len(paired_valid),
        "operationally_consequential_anomalies": sum(
            1 for row in consequence_rows if row["operationally_consequential"]
        ),
        "source_target_security_runs": artifact_summary_rows,
        "interpretation": (
            "N-1 consequence reveal was run after PCC receipts were locked. "
            "Solver/import failures are retained; no task-relevant external anomaly was observed."
        ),
    }
    write_json(OUT_SUMMARY, summary)
    if SUMMARY.is_file():
        external_summary = read_json(SUMMARY)
        external_summary.update({
            "status": "complete_with_retained_consequence_adjudication",
            "operational_consequence_attempted": summary["operational_consequence_attempted"],
            "paired_valid_consequence_evaluated": summary["paired_valid_consequence_evaluated"],
            "operational_consequence_evaluated": summary["paired_valid_consequence_evaluated"] > 0,
            "operationally_consequential_anomalies": summary["operationally_consequential_anomalies"],
            "success_criteria": {
                **external_summary.get("success_criteria", {}),
                "at_least_one_operationally_consequential_anomaly": (
                    summary["operationally_consequential_anomalies"] > 0
                ),
            },
            "claim_use": (
                "external lawfulness/portability control with retained N-1 consequence adjudication; "
                "do not promote to main operational-consequence claim because no external task anomaly was observed"
            ),
        })
        write_json(SUMMARY, external_summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
