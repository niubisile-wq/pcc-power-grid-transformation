from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "operations"))

from package_roundtrip_with_boundary import combine_archives  # noqa: E402
from run_stage2_roundtrip_matrix import _payload, _run  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig"
REGISTRY = ROOT / "corpus" / "development_model_registry.csv"
MATRIX = ROOT / "results" / "stage2_roundtrip_matrix_results.csv"
IMPORT_WORKER = ROOT / "operations" / "stage2_import_worker.py"
COMBINED = ROOT / "results" / "stage2_roundtrip_with_boundary"
ASSETS = ROOT / "results" / "stage2_roundtrip_boundary_retry_assets"
WORKER_RESULTS = ROOT / "logs" / "stage2_roundtrip_boundary_retry_workers"
CONSOLE_LOGS = ROOT / "logs" / "stage2_roundtrip_boundary_retry_console"


def classify(message: str) -> str:
    lower = message.lower()
    if "nominalvoltage not found for basevoltage" in lower:
        return "missing_boundary_base_voltage_reference"
    if "null object" in lower:
        return "null_or_missing_referenced_object"
    if "busbarsection" in lower and "voltagelevel" in lower:
        return "missing_busbar_voltage_level_container"
    if "already defined" in lower or "duplicate" in lower:
        return "duplicate_identifier_or_object"
    return "other_reimport_error"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    for path in (COMBINED, ASSETS, WORKER_RESULTS, CONSOLE_LOGS):
        path.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        registry = {row["case_id"]: row for row in csv.DictReader(stream)}
    matrix = pd.read_csv(MATRIX, keep_default_na=False)
    failures = matrix[(matrix.stage == "reimport") & (matrix.status == "error")].copy()
    rows: list[dict[str, object]] = []
    for index, raw in enumerate(failures.to_dict("records"), 1):
        case_id = str(raw["case_id"])
        exporter = str(raw["exporter"])
        target = str(raw["target_tool"])
        boundary_relative = registry[case_id].get("boundary_relative_path", "")
        print(f"[{index}/{len(failures)}] {case_id} {exporter}->{target}", flush=True)
        base_row: dict[str, object] = {
            "case_id": case_id,
            "family": raw["family"],
            "representation": raw["representation"],
            "exporter": exporter,
            "target_tool": target,
            "raw_status": raw["status"],
            "raw_error_type": raw["error_type"],
            "raw_error_message": raw["error_message"],
            "raw_failure_class": classify(str(raw["error_message"])),
            "raw_failure_retained_in_denominator": True,
            "boundary_relative_path": boundary_relative,
        }
        if not boundary_relative:
            rows.append({**base_row, "retry_status": "not_attempted_no_registered_boundary"})
            continue
        export = ROOT / str(raw["export_path"])
        boundary = BASE / boundary_relative
        combined = COMBINED / f"{case_id}__{exporter}__with_official_boundary.zip"
        provenance = combine_archives(export, boundary, combined)
        stem = f"{case_id}__{exporter}__to_{target}__with_boundary"
        result_path = WORKER_RESULTS / f"{stem}.json"
        console_path = CONSOLE_LOGS / f"{stem}.txt"
        asset_path = ASSETS / f"{stem}.csv"
        if args.resume and result_path.is_file():
            run = {"elapsed_seconds": 0.0, "peak_rss_mb": "", "timed_out": False, "worker_exit_code": 0}
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            resumed = True
        else:
            command = [
                sys.executable,
                str(IMPORT_WORKER),
                "--tool", target,
                "--case-id", stem,
                "--source", str(combined),
                "--asset-output", str(asset_path),
                "--result-output", str(result_path),
            ]
            run = _run(command, args.timeout_seconds, console_path)
            payload = _payload(result_path, run)
            resumed = False
        row = {
            **base_row,
            "combined_relative_path": combined.relative_to(ROOT).as_posix(),
            "packaging_entry_count": len(provenance),
            "retry_status": payload["status"],
            "retry_asset_count": payload.get("asset_count", 0),
            "retry_error_type": payload.get("error_type", ""),
            "retry_error_message": payload.get("error_message", ""),
            "retry_result_path": result_path.relative_to(ROOT).as_posix() if result_path.is_file() else "",
            "retry_console_path": console_path.relative_to(ROOT).as_posix() if console_path.is_file() else "",
            "retry_asset_path": asset_path.relative_to(ROOT).as_posix() if asset_path.is_file() else "",
            "resumed": resumed,
            **run,
        }
        rows.append(row)
        pd.DataFrame(rows).to_csv(ROOT / "results" / "stage2_roundtrip_boundary_retry_results.csv", index=False)
        print(f"  {row['retry_status']} assets={row['retry_asset_count']}", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "results" / "stage2_roundtrip_boundary_retry_results.csv", index=False)
    taxonomy = frame.groupby(["raw_failure_class", "retry_status"], dropna=False).size().reset_index(name="count")
    taxonomy.to_csv(ROOT / "results" / "stage2_roundtrip_failure_taxonomy.csv", index=False)
    summary = {
        "raw_reimport_failure_denominator": len(frame),
        "retry_attempts": int(frame.retry_status.ne("not_attempted_no_registered_boundary").sum()),
        "retry_successes": int(frame.retry_status.eq("success").sum()),
        "retry_failures_or_not_attempted": int(frame.retry_status.ne("success").sum()),
        "raw_failures_retained": True,
        "status_counts": frame.retry_status.value_counts().to_dict(),
    }
    (ROOT / "results" / "stage2_roundtrip_boundary_retry_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
