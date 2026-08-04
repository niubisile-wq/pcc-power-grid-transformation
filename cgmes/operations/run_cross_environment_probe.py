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
WORKER = ROOT / "operations" / "stage2_import_worker.py"
FROZEN_CASE_IDS = (
    "validation_cgmes3_powerflow_powerflow_a9b0a0bd",
    "validation_cgmes3_fullgrid_fullgrid_merged_6fb9a0f1",
)
TOOLS = ("pandapower", "pypowsybl", "veragrid")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    workers = output_dir / "workers"
    assets = output_dir / "assets"
    console = output_dir / "console"
    for path in (workers, assets, console):
        path.mkdir(parents=True, exist_ok=True)

    with REGISTRY.open(encoding="utf-8", newline="") as stream:
        registry = {row["case_id"]: row for row in csv.DictReader(stream)}
    missing = set(FROZEN_CASE_IDS) - set(registry)
    if missing:
        raise RuntimeError(f"Frozen cross-environment cases missing: {sorted(missing)}")

    environment = {
        "environment_id": args.environment_id,
        "os": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "container": Path("/.dockerenv").is_file(),
        "packages": {
            "pandapower": _version("pandapower"),
            "pypowsybl": _version("pypowsybl"),
            "VeraGrid": _version("VeraGrid"),
            "VeraGridEngine": _version("VeraGridEngine"),
            "pandas": _version("pandas"),
            "rdflib": _version("rdflib"),
        },
    }
    pre_probe_lock = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "created_before_attempts": True,
        "environment": environment,
        "frozen_cases": {
            case_id: registry[case_id]["package_sha256"] for case_id in FROZEN_CASE_IDS
        },
        "tools": list(TOOLS),
        "import_worker_sha256": _sha256(WORKER),
        "probe_script_sha256": _sha256(Path(__file__).resolve()),
    }
    (output_dir / "cross_environment_probe_lock.json").write_text(
        json.dumps(pre_probe_lock, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    rows: list[dict[str, object]] = []
    for case_id in FROZEN_CASE_IDS:
        model = registry[case_id]
        source = ROOT / model["package_relative_path"]
        if _sha256(source) != model["package_sha256"]:
            raise RuntimeError(f"Input hash mismatch: {case_id}")
        for tool in TOOLS:
            result_path = workers / f"{case_id}__{tool}.json"
            asset_path = assets / f"{case_id}__{tool}.csv"
            console_path = console / f"{case_id}__{tool}.txt"
            command = [
                sys.executable,
                str(WORKER),
                "--tool",
                tool,
                "--case-id",
                case_id,
                "--source",
                str(source),
                "--cgmes-version",
                "3.0.0",
                "--asset-output",
                str(asset_path),
                "--result-output",
                str(result_path),
            ]
            started = time.perf_counter()
            timed_out = False
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=args.timeout_seconds,
                    check=False,
                    env={**os.environ, "PYTHONHASHSEED": "0"},
                )
                output = completed.stdout
                exit_code: int | str = completed.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                exit_code = "timeout"
            elapsed = time.perf_counter() - started
            console_path.write_text(output, encoding="utf-8")
            payload = (
                json.loads(result_path.read_text(encoding="utf-8"))
                if result_path.is_file()
                else {}
            )
            rows.append(
                {
                    **environment,
                    "packages": json.dumps(environment["packages"], sort_keys=True),
                    "case_id": case_id,
                    "family": model["family"],
                    "package_sha256": model["package_sha256"],
                    "tool": tool,
                    "status": "timeout" if timed_out else payload.get("status", "worker_crash"),
                    "asset_count": payload.get("asset_count", 0),
                    "elapsed_seconds": elapsed,
                    "timed_out": timed_out,
                    "worker_exit_code": exit_code,
                    "error_type": "TimeoutExpired" if timed_out else payload.get("error_type", "MissingWorkerResult"),
                    "error_message": (
                        f"Exceeded {args.timeout_seconds} seconds"
                        if timed_out
                        else payload.get("error_message", "")
                    ),
                    "result_path": result_path.relative_to(ROOT).as_posix()
                    if result_path.is_file()
                    else "",
                    "console_path": console_path.relative_to(ROOT).as_posix(),
                }
            )
            print(f"{case_id} {tool}: {rows[-1]['status']}", flush=True)

    frame = pd.DataFrame(rows)
    frame.to_csv(output_dir / "cross_environment_probe_results.csv", index=False)
    summary = {
        "environment": environment,
        "frozen_cases": list(FROZEN_CASE_IDS),
        "tools": list(TOOLS),
        "expected_attempts": len(FROZEN_CASE_IDS) * len(TOOLS),
        "recorded_attempts": len(frame),
        "complete_denominator": len(frame) == len(FROZEN_CASE_IDS) * len(TOOLS),
        "status_counts": frame.status.value_counts().sort_index().to_dict(),
        "evidence_role": "cross_environment_reproducibility_probe_not_final_holdout",
    }
    (output_dir / "cross_environment_probe_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
