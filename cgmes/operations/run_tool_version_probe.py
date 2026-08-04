from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "corpus" / "validation_model_registry.csv"
EXPORT_WORKER = ROOT / "operations" / "stage2_export_worker.py"
IMPORT_WORKER = ROOT / "operations" / "stage2_import_worker.py"
CASES = (
    "validation_cgmes3_powerflow_powerflow_a9b0a0bd",
    "validation_cgmes3_fullgrid_fullgrid_merged_6fb9a0f1",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], timeout: int, log: Path) -> tuple[dict[str, object], float, int | str]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONHASHSEED": "0"},
        )
        log.write_text(completed.stdout, encoding="utf-8")
        return {}, time.perf_counter() - started, completed.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        log.write_text(output, encoding="utf-8")
        return {"status": "timeout", "error_type": "TimeoutExpired"}, time.perf_counter() - started, "timeout"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    for name in ("exports", "assets", "workers", "console"):
        (output / name).mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        registry = {row["case_id"]: row for row in csv.DictReader(stream)}
    version = importlib.metadata.version("pypowsybl")
    environment = {
        "environment_id": args.environment_id,
        "system": platform.system(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "pypowsybl_version": version,
        "container": Path("/.dockerenv").is_file(),
    }
    pre_probe_lock = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "created_before_attempts": True,
        "environment": environment,
        "frozen_cases": {case_id: registry[case_id]["package_sha256"] for case_id in CASES},
        "export_worker_sha256": _sha256(EXPORT_WORKER),
        "import_worker_sha256": _sha256(IMPORT_WORKER),
        "probe_script_sha256": _sha256(Path(__file__).resolve()),
    }
    (output / "tool_version_probe_lock.json").write_text(
        json.dumps(pre_probe_lock, indent=2) + "\n", encoding="utf-8"
    )
    rows: list[dict[str, object]] = []
    for case_id in CASES:
        model = registry[case_id]
        source = ROOT / model["package_relative_path"]
        if _sha256(source) != model["package_sha256"]:
            raise RuntimeError(f"Input hash mismatch: {case_id}")
        export = output / "exports" / f"{case_id}.zip"
        export_result = output / "workers" / f"{case_id}__export.json"
        export_log = output / "console" / f"{case_id}__export.txt"
        fallback, elapsed, exit_code = _run(
            [
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
            ],
            args.timeout_seconds,
            export_log,
        )
        payload = json.loads(export_result.read_text(encoding="utf-8")) if export_result.is_file() else fallback
        rows.append(
            {
                **environment,
                "case_id": case_id,
                "family": model["family"],
                "package_sha256": model["package_sha256"],
                "stage": "export",
                "status": payload.get("status", "worker_crash"),
                "export_sha256": payload.get("export_sha256", ""),
                "export_size_bytes": payload.get("export_size_bytes", 0),
                "asset_count": 0,
                "elapsed_seconds": elapsed,
                "worker_exit_code": exit_code,
                "error_type": payload.get("error_type", "MissingWorkerResult"),
                "error_message": payload.get("error_message", ""),
            }
        )
        if rows[-1]["status"] != "success":
            rows.append(
                {
                    **environment,
                    "case_id": case_id,
                    "family": model["family"],
                    "package_sha256": model["package_sha256"],
                    "stage": "self_reimport",
                    "status": "not_attempted_export_failed",
                    "export_sha256": "",
                    "export_size_bytes": 0,
                    "asset_count": 0,
                    "elapsed_seconds": 0.0,
                    "worker_exit_code": "",
                    "error_type": "UpstreamExportFailed",
                    "error_message": rows[-1]["error_message"],
                }
            )
            continue
        import_result = output / "workers" / f"{case_id}__reimport.json"
        import_log = output / "console" / f"{case_id}__reimport.txt"
        asset = output / "assets" / f"{case_id}.csv"
        fallback, elapsed, exit_code = _run(
            [
                sys.executable,
                str(IMPORT_WORKER),
                "--tool",
                "pypowsybl",
                "--case-id",
                f"{case_id}__tool_version_probe",
                "--source",
                str(export),
                "--cgmes-version",
                "3.0.0",
                "--asset-output",
                str(asset),
                "--result-output",
                str(import_result),
            ],
            args.timeout_seconds,
            import_log,
        )
        payload = json.loads(import_result.read_text(encoding="utf-8")) if import_result.is_file() else fallback
        rows.append(
            {
                **environment,
                "case_id": case_id,
                "family": model["family"],
                "package_sha256": model["package_sha256"],
                "stage": "self_reimport",
                "status": payload.get("status", "worker_crash"),
                "export_sha256": rows[-1]["export_sha256"],
                "export_size_bytes": rows[-1]["export_size_bytes"],
                "asset_count": payload.get("asset_count", 0),
                "elapsed_seconds": elapsed,
                "worker_exit_code": exit_code,
                "error_type": payload.get("error_type", "MissingWorkerResult"),
                "error_message": payload.get("error_message", ""),
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "tool_version_probe_results.csv", index=False)
    summary = {
        "environment": environment,
        "expected_rows": 4,
        "recorded_rows": len(frame),
        "complete_denominator": len(frame) == 4,
        "status_counts": frame.status.value_counts().sort_index().to_dict(),
        "evidence_role": "same_tool_version_sensitivity_probe_not_final_holdout",
    }
    (output / "tool_version_probe_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
