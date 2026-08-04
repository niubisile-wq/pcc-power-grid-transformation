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
REGISTRY = ROOT / "corpus" / "validation_model_registry.csv"
SHAPES_ROOT = ROOT / "corpus" / "extracted" / "cgmes3_profiles"
WORKER = ROOT / "validation" / "run_shacl_worker.py"
WORKER_RESULTS = ROOT / "logs" / "stage5_shacl_workers"
CONSOLE_LOGS = ROOT / "logs" / "stage5_shacl_console"
REPORTS = ROOT / "results" / "stage5_shacl_reports"
SELECTIONS = ROOT / "results" / "stage5_shacl_selections"


def _descendant_rss(process: psutil.Process) -> int:
    total = 0
    for item in [process, *process.children(recursive=True)]:
        try:
            total += item.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def _run(
    row: dict[str, str], timeout_seconds: int, resume: bool
) -> dict[str, object]:
    case_id = row["case_id"]
    source = ROOT / row["package_relative_path"]
    result_path = WORKER_RESULTS / f"{case_id}.json"
    console_path = CONSOLE_LOGS / f"{case_id}.txt"
    report_graph = REPORTS / f"{case_id}.ttl"
    report_text = REPORTS / f"{case_id}.txt"
    selection = SELECTIONS / f"{case_id}.json"
    if resume and result_path.is_file():
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return {
            "case_id": case_id,
            "family": row["family"],
            "split": row["split"],
            "package_relative_path": row["package_relative_path"],
            "package_sha256": row["package_sha256"],
            **{
                key: payload.get(key, "")
                for key in (
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
            },
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
        case_id,
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
    payload = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else {}
    )
    status = "timeout" if timed_out else payload.get("status", "worker_crash")
    error_type = (
        "TimeoutExpired"
        if timed_out
        else payload.get("error_type", "MissingWorkerResult")
    )
    error_message = (
        f"Exceeded {timeout_seconds} seconds"
        if timed_out
        else payload.get("error_message", "")
    )
    return {
        "case_id": case_id,
        "family": row["family"],
        "split": row["split"],
        "package_relative_path": row["package_relative_path"],
        "package_sha256": row["package_sha256"],
        "status": status,
        **{
            key: payload.get(key, "")
            for key in (
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
            )
        },
        "worker_elapsed_seconds": payload.get("worker_elapsed_seconds", elapsed),
        "peak_rss_mb": peak_rss / (1024 * 1024),
        "timed_out": timed_out,
        "error_type": error_type,
        "error_message": error_message,
        "result_path": result_path.relative_to(ROOT).as_posix()
        if result_path.is_file()
        else "",
        "report_graph_path": report_graph.relative_to(ROOT).as_posix()
        if report_graph.is_file()
        else "",
        "report_text_path": report_text.relative_to(ROOT).as_posix()
        if report_text.is_file()
        else "",
        "selection_path": selection.relative_to(ROOT).as_posix()
        if selection.is_file()
        else "",
        "resumed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    for path in (WORKER_RESULTS, CONSOLE_LOGS, REPORTS, SELECTIONS):
        path.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        models = [
            row
            for row in csv.DictReader(stream)
            if row["included"].lower() == "true"
        ]
    rows: list[dict[str, object]] = []
    output = ROOT / "results" / "cgmes_shacl_validation_results.csv"
    for index, row in enumerate(models, 1):
        print(f"[{index}/{len(models)}] {row['case_id']}", flush=True)
        result = _run(row, args.timeout_seconds, args.resume)
        rows.append(result)
        pd.DataFrame(rows).to_csv(output, index=False)
        print(
            f"  {result['status']} conforms={result['shacl_conforms']} "
            f"results={result['validation_result_count']} "
            f"elapsed={float(result['worker_elapsed_seconds']):.2f}s",
            flush=True,
        )
    frame = pd.DataFrame(rows)
    successful = frame[frame.status == "success"]
    summary = {
        "evidence_role": "internal_validation_not_untouched_final_holdout",
        "official_shapes": True,
        "official_shapes_source": "ENTSO-E CGMES Conformity Assessment Scheme Application Profiles v3.0.2, SHACL v3.0.0",
        "validation_engine": "pyshacl",
        "expected_artifacts": len(models),
        "recorded_artifacts": len(frame),
        "complete_denominator": len(frame) == len(models),
        "successful_validations": len(successful),
        "execution_failures": int((frame.status != "success").sum()),
        "conforming_artifacts": int(
            successful.shacl_conforms.astype(str).str.lower().eq("true").sum()
        ),
        "nonconforming_artifacts": int(
            successful.shacl_conforms.astype(str).str.lower().eq("false").sum()
        ),
        "total_validation_results": int(
            pd.to_numeric(successful.validation_result_count, errors="coerce")
            .fillna(0)
            .sum()
        ),
        "timeouts": int(frame.timed_out.astype(bool).sum()),
        "selection_policy": (
            "declared-profile-matched official constraints on a merged package graph; "
            "Explicit-CrossProfile selected and Implicit alternative excluded"
        ),
        "datatype_policy": (
            "untyped CIM/XML literals enriched only in the in-memory validation view "
            "from the selected official Simple SHACL sh:path/sh:datatype declarations; "
            "source archives remain byte-identical"
        ),
    }
    (ROOT / "results" / "cgmes_shacl_validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
