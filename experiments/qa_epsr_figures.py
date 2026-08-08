"""Automated export and source-integrity QA for EPSR figures (Python only)."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
FIGDIR = ROOT / "manuscript" / "figures"
QADIR = FIGDIR / "qa"
STEMS = [
    "fig1_pcc_workflow",
    "fig2_semantic_baseline_ladder",
    "fig3_operational_consequences",
    "fig4_dc_scopf_heterogeneity",
    "fig5_validation_portability_scaling",
    "fig6_external_tool_blind_roundtrip",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(name: str) -> list[dict]:
    with (FIGDIR / "source_data" / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    QADIR.mkdir(parents=True, exist_ok=True)
    source_manifest = json.loads((FIGDIR / "figure_source_manifest.json").read_text(encoding="utf-8"))
    expected_hash = {item["path"]: item["sha256"] for item in source_manifest["figure_outputs"]}
    checks = []
    all_pass = True

    for stem in STEMS:
        figure_check = {"stem": stem, "formats": {}, "pass": True}
        for suffix in ("svg", "pdf", "png"):
            path = FIGDIR / f"{stem}.{suffix}"
            rel = path.relative_to(ROOT).as_posix()
            item = {
                "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else 0,
                "sha256_matches_manifest": path.is_file() and sha256(path) == expected_hash.get(rel),
            }
            item["pass"] = item["exists"] and item["bytes"] > 10_000 and item["sha256_matches_manifest"]
            figure_check["formats"][suffix] = item
            figure_check["pass"] &= item["pass"]

        png = FIGDIR / f"{stem}.png"
        with Image.open(png) as image:
            width, height = image.size
            figure_check["png_dimensions"] = [width, height]
            figure_check["png_minimum_resolution_pass"] = width >= 3000 and height >= 1800
            gray = ImageOps.grayscale(image.convert("RGB"))
            gray.save(QADIR / f"{stem}_grayscale.png", dpi=(300, 300))
            extrema = gray.getextrema()
            figure_check["grayscale_extrema"] = list(extrema)
            figure_check["grayscale_contrast_pass"] = extrema[1] - extrema[0] >= 180
        figure_check["pass"] &= figure_check["png_minimum_resolution_pass"] and figure_check["grayscale_contrast_pass"]

        svg = FIGDIR / f"{stem}.svg"
        tree = ET.parse(svg)
        text_nodes = [node for node in tree.iter() if node.tag.endswith("text")]
        svg_text = svg.read_text(encoding="utf-8")
        figure_check["svg_text_nodes"] = len(text_nodes)
        figure_check["svg_editable_text_pass"] = len(text_nodes) >= 10 and "�" not in svg_text
        figure_check["pass"] &= figure_check["svg_editable_text_pass"]

        pdf = FIGDIR / f"{stem}.pdf"
        proc = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, check=False)
        font_lines = [line for line in proc.stdout.splitlines()[2:] if line.strip()]
        figure_check["pdf_font_records"] = font_lines
        figure_check["pdf_fonts_embedded_pass"] = proc.returncode == 0 and bool(font_lines) and all(" yes " in f" {line} " for line in font_lines)
        figure_check["pass"] &= figure_check["pdf_fonts_embedded_pass"]
        checks.append(figure_check)
        all_pass &= figure_check["pass"]

    semantic = csv_rows("fig2_aggregate_acceptance.csv")
    full_pcc = next(row for row in semantic if row["baseline"] == "B5_full_PCC_v2")
    state_grid = csv_rows("fig4_false_secure_state_grid.csv")
    state_sum = sum(int(row[f"offset{i}"]) for row in state_grid for i in range(10))
    elements = csv_rows("fig5_holdout_import_counts.csv")
    element_sum = sum(int(row["count"]) for row in elements)
    source_assertions = {
        "full_pcc_harmful_rate_is_zero": float(full_pcc["harmful_rate"]) == 0.0,
        "full_pcc_lawful_rate_is_one": float(full_pcc["lawful_rate"]) == 1.0,
        "dc_state_grid_sums_to_369": state_sum == 369,
        "holdout_import_counts_sum_to_59": element_sum == 59,
        "source_table_count_is_20": len(list((FIGDIR / "source_data").glob("*.csv"))) == 20,
    }
    all_pass &= all(source_assertions.values())
    result = {
        "qa_version": "epsr-figure-qa-v1",
        "backend": "Python",
        "status": "pass" if all_pass else "fail",
        "figure_checks": checks,
        "source_assertions": source_assertions,
        "grayscale_previews": [f"qa/{stem}_grayscale.png" for stem in STEMS],
        "visual_review_required": True,
    }
    target = QADIR / "figure_qa.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
