from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import frame, sha256  # noqa: E402
from adapters.pandapower_adapter import load_and_extract as load_pandapower  # noqa: E402
from adapters.pypowsybl_adapter import load_and_extract as load_pypowsybl  # noqa: E402

from VeraGridEngine.IO.cim.cgmes.cgmes_enums import CgmesProfileType  # noqa: E402
from VeraGridEngine.IO.file_open import FileOpen, FileOpenOptions  # noqa: E402
from VeraGridEngine.IO.file_save import FileSave, FileSavingOptions  # noqa: E402
from VeraGridEngine.enumerations import CGMESVersions, FileType  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
CASES = {
    "cgmes24_minigrid_t1": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip",
    "cgmes24_minigrid_t2": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip",
}
BOUNDARY = BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_Boundary_v3.zip"
EXPORTS = ROOT / "results" / "roundtrip_exports"
LOGS = ROOT / "logs"
ATTEMPT_ID = "attempt3_single_archive_no_sv"


def main() -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    rows: list[dict[str, object]] = []
    for case_id, source in CASES.items():
        export = EXPORTS / f"{case_id}__veragrid_roundtrip.zip"
        started = time.perf_counter()
        status = "success"
        messages: list[str] = []
        error_type = ""
        error_message = ""
        try:
            open_options = FileOpenOptions(
                file_type=FileType.CGMES,
                cgmes_version=CGMESVersions.v2_4_15,
            )
            opener = FileOpen(str(source), options=open_options)
            circuit = opener.open()
            if circuit is None:
                raise RuntimeError("VeraGrid returned no circuit")
            save_options = FileSavingOptions(
                file_type=FileType.CGMES,
                cgmes_boundary_set=str(BOUNDARY),
                cgmes_version=CGMESVersions.v2_4_15,
                cgmes_profiles=[
                    CgmesProfileType.EQ,
                    CgmesProfileType.TP,
                    CgmesProfileType.SSH,
                ],
                cgmes_one_file_per_profile=False,
            )
            save_log = FileSave(circuit, str(export), options=save_options).save()
            messages = [str(entry) for entry in save_log.entries]
            if not export.is_file() or export.stat().st_size == 0:
                raise RuntimeError("VeraGrid export did not create a non-empty archive")
        except Exception as exc:
            status = "error"
            error_type = type(exc).__name__
            error_message = str(exc)
            messages.append(traceback.format_exc())
        export_hash = sha256(export) if export.is_file() else ""
        row: dict[str, object] = {
            "case_id": case_id,
            "route": "official_cgmes->veragrid->cgmes",
            "status": status,
            "source_sha256": sha256(source),
            "boundary_sha256": sha256(BOUNDARY),
            "export_path": export.relative_to(ROOT).as_posix() if export.is_file() else "",
            "export_sha256": export_hash,
            "export_size_bytes": export.stat().st_size if export.is_file() else 0,
            "elapsed_seconds": time.perf_counter() - started,
            "log_count": len(messages),
            "error_type": error_type,
            "error_message": error_message,
        }
        (LOGS / f"roundtrip_export__{case_id}__{ATTEMPT_ID}.json").write_text(
            json.dumps({**row, "messages": messages}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        rows.append(row)
        if status != "success":
            continue
        for target_tool, loader in {
            "pandapower": load_pandapower,
            "pypowsybl": load_pypowsybl,
        }.items():
            reimport_started = time.perf_counter()
            reimport_status = "success"
            reimport_error_type = ""
            reimport_error_message = ""
            asset_count = 0
            reimport_logs: list[str] = []
            try:
                records, metadata, reimport_logs = loader(export, case_id + "__veragrid_roundtrip")
                assets = frame(records)
                asset_count = len(assets)
                assets.to_csv(
                    ROOT / "results" / f"common_assets__{case_id}__veragrid_roundtrip_to_{target_tool}.csv",
                    index=False,
                )
            except Exception as exc:
                reimport_status = "error"
                reimport_error_type = type(exc).__name__
                reimport_error_message = str(exc)
                metadata = {}
                reimport_logs = [traceback.format_exc()]
            reimport_row = {
                "case_id": case_id,
                "route": f"official_cgmes->veragrid->cgmes->{target_tool}",
                "status": reimport_status,
                "source_sha256": sha256(source),
                "boundary_sha256": sha256(BOUNDARY),
                "export_path": export.relative_to(ROOT).as_posix(),
                "export_sha256": export_hash,
                "export_size_bytes": export.stat().st_size,
                "elapsed_seconds": time.perf_counter() - reimport_started,
                "log_count": len(reimport_logs),
                "asset_count": asset_count,
                "error_type": reimport_error_type,
                "error_message": reimport_error_message,
            }
            (LOGS / f"roundtrip_reimport__{case_id}__{target_tool}__{ATTEMPT_ID}.json").write_text(
                json.dumps(
                    {**reimport_row, "metadata": metadata, "messages": reimport_logs},
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            rows.append(reimport_row)
    result = pd.DataFrame(rows)
    result.to_csv(ROOT / "results" / f"minimum_roundtrip_results__{ATTEMPT_ID}.csv", index=False)
    summary = {
        "attempts": len(result),
        "successes": int((result["status"] == "success").sum()),
        "failures": int((result["status"] != "success").sum()),
        "export_successes": int(
            ((result["route"] == "official_cgmes->veragrid->cgmes") & (result["status"] == "success")).sum()
        ),
        "reimport_successes": int(
            ((result["route"] != "official_cgmes->veragrid->cgmes") & (result["status"] == "success")).sum()
        ),
    }
    (ROOT / "results" / f"minimum_roundtrip_summary__{ATTEMPT_ID}.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(result.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
