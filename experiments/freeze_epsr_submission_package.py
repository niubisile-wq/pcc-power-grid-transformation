"""Run the EPSR final package freeze sequence in dependency order."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "epsr_freeze_sequence"

STEPS = [
    {
        "name": "validate_author_metadata",
        "command": [sys.executable, "experiments/validate_epsr_author_metadata.py"],
        "required": True,
    },
    {
        "name": "apply_author_metadata",
        "command": [sys.executable, "experiments/apply_epsr_author_metadata.py"],
        "required": True,
    },
    {
        "name": "build_submission_manifest",
        "command": [sys.executable, "experiments/build_epsr_submission_manifest.py"],
        "required": True,
    },
    {
        "name": "build_archive_candidate",
        "command": [sys.executable, "experiments/build_epsr_final_archive_candidate.py"],
        "required": True,
    },
    {
        "name": "validate_final_readiness",
        "command": [sys.executable, "experiments/validate_epsr_final_readiness.py"],
        "required": True,
    },
]


def run_step(step: dict) -> dict:
    completed = subprocess.run(
        step["command"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return {
        "name": step["name"],
        "command": step["command"],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "pass" if completed.returncode == 0 else "fail",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    final_status = "pass"
    for step in STEPS:
        result = run_step(step)
        results.append(result)
        if result["returncode"] != 0:
            if step["name"] == "validate_author_metadata":
                request_result = run_step({
                    "name": "build_author_metadata_request",
                    "command": [sys.executable, "experiments/build_epsr_author_metadata_request.py"],
                })
                results.append(request_result)
                coverage_result = run_step({
                    "name": "validate_author_request_coverage",
                    "command": [sys.executable, "experiments/validate_epsr_author_request_coverage.py"],
                })
                results.append(coverage_result)
            final_status = "fail"
            break

    summary = {
        "sequence": "epsr-final-freeze-v1",
        "status": final_status,
        "steps": results,
        "policy": (
            "The sequence stops at the first fail-closed gate. A failed "
            "author metadata step means external author/release fields remain "
            "unconfirmed, not that the scientific evidence failed."
        ),
    }
    target = OUT / "freeze_sequence_summary.json"
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if final_status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
