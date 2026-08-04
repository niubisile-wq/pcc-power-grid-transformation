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
WORKER = ROOT / "operations" / "stage2_import_worker.py"
ASSETS = ROOT / "results" / "stage2_import_assets"
WORKER_RESULTS = ROOT / "logs" / "stage2_import_workers"
CONSOLE_LOGS = ROOT / "logs" / "stage2_import_console"
TOOLS = ("pandapower", "pypowsybl", "veragrid")


def _descendant_rss(process: psutil.Process) -> int:
    total = 0
    for item in [process, *process.children(recursive=True)]:
        try:
            total += item.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def _run_attempt(
    row: dict[str, str], tool: str, timeout_seconds: int, resume: bool
) -> dict[str, object]:
    case_id = row["case_id"]
    source = BASE / row["relative_path"]
    asset_output = ASSETS / f"{case_id}__{tool}.csv"
    result_output = WORKER_RESULTS / f"{case_id}__{tool}.json"
    console_output = CONSOLE_LOGS / f"{case_id}__{tool}.txt"
    if resume and result_output.is_file():
        payload = json.loads(result_output.read_text(encoding="utf-8"))
        return {
            **{key: row[key] for key in ("case_id", "relative_path", "family", "representation", "sha256")},
            "tool": tool,
            "status": payload["status"],
            "asset_count": payload.get("asset_count", 0),
            "elapsed_seconds": payload.get("worker_elapsed_seconds", 0),
            "peak_rss_mb": "",
            "timed_out": False,
            "worker_exit_code": 0,
            "error_type": payload.get("error_type", ""),
            "error_message": payload.get("error_message", ""),
            "result_path": result_output.relative_to(ROOT).as_posix(),
            "console_log_path": console_output.relative_to(ROOT).as_posix() if console_output.is_file() else "",
            "resumed": True,
        }
    command = [
        sys.executable,
        str(WORKER),
        "--tool",
        tool,
        "--case-id",
        case_id,
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
        status = "timeout"
        payload: dict[str, object] = {}
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
        **{key: row[key] for key in ("case_id", "relative_path", "family", "representation", "sha256")},
        "tool": tool,
        "status": status,
        "asset_count": payload.get("asset_count", 0),
        "elapsed_seconds": elapsed,
        "peak_rss_mb": peak_rss / (1024 * 1024),
        "timed_out": timed_out,
        "worker_exit_code": process.returncode,
        "error_type": error_type,
        "error_message": error_message,
        "result_path": result_output.relative_to(ROOT).as_posix() if result_output.is_file() else "",
        "console_log_path": console_output.relative_to(ROOT).as_posix(),
        "resumed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    ASSETS.mkdir(parents=True, exist_ok=True)
    WORKER_RESULTS.mkdir(parents=True, exist_ok=True)
    CONSOLE_LOGS.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        models = [row for row in csv.DictReader(stream) if row["included"].lower() == "true"]
    attempts: list[dict[str, object]] = []
    for model_index, row in enumerate(models, 1):
        for tool in TOOLS:
            print(f"[{model_index}/{len(models)}] {row['case_id']} {tool}", flush=True)
            result = _run_attempt(row, tool, args.timeout_seconds, args.resume)
            attempts.append(result)
            print(
                f"  {result['status']} assets={result['asset_count']} elapsed={float(result['elapsed_seconds']):.2f}s peak={result['peak_rss_mb']}",
                flush=True,
            )
            pd.DataFrame(attempts).to_csv(ROOT / "results" / "stage2_import_matrix_results.csv", index=False)
    frame = pd.DataFrame(attempts)
    status_table = (
        frame.groupby(["tool", "status"], dropna=False).size().reset_index(name="count")
    )
    status_table.to_csv(ROOT / "results" / "stage2_import_matrix_status_by_tool.csv", index=False)
    latency = (
        frame.groupby("tool")["elapsed_seconds"]
        .agg(
            attempts="count",
            p50=lambda values: values.quantile(0.50),
            p95=lambda values: values.quantile(0.95),
            p99=lambda values: values.quantile(0.99),
            maximum="max",
        )
        .reset_index()
    )
    latency.to_csv(ROOT / "results" / "stage2_import_latency_summary.csv", index=False)
    summary = {
        "included_models": len(models),
        "tools": list(TOOLS),
        "expected_attempts": len(models) * len(TOOLS),
        "recorded_attempts": len(frame),
        "successes": int((frame.status == "success").sum()),
        "failures": int((frame.status != "success").sum()),
        "timeouts": int(frame.timed_out.astype(bool).sum()),
        "complete_denominator": len(frame) == len(models) * len(TOOLS),
        "status_counts": frame.status.value_counts().to_dict(),
    }
    (ROOT / "results" / "stage2_import_matrix_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
