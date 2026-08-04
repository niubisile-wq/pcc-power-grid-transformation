from __future__ import annotations

import csv
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import frame, sha256  # noqa: E402
from adapters.pandapower_adapter import load_and_extract as load_pandapower  # noqa: E402
from adapters.pypowsybl_adapter import load_and_extract as load_pypowsybl  # noqa: E402
from adapters.veragrid_adapter import load_and_extract as load_veragrid  # noqa: E402


CASES = {
    "cgmes24_minigrid_t1": ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch" / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip",
    "cgmes24_minigrid_t2": ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch" / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip",
}

TOOLS = {
    "pandapower": load_pandapower,
    "pypowsybl": load_pypowsybl,
    "veragrid": load_veragrid,
}

RESULTS = ROOT / "results"
LOGS = ROOT / "logs"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    rows: list[dict[str, object]] = []
    for case_id, path in CASES.items():
        if not path.is_file():
            raise SystemExit(f"Missing preregistered model: {path}")
        for tool, loader in TOOLS.items():
            started = time.perf_counter()
            status = "success"
            error_type = ""
            error_message = ""
            metadata: dict[str, object] = {}
            logs: list[str] = []
            asset_count = 0
            try:
                records, metadata, logs = loader(path, case_id)
                assets = frame(records)
                asset_count = len(assets)
                assets.to_csv(RESULTS / f"common_assets__{case_id}__{tool}.csv", index=False)
            except Exception as exc:  # retain every tool/case failure
                status = "error"
                error_type = type(exc).__name__
                error_message = str(exc)
                logs = [traceback.format_exc()]
            elapsed = time.perf_counter() - started
            log_path = LOGS / f"import__{case_id}__{tool}.json"
            log_payload = {
                "case_id": case_id,
                "tool": tool,
                "status": status,
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": elapsed,
                "source_path": path.as_posix(),
                "source_sha256": sha256(path),
                "metadata": metadata,
                "messages": logs,
                "error_type": error_type,
                "error_message": error_message,
            }
            log_path.write_text(json.dumps(log_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            rows.append(
                {
                    "case_id": case_id,
                    "tool": tool,
                    "status": status,
                    "source_sha256": sha256(path),
                    "asset_count": asset_count,
                    "elapsed_seconds": elapsed,
                    "tool_log_count": len(logs),
                    "error_type": error_type,
                    "error_message": error_message,
                    "log_path": log_path.relative_to(ROOT).as_posix(),
                }
            )
            print(case_id, tool, status, asset_count, f"{elapsed:.3f}s")
    output = RESULTS / "tool_import_smoke_results.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "attempts": len(rows),
        "successes": sum(row["status"] == "success" for row in rows),
        "failures": sum(row["status"] != "success" for row in rows),
        "two_models_two_tools_gate": all(
            sum(row["case_id"] == case_id and row["status"] == "success" for row in rows) >= 2
            for case_id in CASES
        ),
    }
    (RESULTS / "tool_import_smoke_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

