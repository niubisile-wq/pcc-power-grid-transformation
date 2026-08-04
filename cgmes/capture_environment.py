from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = ROOT / "environment"


def main() -> None:
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    (ENV_DIR / "requirements-lock.txt").write_text(freeze, encoding="utf-8")
    important = ["pandapower", "VeraGrid", "pypowsybl", "pyshacl", "rdflib", "numpy", "pandas", "scipy"]
    payload = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in important},
    }
    (ENV_DIR / "environment.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

