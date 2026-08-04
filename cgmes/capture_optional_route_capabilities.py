from __future__ import annotations

import importlib.util
import json
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    commands = {
        name: shutil.which(name) for name in ("matlab", "octave", "julia")
    }
    modules = {
        name: importlib.util.find_spec(name) is not None
        for name in ("matpower", "powermodels", "julia")
    }
    matpower_available = bool(commands["matlab"] or commands["octave"]) and modules[
        "matpower"
    ]
    powermodels_available = bool(commands["julia"]) and modules["julia"]
    payload = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "commands": commands,
        "python_modules": modules,
        "optional_routes": {
            "CGMES_to_MATPOWER_to_CGMES": {
                "supported_in_environment": matpower_available,
                "execution_status": (
                    "not_attempted_optional_route_unavailable"
                    if not matpower_available
                    else "available_not_yet_executed"
                ),
            },
            "CGMES_to_PowerModels_to_CGMES": {
                "supported_in_environment": powermodels_available,
                "execution_status": (
                    "not_attempted_optional_route_unavailable"
                    if not powermodels_available
                    else "available_not_yet_executed"
                ),
            },
        },
        "claim_limit": (
            "The plan marks these routes optional when supported. Their absence is a "
            "capability exclusion, not a failed conversion attempt."
        ),
    }
    output = ROOT / "environment" / "optional_route_capabilities.json"
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
