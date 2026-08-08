from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "protocols" / "semantic_confirmatory_lock_v2.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    checks = {}
    for name, expected in lock["sha256"].items():
        path = ROOT / name
        actual = sha256(path) if path.is_file() else None
        checks[name] = {"exists": path.is_file(), "expected": expected, "actual": actual, "match": actual == expected}
    result = {
        "lock_version": lock["lock_version"],
        "checked_files": len(checks),
        "all_match": all(item["match"] for item in checks.values()),
        "checks": checks,
    }
    print(json.dumps(result, indent=2))
    if not result["all_match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
