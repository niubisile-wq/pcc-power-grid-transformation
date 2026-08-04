from __future__ import annotations

import json
import sys
import traceback
import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import frame, sha256  # noqa: E402
from adapters.pandapower_adapter import load_and_extract as load_pandapower  # noqa: E402
from adapters.pypowsybl_adapter import load_and_extract as load_pypowsybl  # noqa: E402


BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
BOUNDARY = BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_Boundary_v3.zip"
EXPORTS = ROOT / "results" / "roundtrip_exports"
CASES = ["cgmes24_minigrid_t1", "cgmes24_minigrid_t2"]


def combine_archives(model: Path, boundary: Path, output: Path) -> list[str]:
    entries: dict[str, bytes] = {}
    provenance: list[str] = []
    for role, path in (("model", model), ("boundary", boundary)):
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                data = archive.read(name)
                output_name = name
                if output_name in entries:
                    output_name = f"{role}__{Path(name).name}"
                entries[output_name] = data
                provenance.append(f"{role}:{path.name}:{name}->{output_name}")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, entries[name])
    return provenance


def main() -> None:
    rows: list[dict[str, object]] = []
    for case_id in CASES:
        model = EXPORTS / f"{case_id}__veragrid_roundtrip.zip"
        combined = EXPORTS / f"{case_id}__veragrid_roundtrip_with_boundary.zip"
        provenance = combine_archives(model, BOUNDARY, combined)
        for tool, loader in {"pandapower": load_pandapower, "pypowsybl": load_pypowsybl}.items():
            status = "success"
            error_type = ""
            error_message = ""
            asset_count = 0
            metadata: dict[str, object] = {}
            messages: list[str] = []
            try:
                records, metadata, messages = loader(combined, case_id + "__roundtrip_with_boundary")
                assets = frame(records)
                asset_count = len(assets)
                assets.to_csv(
                    ROOT / "results" / f"common_assets__{case_id}__veragrid_roundtrip_with_boundary_to_{tool}.csv",
                    index=False,
                )
            except Exception as exc:
                status = "error"
                error_type = type(exc).__name__
                error_message = str(exc)
                messages = [traceback.format_exc()]
            rows.append(
                {
                    "case_id": case_id,
                    "route": f"veragrid_export+official_boundary->{tool}",
                    "status": status,
                    "model_export_sha256": sha256(model),
                    "boundary_sha256": sha256(BOUNDARY),
                    "combined_sha256": sha256(combined),
                    "asset_count": asset_count,
                    "error_type": error_type,
                    "error_message": error_message,
                }
            )
            (ROOT / "logs" / f"boundary_reimport__{case_id}__{tool}.json").write_text(
                json.dumps(
                    {
                        **rows[-1],
                        "metadata": metadata,
                        "messages": messages,
                        "packaging_provenance": provenance,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
    result = pd.DataFrame(rows)
    result.to_csv(ROOT / "results" / "minimum_roundtrip_boundary_reimport_results.csv", index=False)
    summary = {
        "attempts": len(result),
        "successes": int((result["status"] == "success").sum()),
        "failures": int((result["status"] != "success").sum()),
        "packaging_is_semantic_edit": False,
    }
    (ROOT / "results" / "minimum_roundtrip_boundary_reimport_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(result.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

