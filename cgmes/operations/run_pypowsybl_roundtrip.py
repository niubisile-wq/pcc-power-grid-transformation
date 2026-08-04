from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pypowsybl as pp


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import frame, sha256  # noqa: E402
from adapters.pandapower_adapter import load_and_extract as load_pandapower  # noqa: E402
from adapters.pypowsybl_adapter import load_and_extract as load_pypowsybl  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
CASES = {
    "cgmes24_minigrid_t1": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip",
    "cgmes24_minigrid_t2": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip",
}
EXPORTS = ROOT / "results" / "roundtrip_exports"
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"
EXPORT_PARAMETERS = {
    "iidm.export.cgmes.cim-version": "16",
    "iidm.export.cgmes.profiles": "EQ,TP,SSH",
    "iidm.export.cgmes.naming-strategy": "identity",
}


def main() -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    rows: list[dict[str, object]] = []
    for case_id, source in CASES.items():
        export = EXPORTS / f"{case_id}__pypowsybl_roundtrip.zip"
        capture = io.StringIO()
        started = time.perf_counter()
        status = "success"
        error_type = ""
        error_message = ""
        try:
            with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                network = pp.network.load(str(source))
                parameters = {
                    **EXPORT_PARAMETERS,
                    "iidm.export.cgmes.base-name": f"{case_id}_pypowsybl",
                }
                network.save(str(export), format="CGMES", parameters=parameters)
            if not export.is_file() or export.stat().st_size == 0:
                raise RuntimeError("pypowsybl export did not create a non-empty archive")
        except Exception as exc:
            status = "error"
            error_type = type(exc).__name__
            error_message = str(exc)
            capture.write("\n" + traceback.format_exc())
        export_row: dict[str, object] = {
            "case_id": case_id,
            "route": "official_cgmes->pypowsybl->cgmes",
            "stage": "export",
            "target_tool": "",
            "status": status,
            "source_sha256": sha256(source),
            "export_path": export.relative_to(ROOT).as_posix() if export.is_file() else "",
            "export_sha256": sha256(export) if export.is_file() else "",
            "export_size_bytes": export.stat().st_size if export.is_file() else 0,
            "asset_count": 0,
            "elapsed_seconds": time.perf_counter() - started,
            "error_type": error_type,
            "error_message": error_message,
        }
        export_log = LOGS / f"pypowsybl_roundtrip_export__{case_id}.json"
        export_log.write_text(
            json.dumps(
                {
                    **export_row,
                    "started_utc": datetime.now(timezone.utc).isoformat(),
                    "export_parameters": EXPORT_PARAMETERS,
                    "messages": [line for line in capture.getvalue().splitlines() if line.strip()],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        export_row["log_path"] = export_log.relative_to(ROOT).as_posix()
        rows.append(export_row)
        print(case_id, "export", status)
        if status != "success":
            continue

        for target_tool, loader in {
            "pandapower": load_pandapower,
            "pypowsybl": load_pypowsybl,
        }.items():
            started = time.perf_counter()
            status = "success"
            error_type = ""
            error_message = ""
            metadata: dict[str, object] = {}
            messages: list[str] = []
            asset_count = 0
            try:
                records, metadata, messages = loader(export, f"{case_id}__pypowsybl_roundtrip")
                assets = frame(records)
                asset_count = len(assets)
                assets.to_csv(
                    RESULTS / f"common_assets__{case_id}__pypowsybl_roundtrip_to_{target_tool}.csv",
                    index=False,
                )
            except Exception as exc:
                status = "error"
                error_type = type(exc).__name__
                error_message = str(exc)
                messages.append(traceback.format_exc())
            row: dict[str, object] = {
                "case_id": case_id,
                "route": f"official_cgmes->pypowsybl->cgmes->{target_tool}",
                "stage": "reimport",
                "target_tool": target_tool,
                "status": status,
                "source_sha256": sha256(source),
                "export_path": export.relative_to(ROOT).as_posix(),
                "export_sha256": sha256(export),
                "export_size_bytes": export.stat().st_size,
                "asset_count": asset_count,
                "elapsed_seconds": time.perf_counter() - started,
                "error_type": error_type,
                "error_message": error_message,
            }
            log_path = LOGS / f"pypowsybl_roundtrip_reimport__{case_id}__{target_tool}.json"
            log_path.write_text(
                json.dumps({**row, "metadata": metadata, "messages": messages}, indent=2, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            row["log_path"] = log_path.relative_to(ROOT).as_posix()
            rows.append(row)
            print(case_id, "reimport", target_tool, status, asset_count)

    output = RESULTS / "pypowsybl_roundtrip_results.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "attempts": len(rows),
        "successes": sum(row["status"] == "success" for row in rows),
        "failures": sum(row["status"] != "success" for row in rows),
        "export_successes": sum(row["stage"] == "export" and row["status"] == "success" for row in rows),
        "reimport_successes": sum(row["stage"] == "reimport" and row["status"] == "success" for row in rows),
        "all_two_models_two_reimports_succeeded": all(
            any(
                row["case_id"] == case_id
                and row["target_tool"] == tool
                and row["status"] == "success"
                for row in rows
            )
            for case_id in CASES
            for tool in ("pandapower", "pypowsybl")
        ),
    }
    (RESULTS / "pypowsybl_roundtrip_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
