from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import psutil


ROOT = Path(__file__).resolve().parents[1]
SHAPES_ROOT = ROOT / "corpus" / "extracted" / "cgmes3_profiles"
WORKER = ROOT / "validation" / "run_shacl_worker.py"
WORKER_RESULTS = ROOT / "logs" / "converted_shacl_workers"
CONSOLE_LOGS = ROOT / "logs" / "converted_shacl_console"
REPORTS = ROOT / "results" / "converted_shacl_reports"
SELECTIONS = ROOT / "results" / "converted_shacl_selections"


PAYLOAD_FIELDS = (
    "status",
    "rdf_parse_valid",
    "xml_file_count",
    "data_triple_count",
    "shape_file_count",
    "shape_triple_count",
    "datatype_mapping_property_count",
    "datatype_mapping_ambiguous_property_count",
    "datatype_enriched_literal_count",
    "datatype_invalid_lexical_count",
    "shacl_conforms",
    "validation_result_count",
    "violation_count",
    "warning_count",
    "info_count",
    "other_severity_count",
    "worker_elapsed_seconds",
    "error_type",
    "error_message",
)


def _descendant_rss(process: psutil.Process) -> int:
    total = 0
    for item in [process, *process.children(recursive=True)]:
        try:
            total += item.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def _artifacts() -> list[dict[str, str]]:
    stage5 = pd.read_csv(
        ROOT / "results" / "stage5_roundtrip_matrix_results.csv",
        keep_default_na=False,
    )
    migration = pd.read_csv(
        ROOT / "results" / "version_migration_matrix_results.csv",
        keep_default_na=False,
    )
    rows: list[dict[str, str]] = []
    for raw in stage5[(stage5.stage == "export") & (stage5.status == "success")].to_dict("records"):
        rows.append(
            {
                "artifact_group": "stage5_cgmes3_roundtrip_export",
                "evidence_role": "internal_validation_not_untouched_final_holdout",
                "case_id": str(raw["case_id"]),
                "family": str(raw["family"]),
                "exporter": str(raw["exporter"]),
                "artifact_path": str(raw["export_path"]),
                "artifact_sha256": str(raw["export_sha256"]),
            }
        )
    for raw in migration[(migration.stage == "export") & (migration.status == "success")].to_dict("records"):
        rows.append(
            {
                "artifact_group": "development_cgmes2415_to_cgmes3_export",
                "evidence_role": "development_version_migration_not_final_holdout",
                "case_id": str(raw["case_id"]),
                "family": str(raw["family"]),
                "exporter": str(raw["exporter"]),
                "artifact_path": str(raw["export_path"]),
                "artifact_sha256": str(raw["export_sha256"]),
            }
        )
    return rows


def _run(row: dict[str, str], timeout_seconds: int, resume: bool) -> dict[str, object]:
    artifact_id = f"{row['artifact_group']}__{row['case_id']}__{row['exporter']}"
    source = ROOT / row["artifact_path"]
    result_path = WORKER_RESULTS / f"{artifact_id}.json"
    console_path = CONSOLE_LOGS / f"{artifact_id}.txt"
    report_graph = REPORTS / f"{artifact_id}.ttl"
    report_text = REPORTS / f"{artifact_id}.txt"
    selection = SELECTIONS / f"{artifact_id}.json"
    common = {**row, "artifact_id": artifact_id}
    if resume and result_path.is_file():
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return {
            **common,
            **{key: payload.get(key, "") for key in PAYLOAD_FIELDS},
            "peak_rss_mb": "",
            "timed_out": False,
            "result_path": result_path.relative_to(ROOT).as_posix(),
            "report_graph_path": report_graph.relative_to(ROOT).as_posix()
            if report_graph.is_file()
            else "",
            "report_text_path": report_text.relative_to(ROOT).as_posix()
            if report_text.is_file()
            else "",
            "selection_path": selection.relative_to(ROOT).as_posix()
            if selection.is_file()
            else "",
            "resumed": True,
        }
    command = [
        sys.executable,
        str(WORKER),
        "--case-id",
        artifact_id,
        "--source",
        str(source),
        "--shapes-root",
        str(SHAPES_ROOT),
        "--result-output",
        str(result_path),
        "--report-graph-output",
        str(report_graph),
        "--report-text-output",
        str(report_text),
        "--selection-output",
        str(selection),
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
        time.sleep(0.2)
    stdout, _ = process.communicate()
    console_path.write_text(stdout, encoding="utf-8")
    elapsed = time.perf_counter() - started
    payload = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    status = "timeout" if timed_out else payload.get("status", "worker_crash")
    return {
        **common,
        "status": status,
        **{key: payload.get(key, "") for key in PAYLOAD_FIELDS if key != "status"},
        "worker_elapsed_seconds": payload.get("worker_elapsed_seconds", elapsed),
        "peak_rss_mb": peak_rss / (1024 * 1024),
        "timed_out": timed_out,
        "error_type": "TimeoutExpired" if timed_out else payload.get("error_type", "MissingWorkerResult"),
        "error_message": f"Exceeded {timeout_seconds} seconds" if timed_out else payload.get("error_message", ""),
        "result_path": result_path.relative_to(ROOT).as_posix() if result_path.is_file() else "",
        "report_graph_path": report_graph.relative_to(ROOT).as_posix() if report_graph.is_file() else "",
        "report_text_path": report_text.relative_to(ROOT).as_posix() if report_text.is_file() else "",
        "selection_path": selection.relative_to(ROOT).as_posix() if selection.is_file() else "",
        "resumed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    for path in (WORKER_RESULTS, CONSOLE_LOGS, REPORTS, SELECTIONS):
        path.mkdir(parents=True, exist_ok=True)
    artifacts = _artifacts()
    output = ROOT / "results" / "converted_cgmes3_shacl_validation_results.csv"
    rows: list[dict[str, object]] = []
    for index, artifact in enumerate(artifacts, 1):
        print(f"[{index}/{len(artifacts)}] {artifact['artifact_group']} {artifact['case_id']}", flush=True)
        result = _run(artifact, args.timeout_seconds, args.resume)
        rows.append(result)
        pd.DataFrame(rows).to_csv(output, index=False)
        print(f"  {result['status']} conforms={result['shacl_conforms']}", flush=True)
    frame = pd.DataFrame(rows)
    successful = frame[frame.status == "success"]
    summary = {
        "official_shapes": True,
        "expected_artifacts": len(artifacts),
        "recorded_artifacts": len(frame),
        "complete_denominator": len(frame) == len(artifacts),
        "source_route_failures_retained_in_matrix_tables": True,
        "successful_validations": len(successful),
        "execution_failures": int(frame.status.ne("success").sum()),
        "conforming_artifacts": int(successful.shacl_conforms.astype(str).str.lower().eq("true").sum()),
        "nonconforming_artifacts": int(successful.shacl_conforms.astype(str).str.lower().eq("false").sum()),
        "timeouts": int(frame.timed_out.astype(bool).sum()),
        "artifact_group_counts": frame.artifact_group.value_counts().to_dict(),
    }
    (ROOT / "results" / "converted_cgmes3_shacl_validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
