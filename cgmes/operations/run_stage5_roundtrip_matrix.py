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


REGISTRY = ROOT / "corpus" / "validation_model_registry.csv"
DIRECT = ROOT / "results" / "stage5_import_matrix_results.csv"
EXPORT_WORKER = ROOT / "operations" / "stage2_export_worker.py"
IMPORT_WORKER = ROOT / "operations" / "stage2_import_worker.py"
EXPORTS = ROOT / "results" / "stage5_roundtrip_exports"
ASSETS = ROOT / "results" / "stage5_roundtrip_assets"
WORKER_RESULTS = ROOT / "logs" / "stage5_roundtrip_workers"
CONSOLE_LOGS = ROOT / "logs" / "stage5_roundtrip_console"
EXPORTERS = ("veragrid", "pypowsybl")
TARGETS = ("pandapower", "pypowsybl", "veragrid")
CGMES_VERSION = "3.0.0"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    for path in (EXPORTS, ASSETS, WORKER_RESULTS, CONSOLE_LOGS):
        path.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        models = [
            row
            for row in csv.DictReader(stream)
            if row["included"].lower() == "true"
        ]
    if not DIRECT.is_file():
        raise SystemExit("Run operations/run_stage5_import_matrix.py first")
    direct = pd.read_csv(DIRECT, keep_default_na=False)
    if len(direct) != len(models) * 3:
        raise SystemExit("Stage 5 direct-import denominator is incomplete")
    direct_status = {
        (str(row.case_id), str(row.tool)): str(row.status)
        for row in direct.itertuples(index=False)
    }
    rows: list[dict[str, object]] = []
    output = ROOT / "results" / "stage5_roundtrip_matrix_results.csv"
    for model_index, model in enumerate(models, 1):
        case_id = model["case_id"]
        source = ROOT / model["package_relative_path"]
        for exporter in EXPORTERS:
            export = EXPORTS / f"{case_id}__{exporter}.zip"
            export_result = WORKER_RESULTS / f"{case_id}__{exporter}__export.json"
            export_console = CONSOLE_LOGS / f"{case_id}__{exporter}__export.txt"
            print(
                f"[{model_index}/{len(models)}] {case_id} {exporter} export",
                flush=True,
            )
            if args.resume and export_result.is_file():
                run = {
                    "elapsed_seconds": 0.0,
                    "peak_rss_mb": "",
                    "timed_out": False,
                    "worker_exit_code": 0,
                }
                payload = json.loads(export_result.read_text(encoding="utf-8"))
                resumed = True
            else:
                command = [
                    sys.executable,
                    str(EXPORT_WORKER),
                    "--tool",
                    exporter,
                    "--case-id",
                    case_id,
                    "--source",
                    str(source),
                    "--cgmes-version",
                    CGMES_VERSION,
                    "--export-output",
                    str(export),
                    "--result-output",
                    str(export_result),
                ]
                run = _run(command, args.timeout_seconds, export_console)
                payload = _payload(export_result, run)
                resumed = False
            export_row = {
                "case_id": case_id,
                "family": model["family"],
                "split": model["split"],
                "cgmes_version": CGMES_VERSION,
                "exporter": exporter,
                "target_tool": "",
                "stage": "export",
                "route": f"official_cgmes3->{exporter}->cgmes3",
                "direct_import_status_for_exporter": direct_status[
                    (case_id, exporter)
                ],
                "status": payload["status"],
                "source_path": source.relative_to(ROOT).as_posix(),
                "source_sha256": model["package_sha256"],
                "export_path": export.relative_to(ROOT).as_posix()
                if export.is_file()
                else "",
                "export_sha256": payload.get("export_sha256", ""),
                "export_size_bytes": payload.get("export_size_bytes", 0),
                "asset_count": 0,
                **run,
                "error_type": payload.get("error_type", ""),
                "error_message": payload.get("error_message", ""),
                "worker_result_path": export_result.relative_to(ROOT).as_posix()
                if export_result.is_file()
                else "",
                "console_log_path": export_console.relative_to(ROOT).as_posix()
                if export_console.is_file()
                else "",
                "resumed": resumed,
            }
            rows.append(export_row)
            print(f"  {export_row['status']}", flush=True)
            for target in TARGETS:
                route = f"official_cgmes3->{exporter}->cgmes3->{target}"
                import_result = (
                    WORKER_RESULTS / f"{case_id}__{exporter}__to_{target}.json"
                )
                import_console = (
                    CONSOLE_LOGS / f"{case_id}__{exporter}__to_{target}.txt"
                )
                asset_output = ASSETS / f"{case_id}__{exporter}__to_{target}.csv"
                if payload["status"] != "success":
                    rows.append(
                        {
                            **{
                                key: export_row[key]
                                for key in (
                                    "case_id",
                                    "family",
                                    "split",
                                    "cgmes_version",
                                    "exporter",
                                    "source_path",
                                    "source_sha256",
                                    "direct_import_status_for_exporter",
                                )
                            },
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
                print(f"  reimport {target}", flush=True)
                if args.resume and import_result.is_file():
                    import_run = {
                        "elapsed_seconds": 0.0,
                        "peak_rss_mb": "",
                        "timed_out": False,
                        "worker_exit_code": 0,
                    }
                    import_payload = json.loads(
                        import_result.read_text(encoding="utf-8")
                    )
                    import_resumed = True
                else:
                    command = [
                        sys.executable,
                        str(IMPORT_WORKER),
                        "--tool",
                        target,
                        "--case-id",
                        f"{case_id}__{exporter}_roundtrip",
                        "--source",
                        str(export),
                        "--cgmes-version",
                        CGMES_VERSION,
                        "--asset-output",
                        str(asset_output),
                        "--result-output",
                        str(import_result),
                    ]
                    import_run = _run(
                        command, args.timeout_seconds, import_console
                    )
                    import_payload = _payload(import_result, import_run)
                    import_resumed = False
                rows.append(
                    {
                        **{
                            key: export_row[key]
                            for key in (
                                "case_id",
                                "family",
                                "split",
                                "cgmes_version",
                                "exporter",
                                "source_path",
                                "source_sha256",
                                "direct_import_status_for_exporter",
                            )
                        },
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
                        "worker_result_path": import_result.relative_to(ROOT).as_posix()
                        if import_result.is_file()
                        else "",
                        "console_log_path": import_console.relative_to(ROOT).as_posix()
                        if import_console.is_file()
                        else "",
                        "resumed": import_resumed,
                    }
                )
                print(
                    f"    {rows[-1]['status']} assets={rows[-1]['asset_count']}",
                    flush=True,
                )
            pd.DataFrame(rows).to_csv(output, index=False)
    frame = pd.DataFrame(rows)
    frame.to_csv(output, index=False)
    by_route = (
        frame.groupby(
            ["stage", "exporter", "target_tool", "status"], dropna=False
        )
        .size()
        .reset_index(name="count")
    )
    by_route.to_csv(
        ROOT / "results" / "stage5_roundtrip_status_by_route.csv", index=False
    )
    expected = len(models) * len(EXPORTERS) * (1 + len(TARGETS))
    summary = {
        "evidence_role": "internal_validation_not_untouched_final_holdout",
        "cgmes_version": CGMES_VERSION,
        "models": len(models),
        "expected_attempt_rows": expected,
        "recorded_attempt_rows": len(frame),
        "complete_denominator": len(frame) == expected,
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
    (ROOT / "results" / "stage5_roundtrip_matrix_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
