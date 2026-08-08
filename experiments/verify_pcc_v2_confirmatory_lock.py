"""Verify frozen PCC v2 implementation and result hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "protocols" / "pcc_v2_confirmatory_lock.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    checks = {}
    expected = {
        "protocols/benchmark_protocol_v5_pcc_v2.yaml": lock["protocol_sha256"],
        "protocols/dc_scopf_protocol_v1.yaml": lock["dc_scopf_protocol_sha256"],
        **lock["implementation_sha256"],
        **lock["result_sha256"],
    }
    for relative, expected_hash in expected.items():
        path = ROOT / relative
        actual_hash = sha256(path) if path.is_file() else None
        checks[relative] = {
            "exists": path.is_file(),
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "match": actual_hash == expected_hash,
        }
    report = {
        "lock_version": lock["lock_version"],
        "checked_files": len(checks),
        "all_match": all(item["match"] for item in checks.values()),
        "checks": checks,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["all_match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
