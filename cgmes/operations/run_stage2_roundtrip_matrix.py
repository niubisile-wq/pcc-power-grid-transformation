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
DIRECT = ROOT / "results" / "stage2_import_matrix_results.csv"
BOUNDARY_RETRY = ROOT / "results" / "stage2_boundary_retry_results.csv"
EXPORT_WORKER = ROOT / "operations" / "stage2_export_worker.py"
IMPORT_WORKER = ROOT / "operations" / "stage2_import_worker.py"
EXPORTS = ROOT / "results" / "stage2_roundtrip_exports"
ASSETS = ROOT / "results" / "stage2_roundtrip_assets"
WORKER_RESULTS = ROOT / "logs" / "stage2_roundtrip_workers"
CONSOLE_LOGS = ROOT / "logs" / "stage2_roundtrip_console"
EXPORTERS = ("veragrid", "pypowsybl")
TARGETS = ("pandapower", "pypowsybl", "veragrid")


def _descendant_rss(process: psutil.Process) -> int:
    total = 0
    for item in [process, *process.children(recursive=True)]:
        try:
            total += item.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def _run(command: list[str], timeout_seconds: int, console: Path) -> dict[str, object]:
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
    console.write_text(stdout, encoding="utf-8")
    return {
        "elapsed_seconds": time.perf_counter() - started,
        "peak_rss_mb": peak_rss / (1024 * 1024),
        "timed_out": timed_out,
        "worker_exit_code": process.returncode,
    }


def _payload(result_path: Path, run: dict[str, object]) -> dict[str, object]:
    if run["timed_out"]:
        return {"status": "timeout", "error_type": "TimeoutExpired", "error_message": "worker timeout"}
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))
    return {
        "status": "worker_crash",
        "error_type": "MissingWorkerResult",
        "error_message": f"worker exited {run['worker_exit_code']} without result",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    for path in (EXPORTS, ASSETS, WORKER_RESULTS, CONSOLE_LOGS):
        path.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        models = [row for row in csv.DictReader(stream) if row["included"].lower() == "true"]
    direct = pd.read_csv(DIRECT)
    direct_status = {
        (str(row.case_id), str(row.tool)): str(row.status)
        for row in direct.itertuples(index=False)
    }
    retry = pd.read_csv(BOUNDARY_RETRY)
    retry_by_case = retry.set_index("case_id").to_dict("index")
    rows: list[dict[str, object]] = []

    for model_index, model in enumerate(models, 1):
        case_id = model["case_id"]
        raw_source = BASE / model["relative_path"]
        boundary = BASE / model["boundary_relative_path"] if model["boundary_relative_path"] else None
        for exporter in EXPORTERS:
            export = EXPORTS / f"{case_id}__{exporter}.zip"
            export_result = WORKER_RESULTS / f"{case_id}__{exporter}__export.json"
            export_console = CONSOLE_LOGS / f"{case_id}__{exporter}__export.txt"
            source = raw_source
            dependency_mode = "raw_model"
            if exporter == "pypowsybl" and direct_status[(case_id, "pypowsybl")] != "success":
                source = ROOT / str(retry_by_case[case_id]["combined_relative_path"])
                dependency_mode = "raw_model+matched_official_boundary"
            print(f"[{model_index}/{len(models)}] {case_id} {exporter} export", flush=True)
            if args.resume and export_result.is_file():
                run = {"elapsed_seconds": 0.0, "peak_rss_mb": "", "timed_out": False, "worker_exit_code": 0}
                payload = json.loads(export_result.read_text(encoding="utf-8"))
                resumed = True
            else:
                command = [
                    sys.executable,
                    str(EXPORT_WORKER),
                    "--tool", exporter,
                    "--case-id", case_id,
                    "--source", str(source),
                    "--export-output", str(export),
                    "--result-output", str(export_result),
                ]
                if exporter == "veragrid" and boundary is not None:
                    command.extend(["--boundary", str(boundary)])
                run = _run(command, args.timeout_seconds, export_console)
                payload = _payload(export_result, run)
                resumed = False
            export_row = {
                "case_id": case_id,
                "family": model["family"],
                "representation": model["representation"],
                "exporter": exporter,
                "target_tool": "",
                "stage": "export",
                "route": f"official_cgmes->{exporter}->cgmes",
                "dependency_mode": dependency_mode,
                "status": payload["status"],
                "source_path": source.relative_to(ROOT).as_posix(),
                "export_path": export.relative_to(ROOT).as_posix() if export.is_file() else "",
                "export_sha256": payload.get("export_sha256", ""),
                "export_size_bytes": payload.get("export_size_bytes", 0),
                "asset_count": 0,
                **run,
                "error_type": payload.get("error_type", ""),
                "error_message": payload.get("error_message", ""),
                "worker_result_path": export_result.relative_to(ROOT).as_posix() if export_result.is_file() else "",
                "console_log_path": export_console.relative_to(ROOT).as_posix() if export_console.is_file() else "",
                "resumed": resumed,
            }
            rows.append(export_row)
            print(f"  {export_row['status']} elapsed={export_row['elapsed_seconds']}", flush=True)

            for target in TARGETS:
                route = f"official_cgmes->{exporter}->cgmes->{target}"
                import_result = WORKER_RESULTS / f"{case_id}__{exporter}__to_{target}.json"
                import_console = CONSOLE_LOGS / f"{case_id}__{exporter}__to_{target}.txt"
                asset_output = ASSETS / f"{case_id}__{exporter}__to_{target}.csv"
                if payload["status"] != "success":
                    row = {
                        **{k: export_row[k] for k in ("case_id", "family", "representation", "exporter", "dependency_mode")},
                        "target_tool": target,
                        "stage": "reimport",
                        "route": route,
                        "status": "not_attempted_export_failed",
                        "source_path": export_row["source_path"],
                        "export_path": "",
                        "export_sha256": "",
                        "export_size_bytes": 0,
                        "asset_count": 0,
                        "elapsed_seconds": 0.0,
                        "peak_rss_mb": "",
                        "timed_out": False,
                        "worker_exit_code": "",
                        "error_type": "UpstreamExportFailed",
                        "error_message": export_row["error_message"],
                        "worker_result_path": "",
                        "console_log_path": "",
                        "resumed": False,
                    }
                    rows.append(row)
                    continue
                print(f"  reimport {target}", flush=True)
                if args.resume and import_result.is_file():
                    import_run = {"elapsed_seconds": 0.0, "peak_rss_mb": "", "timed_out": False, "worker_exit_code": 0}
                    import_payload = json.loads(import_result.read_text(encoding="utf-8"))
                    import_resumed = True
                else:
                    command = [
                        sys.executable,
                        str(IMPORT_WORKER),
                        "--tool", target,
                        "--case-id", f"{case_id}__{exporter}_roundtrip",
                        "--source", str(export),
                        "--asset-output", str(asset_output),
                        "--result-output", str(import_result),
                    ]
                    import_run = _run(command, args.timeout_seconds, import_console)
                    import_payload = _payload(import_result, import_run)
                    import_resumed = False
                row = {
                    **{k: export_row[k] for k in ("case_id", "family", "representation", "exporter", "dependency_mode")},
                    "target_tool": target,
                    "stage": "reimport",
                    "route": route,
                    "status": import_payload["status"],
                    "source_path": export_row["source_path"],
                    "export_path": export.relative_to(ROOT).as_posix(),
                    "export_sha256": export_row["export_sha256"],
                    "export_size_bytes": export_row["export_size_bytes"],
                    "asset_count": import_payload.get("asset_count", 0),
                    **import_run,
                    "error_type": import_payload.get("error_type", ""),
                    "error_message": import_payload.get("error_message", ""),
                    "worker_result_path": import_result.relative_to(ROOT).as_posix() if import_result.is_file() else "",
                    "console_log_path": import_console.relative_to(ROOT).as_posix() if import_console.is_file() else "",
                    "resumed": import_resumed,
                }
                rows.append(row)
                print(f"    {row['status']} assets={row['asset_count']} elapsed={row['elapsed_seconds']}", flush=True)
            pd.DataFrame(rows).to_csv(ROOT / "results" / "stage2_roundtrip_matrix_results.csv", index=False)

    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "results" / "stage2_roundtrip_matrix_results.csv", index=False)
    by_route = frame.groupby(["stage", "exporter", "target_tool", "status"], dropna=False).size().reset_index(name="count")
    by_route.to_csv(ROOT / "results" / "stage2_roundtrip_status_by_route.csv", index=False)
    latency = (
        frame.groupby(["stage", "exporter", "target_tool"], dropna=False)["elapsed_seconds"]
        .agg(attempts="count", p50=lambda x: x.quantile(.5), p95=lambda x: x.quantile(.95), p99=lambda x: x.quantile(.99), maximum="max")
        .reset_index()
    )
    latency.to_csv(ROOT / "results" / "stage2_roundtrip_latency_summary.csv", index=False)
    expected = len(models) * len(EXPORTERS) * (1 + len(TARGETS))
    summary = {
        "models": len(models),
        "exporters": list(EXPORTERS),
        "reimport_targets": list(TARGETS),
        "expected_attempt_rows": expected,
        "recorded_attempt_rows": len(frame),
        "complete_denominator": len(frame) == expected,
        "export_successes": int(((frame.stage == "export") & (frame.status == "success")).sum()),
        "export_failures": int(((frame.stage == "export") & (frame.status != "success")).sum()),
        "reimport_successes": int(((frame.stage == "reimport") & (frame.status == "success")).sum()),
        "reimport_failures_or_not_attempted": int(((frame.stage == "reimport") & (frame.status != "success")).sum()),
        "status_counts": frame.status.value_counts().to_dict(),
    }
    (ROOT / "results" / "stage2_roundtrip_matrix_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
