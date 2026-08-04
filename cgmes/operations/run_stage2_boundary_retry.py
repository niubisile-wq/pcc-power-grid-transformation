from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import psutil


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig"
REGISTRY = ROOT / "corpus" / "development_model_registry.csv"
RAW_RESULTS = ROOT / "results" / "stage2_import_matrix_results.csv"
WORKER = ROOT / "operations" / "stage2_import_worker.py"
COMBINED = ROOT / "results" / "stage2_boundary_inputs"
ASSETS = ROOT / "results" / "stage2_boundary_retry_assets"
WORKER_RESULTS = ROOT / "logs" / "stage2_boundary_retry_workers"
CONSOLE_LOGS = ROOT / "logs" / "stage2_boundary_retry_console"


def _descendant_rss(process: psutil.Process) -> int:
    total = 0
    for item in [process, *process.children(recursive=True)]:
        try:
            total += item.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def _combine_archives(model: Path, boundary: Path, output: Path) -> list[str]:
    # Import locally so the deterministic packaging implementation has a
    # single source of truth for Stage 1 and Stage 2.
    from package_roundtrip_with_boundary import combine_archives

    output.parent.mkdir(parents=True, exist_ok=True)
    return combine_archives(model, boundary, output)


def _classify_raw_failure(error_message: str) -> str:
    message = error_message.lower()
    if "nominalvoltage not found for basevoltage" in message:
        return "missing_boundary_base_voltage_reference"
    if "not found" in message or "unknown" in message:
        return "unresolved_reference"
    return "other_import_error"


def _run_worker(case_id: str, source: Path, timeout_seconds: int) -> dict[str, object]:
    result_output = WORKER_RESULTS / f"{case_id}__pypowsybl__with_boundary.json"
    asset_output = ASSETS / f"{case_id}__pypowsybl__with_boundary.csv"
    console_output = CONSOLE_LOGS / f"{case_id}__pypowsybl__with_boundary.txt"
    command = [
        sys.executable,
        str(WORKER),
        "--tool",
        "pypowsybl",
        "--case-id",
        case_id + "__with_boundary",
        "--source",
        str(source),
        "--asset-output",
        str(asset_output),
        "--result-output",
        str(result_output),
    ]
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    ps_process = psutil.Process(process.pid)
    peak_rss = 0
    timed_out = False
    while process.poll() is None:
        peak_rss = max(peak_rss, _descendant_rss(ps_process))
        if time.perf_counter() - started > timeout_seconds:
            timed_out = True
            for child in ps_process.children(recursive=True):
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            process.kill()
            break
        time.sleep(0.1)
    stdout, _ = process.communicate()
    console_output.write_text(stdout, encoding="utf-8")
    elapsed = time.perf_counter() - started
    if timed_out:
        payload: dict[str, object] = {}
        status = "timeout"
        error_type = "TimeoutExpired"
        error_message = f"Exceeded {timeout_seconds} seconds"
    elif result_output.is_file():
        payload = json.loads(result_output.read_text(encoding="utf-8"))
        status = str(payload["status"])
        error_type = str(payload.get("error_type", ""))
        error_message = str(payload.get("error_message", ""))
    else:
        payload = {}
        status = "worker_crash"
        error_type = "MissingWorkerResult"
        error_message = f"Worker exited {process.returncode} without a result file"
    return {
        "retry_status": status,
        "retry_asset_count": payload.get("asset_count", 0),
        "retry_elapsed_seconds": elapsed,
        "retry_peak_rss_mb": peak_rss / (1024 * 1024),
        "retry_timed_out": timed_out,
        "retry_worker_exit_code": process.returncode,
        "retry_error_type": error_type,
        "retry_error_message": error_message,
        "retry_result_path": result_output.relative_to(ROOT).as_posix() if result_output.is_file() else "",
        "retry_console_log_path": console_output.relative_to(ROOT).as_posix(),
        "retry_asset_path": asset_output.relative_to(ROOT).as_posix() if asset_output.is_file() else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    for path in (COMBINED, ASSETS, WORKER_RESULTS, CONSOLE_LOGS):
        path.mkdir(parents=True, exist_ok=True)

    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        registry = {row["case_id"]: row for row in csv.DictReader(stream)}
    raw = pd.read_csv(RAW_RESULTS)
    failures = raw[(raw["tool"] == "pypowsybl") & (raw["status"] != "success")].copy()
    rows: list[dict[str, object]] = []
    for index, failure in enumerate(failures.to_dict("records"), 1):
        case_id = str(failure["case_id"])
        reg = registry[case_id]
        boundary_relative_path = reg.get("boundary_relative_path", "")
        print(f"[{index}/{len(failures)}] {case_id}", flush=True)
        if not boundary_relative_path:
            row = {
                "case_id": case_id,
                "family": failure["family"],
                "representation": failure["representation"],
                "raw_status": failure["status"],
                "raw_error_type": failure["error_type"],
                "raw_error_message": failure["error_message"],
                "raw_failure_class": _classify_raw_failure(str(failure["error_message"])),
                "boundary_relative_path": "",
                "retry_status": "not_attempted_missing_boundary",
            }
            rows.append(row)
            continue
        model = BASE / str(reg["relative_path"])
        boundary = BASE / boundary_relative_path
        combined = COMBINED / f"{case_id}__with_official_boundary.zip"
        provenance = _combine_archives(model, boundary, combined)
        retry = _run_worker(case_id, combined, args.timeout_seconds)
        row = {
            "case_id": case_id,
            "family": failure["family"],
            "representation": failure["representation"],
            "raw_status": failure["status"],
            "raw_error_type": failure["error_type"],
            "raw_error_message": failure["error_message"],
            "raw_failure_class": _classify_raw_failure(str(failure["error_message"])),
            "model_relative_path": reg["relative_path"],
            "boundary_relative_path": boundary_relative_path,
            "combined_relative_path": combined.relative_to(ROOT).as_posix(),
            "packaging_entry_count": len(provenance),
            **retry,
        }
        rows.append(row)
        pd.DataFrame(rows).to_csv(ROOT / "results" / "stage2_boundary_retry_results.csv", index=False)
        print(
            f"  {row['retry_status']} assets={row.get('retry_asset_count', 0)} "
            f"elapsed={float(row.get('retry_elapsed_seconds', 0)):.2f}s",
            flush=True,
        )

    result = pd.DataFrame(rows)
    result.to_csv(ROOT / "results" / "stage2_boundary_retry_results.csv", index=False)
    taxonomy = (
        result.groupby(["raw_failure_class", "retry_status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    taxonomy.to_csv(ROOT / "results" / "stage2_import_failure_taxonomy.csv", index=False)
    summary = {
        "raw_failure_denominator": len(result),
        "raw_failures_retained": True,
        "retry_route": "raw_model+matched_official_boundary->pypowsybl",
        "retry_attempts": int(result["retry_status"].ne("not_attempted_missing_boundary").sum()),
        "retry_successes": int((result["retry_status"] == "success").sum()),
        "retry_failures": int((result["retry_status"] != "success").sum()),
        "raw_failure_classes": result["raw_failure_class"].value_counts().to_dict(),
        "retry_status_counts": result["retry_status"].value_counts().to_dict(),
        "packaging_is_semantic_edit": False,
    }
    (ROOT / "results" / "stage2_boundary_retry_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
