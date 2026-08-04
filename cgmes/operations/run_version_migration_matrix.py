from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "operations"))

from run_stage2_roundtrip_matrix import _payload, _run  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig"
REGISTRY = ROOT / "corpus" / "development_model_registry.csv"
DIRECT = ROOT / "results" / "stage2_import_matrix_results.csv"
EXPORT_WORKER = ROOT / "operations" / "stage2_export_worker.py"
IMPORT_WORKER = ROOT / "operations" / "stage2_import_worker.py"
EXPORTS = ROOT / "results" / "version_migration_exports"
ASSETS = ROOT / "results" / "version_migration_assets"
WORKERS = ROOT / "logs" / "version_migration_workers"
CONSOLE = ROOT / "logs" / "version_migration_console"
TARGETS = ("pandapower", "pypowsybl", "veragrid")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    for path in (EXPORTS, ASSETS, WORKERS, CONSOLE):
        path.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        models = [
            row for row in csv.DictReader(stream) if row["included"].lower() == "true"
        ]
    direct = pd.read_csv(DIRECT, keep_default_na=False)
    source_import = {
        str(row.case_id): str(row.status)
        for row in direct[direct.tool == "pypowsybl"].itertuples(index=False)
    }
    if len(models) != 32 or len(source_import) != 32:
        raise RuntimeError("Frozen CGMES 2.4.15 migration denominator is incomplete")

    rows: list[dict[str, object]] = []
    output = ROOT / "results" / "version_migration_matrix_results.csv"
    for index, model in enumerate(models, 1):
        case_id = model["case_id"]
        source = BASE / model["relative_path"]
        export = EXPORTS / f"{case_id}__pypowsybl__cgmes3.zip"
        export_result = WORKERS / f"{case_id}__export.json"
        export_console = CONSOLE / f"{case_id}__export.txt"
        print(f"[{index}/{len(models)}] {case_id} migrate 2.4.15 -> 3.0.0", flush=True)
        if args.resume and export_result.is_file():
            export_run = {
                "elapsed_seconds": 0.0,
                "peak_rss_mb": "",
                "timed_out": False,
                "worker_exit_code": 0,
            }
            export_payload = json.loads(export_result.read_text(encoding="utf-8"))
            resumed = True
        else:
            command = [
                sys.executable,
                str(EXPORT_WORKER),
                "--tool",
                "pypowsybl",
                "--case-id",
                case_id,
                "--source",
                str(source),
                "--cgmes-version",
                "3.0.0",
                "--export-output",
                str(export),
                "--result-output",
                str(export_result),
            ]
            export_run = _run(command, args.timeout_seconds, export_console)
            export_payload = _payload(export_result, export_run)
            resumed = False
        common = {
            "case_id": case_id,
            "family": model["family"],
            "split": "development",
            "source_cgmes_version": "2.4.15",
            "target_cgmes_version": "3.0.0",
            "exporter": "pypowsybl",
            "source_path": source.relative_to(ROOT).as_posix(),
            "source_sha256": model["sha256"],
            "source_direct_import_status": source_import[case_id],
        }
        export_row = {
            **common,
            "target_tool": "",
            "stage": "export",
            "route": "official_cgmes_2.4.15->pypowsybl->cgmes_3.0.0",
            "status": export_payload["status"],
            "export_path": export.relative_to(ROOT).as_posix() if export.is_file() else "",
            "export_sha256": export_payload.get("export_sha256", ""),
            "export_size_bytes": export_payload.get("export_size_bytes", 0),
            "asset_count": 0,
            **export_run,
            "error_type": export_payload.get("error_type", ""),
            "error_message": export_payload.get("error_message", ""),
            "worker_result_path": export_result.relative_to(ROOT).as_posix()
            if export_result.is_file()
            else "",
            "console_log_path": export_console.relative_to(ROOT).as_posix()
            if export_console.is_file()
            else "",
            "resumed": resumed,
        }
        rows.append(export_row)
        print(f"  export {export_row['status']}", flush=True)

        for target in TARGETS:
            route = f"official_cgmes_2.4.15->pypowsybl->cgmes_3.0.0->{target}"
            result_path = WORKERS / f"{case_id}__to_{target}.json"
            console_path = CONSOLE / f"{case_id}__to_{target}.txt"
            asset_path = ASSETS / f"{case_id}__to_{target}.csv"
            if export_payload["status"] != "success":
                rows.append(
                    {
                        **common,
                        "target_tool": target,
                        "stage": "reimport",
                        "route": route,
                        "status": "not_attempted_export_failed",
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
                )
                continue
            if args.resume and result_path.is_file():
                import_run = {
                    "elapsed_seconds": 0.0,
                    "peak_rss_mb": "",
                    "timed_out": False,
                    "worker_exit_code": 0,
                }
                import_payload = json.loads(result_path.read_text(encoding="utf-8"))
                import_resumed = True
            else:
                command = [
                    sys.executable,
                    str(IMPORT_WORKER),
                    "--tool",
                    target,
                    "--case-id",
                    f"{case_id}__cgmes3_migration",
                    "--source",
                    str(export),
                    "--cgmes-version",
                    "3.0.0",
                    "--asset-output",
                    str(asset_path),
                    "--result-output",
                    str(result_path),
                ]
                import_run = _run(command, args.timeout_seconds, console_path)
                import_payload = _payload(result_path, import_run)
                import_resumed = False
            rows.append(
                {
                    **common,
                    "target_tool": target,
                    "stage": "reimport",
                    "route": route,
                    "status": import_payload["status"],
                    "export_path": export.relative_to(ROOT).as_posix(),
                    "export_sha256": export_row["export_sha256"],
                    "export_size_bytes": export_row["export_size_bytes"],
                    "asset_count": import_payload.get("asset_count", 0),
                    **import_run,
                    "error_type": import_payload.get("error_type", ""),
                    "error_message": import_payload.get("error_message", ""),
                    "worker_result_path": result_path.relative_to(ROOT).as_posix()
                    if result_path.is_file()
                    else "",
                    "console_log_path": console_path.relative_to(ROOT).as_posix()
                    if console_path.is_file()
                    else "",
                    "resumed": import_resumed,
                }
            )
            print(f"  {target} {rows[-1]['status']} assets={rows[-1]['asset_count']}", flush=True)
        pd.DataFrame(rows).to_csv(output, index=False)

    frame = pd.DataFrame(rows)
    frame.to_csv(output, index=False)
    summary = {
        "evidence_role": "development_version_migration_not_final_holdout",
        "models": 32,
        "source_cgmes_version": "2.4.15",
        "target_cgmes_version": "3.0.0",
        "expected_rows": 128,
        "recorded_rows": len(frame),
        "complete_denominator": len(frame) == 128,
        "export_successes": int(
            ((frame.stage == "export") & (frame.status == "success")).sum()
        ),
        "export_failures": int(
            ((frame.stage == "export") & (frame.status != "success")).sum()
        ),
        "reimport_successes": int(
            ((frame.stage == "reimport") & (frame.status == "success")).sum()
        ),
        "reimport_failures_or_not_attempted": int(
            ((frame.stage == "reimport") & (frame.status != "success")).sum()
        ),
        "status_counts": frame.status.value_counts().to_dict(),
    }
    (ROOT / "results" / "version_migration_matrix_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
