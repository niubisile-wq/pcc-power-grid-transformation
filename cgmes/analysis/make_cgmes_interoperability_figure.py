from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["font.size"] = 7
plt.rcParams["axes.linewidth"] = 0.7
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False
plt.rcParams["legend.frameon"] = False

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
SOURCE_DATA = ROOT / "figures" / "source_data"
RENDERED = ROOT.parent / "figures"
STEM = "Fig3_cgmes_interoperability_audit"

COLORS = {
    "success": "#0F4D92",
    "error": "#E9A6A1",
    "not_attempted": "#CFCECE",
    "exact": "#0F4D92",
    "renamed": "#8AB6D6",
    "dropped": "#E9A6A1",
    "created": "#E8C07A",
    "ambiguous": "#767676",
    "shacl_conforming": "#8BCF8B",
    "shacl_nonconforming": "#B64342",
    "strict_rdf_parse_error": "#4D4D4D",
    "validation_execution_error": "#E8C07A",
    "timeout": "#B8B8B8",
}
HATCHES = {
    "success": "",
    "error": "///",
    "not_attempted": "..",
    "exact": "",
    "renamed": "//",
    "dropped": "xx",
    "created": "..",
    "ambiguous": "\\\\",
    "shacl_conforming": "",
    "shacl_nonconforming": "///",
    "strict_rdf_parse_error": "xx",
    "validation_execution_error": "..",
    "timeout": "\\\\",
}


def _json(name: str) -> dict[str, object]:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def _panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.09,
        1.04,
        label,
        transform=ax.transAxes,
        fontweight="bold",
        fontsize=8,
        va="bottom",
    )


def _classify_converted(row: pd.Series) -> str:
    if row.status == "timeout":
        return "timeout"
    if row.status == "success":
        return (
            "shacl_conforming"
            if str(row.shacl_conforms).lower() == "true"
            else "shacl_nonconforming"
        )
    message = str(row.error_message)
    if "RDF/XML parse failures" in message:
        return "strict_rdf_parse_error"
    return "validation_execution_error"


def _stacked_percent(
    ax: plt.Axes,
    labels: list[str],
    counts: pd.DataFrame,
    categories: list[str],
    source_rows: list[dict[str, object]],
    panel: str,
) -> None:
    totals = counts[categories].sum(axis=1).to_numpy(dtype=float)
    left = np.zeros(len(labels))
    for category in categories:
        values = counts[category].to_numpy(dtype=float)
        fraction = np.divide(values, totals, out=np.zeros_like(values), where=totals > 0)
        ax.barh(
            labels,
            fraction,
            left=left,
            color=COLORS[category],
            edgecolor="white",
            linewidth=0.5,
            hatch=HATCHES[category],
            label=category.replace("_", " "),
        )
        for label, count, total in zip(labels, values.astype(int), totals.astype(int)):
            source_rows.append(
                {
                    "panel": panel,
                    "group": label,
                    "category": category,
                    "count": count,
                    "denominator": total,
                    "fraction": count / total if total else 0.0,
                }
            )
        left += fraction
    ax.set_xlim(0, 1)
    ax.set_xlabel("fraction of retained rows")
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")


def main() -> None:
    SOURCE_DATA.mkdir(parents=True, exist_ok=True)
    RENDERED.mkdir(parents=True, exist_ok=True)
    source_rows: list[dict[str, object]] = []

    imports = []
    for label, filename in (
        ("CGMES 2.4.15\ndevelopment", "stage2_import_matrix_results.csv"),
        ("CGMES 3.0\ninternal validation", "stage5_import_matrix_results.csv"),
    ):
        frame = pd.read_csv(RESULTS / filename, keep_default_na=False)
        for tool in ("pandapower", "pypowsybl", "veragrid"):
            part = frame[frame.tool == tool]
            imports.append(
                {
                    "dataset": label,
                    "tool": tool,
                    "success": int(part.status.eq("success").sum()),
                    "total": len(part),
                }
            )
    import_frame = pd.DataFrame(imports)

    roundtrip_specs = (
        ("2.4.15→2.4.15", "stage2_roundtrip_matrix_results.csv"),
        ("3.0→3.0", "stage5_roundtrip_matrix_results.csv"),
        ("2.4.15 → 3.0", "version_migration_matrix_results.csv"),
    )
    route_rows = []
    for label, filename in roundtrip_specs:
        frame = pd.read_csv(RESULTS / filename, keep_default_na=False)
        route_rows.append(
            {
                "group": label,
                "success": int(frame.status.eq("success").sum()),
                "error": int(frame.status.eq("error").sum()),
                "not_attempted": int(
                    frame.status.str.startswith("not_attempted").sum()
                ),
            }
        )
    route_frame = pd.DataFrame(route_rows).set_index("group")

    mapping_specs = (
        ("2.4.15→2.4.15", "stage2_full_roundtrip_mapping_summary.json"),
        ("3.0→3.0", "stage5_full_roundtrip_mapping_summary.json"),
        ("2.4.15 → 3.0", "version_migration_mapping_summary.json"),
    )
    mapping_rows = []
    for label, filename in mapping_specs:
        counts = _json(filename)["mapping_status_counts_including_zeros"]
        mapping_rows.append(
            {
                "group": label,
                "exact": int(counts["exact"]),
                "renamed": int(counts["renamed"]),
                "dropped": int(counts["dropped"]),
                "created": int(counts["created"]),
                "ambiguous": int(counts["ambiguous"]),
            }
        )
    mapping_frame = pd.DataFrame(mapping_rows).set_index("group")

    source_shacl = pd.read_csv(
        RESULTS / "cgmes_shacl_validation_results.csv", keep_default_na=False
    )
    source_shacl["outcome"] = np.where(
        source_shacl.status.eq("timeout"),
        "timeout",
        np.where(
            source_shacl.status.eq("success")
            & source_shacl.shacl_conforms.astype(str).str.lower().eq("true"),
            "shacl_conforming",
            np.where(
                source_shacl.status.eq("success"),
                "shacl_nonconforming",
                "validation_execution_error",
            ),
        ),
    )
    converted = pd.read_csv(
        RESULTS / "converted_cgmes3_shacl_validation_results.csv",
        keep_default_na=False,
    )
    if len(converted) != 32 or converted.artifact_id.nunique() != 32:
        raise RuntimeError("Converted SHACL denominator must be complete (32 artifacts)")
    converted["outcome"] = converted.apply(_classify_converted, axis=1)
    shacl_categories = [
        "shacl_conforming",
        "shacl_nonconforming",
        "strict_rdf_parse_error",
        "validation_execution_error",
        "timeout",
    ]
    shacl_frame = pd.DataFrame(
        [
            {
                "group": "official CGMES 3.0\nsource (n=20)",
                **{
                    category: int(source_shacl.outcome.eq(category).sum())
                    for category in shacl_categories
                },
            },
            {
                "group": "successful CGMES 3.0\nexports (n=32)",
                **{
                    category: int(converted.outcome.eq(category).sum())
                    for category in shacl_categories
                },
            },
        ]
    ).set_index("group")

    fig = plt.figure(figsize=(7.2, 7.0))
    grid = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.15, 1.0], hspace=0.62, wspace=0.50)
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, :])
    ax_d = fig.add_subplot(grid[2, :])

    dataset_labels = import_frame.dataset.drop_duplicates().tolist()
    tools = ["pandapower", "pypowsybl", "veragrid"]
    matrix = np.zeros((len(dataset_labels), len(tools)))
    for i, dataset in enumerate(dataset_labels):
        for j, tool in enumerate(tools):
            row = import_frame[(import_frame.dataset == dataset) & (import_frame.tool == tool)].iloc[0]
            matrix[i, j] = row.success / row.total
            source_rows.append(
                {
                    "panel": "a",
                    "group": dataset.replace("\n", " "),
                    "category": tool,
                    "count": int(row.success),
                    "denominator": int(row.total),
                    "fraction": float(matrix[i, j]),
                }
            )
    image = ax_a.imshow(matrix, vmin=0, vmax=1, cmap="Blues", aspect="auto")
    for i, dataset in enumerate(dataset_labels):
        for j, tool in enumerate(tools):
            row = import_frame[(import_frame.dataset == dataset) & (import_frame.tool == tool)].iloc[0]
            color = "white" if matrix[i, j] > 0.58 else "black"
            ax_a.text(j, i, f"{row.success}/{row.total}", ha="center", va="center", color=color, fontsize=7)
    ax_a.set_xticks(range(len(tools)), ["pandapower", "PyPowSyBl", "VeraGrid"], rotation=20, ha="right")
    ax_a.set_yticks(range(len(dataset_labels)), dataset_labels)
    ax_a.set_title("Direct import compatibility", loc="left", fontsize=8)
    ax_a.set_frame_on(False)
    colorbar = fig.colorbar(image, ax=ax_a, fraction=0.05, pad=0.03)
    colorbar.ax.set_title("fraction", fontsize=6, pad=3)
    _panel_label(ax_a, "a")

    _stacked_percent(
        ax_b,
        route_frame.index.tolist(),
        route_frame,
        ["success", "error", "not_attempted"],
        source_rows,
        "b",
    )
    ax_b.set_title("Route-stage outcomes", loc="left", fontsize=8)
    ax_b.legend(loc="lower center", bbox_to_anchor=(0.5, -0.55), ncol=3, fontsize=6)
    _panel_label(ax_b, "b")

    _stacked_percent(
        ax_c,
        mapping_frame.index.tolist(),
        mapping_frame,
        ["exact", "renamed", "dropped", "created", "ambiguous"],
        source_rows,
        "c",
    )
    full_mapping = _json("full_roundtrip_asset_mapping_summary.json")
    accepted = int(full_mapping["identity_only_accepted_rows"])
    total_mapping = int(full_mapping["rows"])
    review = total_mapping - accepted
    ax_c.text(
        1.0,
        1.10,
        f"identity-only accepted {accepted:,}/{total_mapping:,}; additional review {review:,} ({review / total_mapping:.1%})",
        transform=ax_c.transAxes,
        ha="right",
        va="bottom",
        fontsize=6.5,
    )
    ax_c.set_title("Automated identity-relation workload", loc="left", fontsize=8)
    ax_c.legend(loc="lower center", bbox_to_anchor=(0.5, -0.43), ncol=5, fontsize=6)
    _panel_label(ax_c, "c")

    _stacked_percent(
        ax_d,
        shacl_frame.index.tolist(),
        shacl_frame,
        shacl_categories,
        source_rows,
        "d",
    )
    ax_d.set_title("Official structural-validation gate", loc="left", fontsize=8)
    ax_d.legend(loc="lower center", bbox_to_anchor=(0.5, -0.48), ncol=3, fontsize=6)
    _panel_label(ax_d, "d")

    fig.subplots_adjust(left=0.16, right=0.98, top=0.96, bottom=0.08)
    base = RENDERED / STEM
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, bbox_inches="tight")
    fig.savefig(RENDERED / f"{STEM}_preview.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    pd.DataFrame(source_rows).to_csv(SOURCE_DATA / f"{STEM}_source_data.csv", index=False)
    print(
        json.dumps(
            {
                "stem": STEM,
                "source_rows": len(source_rows),
                "rendered_directory": RENDERED.as_posix(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
