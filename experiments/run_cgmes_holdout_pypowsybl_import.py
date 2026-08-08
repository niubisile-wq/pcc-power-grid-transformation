from __future__ import annotations

import hashlib
import importlib.metadata
import json
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cgmes" / "corpus" / "holdout" / "powsybl_core_holdout_bundle.zip"
OUTPUT = ROOT / "outputs" / "cgmes_untouched_holdout" / "pypowsybl_import.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    result: dict[str, object] = {
        "protocol": "cgmes_untouched_holdout_powsybl_core_v1",
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": sha256_file(SOURCE),
        "tool": "pypowsybl",
    }
    try:
        import pypowsybl as pp

        result["tool_version"] = importlib.metadata.version("pypowsybl")
        network = pp.network.load(str(SOURCE))
        counts = {
            "buses": len(network.get_buses()),
            "lines": len(network.get_lines()),
            "loads": len(network.get_loads()),
            "generators": len(network.get_generators()),
            "two_winding_transformers": len(network.get_2_windings_transformers()),
            "switches": len(network.get_switches()),
        }
        result.update(
            status="success",
            network_id=network.id,
            element_counts=counts,
            nonempty_element_total=sum(counts.values()),
        )
    except Exception as error:  # terminal failures are evidence and must be retained
        result.update(
            status="error",
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
