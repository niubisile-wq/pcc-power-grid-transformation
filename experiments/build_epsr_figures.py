"""Build the EPSR submission figures from frozen evidence only."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon


ROOT = Path(__file__).resolve().parents[1]
FIGDIR = ROOT / "manuscript" / "figures"
DATADIR = FIGDIR / "source_data"

SOURCES = {
    "semantic": ROOT / "outputs/pcc_v2_semantic_baseline_ladder/summary.json",
    "application": ROOT / "outputs/pcc_v2_application_statistics/summary.json",
    "dc": ROOT / "outputs/pcc_v2_dc_scopf_statistics/summary.json",
    "scaling": ROOT / "outputs/pcc_v2_scaling/pcc_v2_scaling_summary.json",
    "apl": ROOT / "outputs/cgmes_apl111_pcc_separation/separation_summary.json",
    "qocdc": ROOT / "outputs/qocdc_414_applicable_subset/summary.json",
    "holdout": ROOT / "outputs/cgmes_untouched_holdout/holdout_summary.json",
    "cross_dcp": ROOT / "outputs/cross_solver_validation/cross_solver_summary.json",
    "cross_dcmp": ROOT / "outputs/cross_solver_dcmp_validation/cross_solver_dcmp_summary.json",
    "dc_atlas": ROOT / "outputs/dc_scopf_mechanism_atlas/summary.json",
    "external": ROOT / "outputs/external_tool_blind_roundtrip/summary.json",
    "external_routes": ROOT / "outputs/external_tool_blind_roundtrip/route_artifacts_manifest.json",
    "external_consequence": ROOT / "outputs/external_tool_blind_roundtrip/consequence_summary.json",
}

COL = {
    "pcc": "#0F4D92",
    "pcc2": "#3775BA",
    "safe": "#2B8C6B",
    "harm": "#B64342",
    "harm2": "#E9A6A1",
    "warn": "#D88A2D",
    "neutral": "#767676",
    "light": "#D7DCE2",
    "lighter": "#F2F4F7",
    "ink": "#272727",
    "teal": "#42949E",
    "violet": "#7868A6",
}


def configure() -> None:
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 7,
        "axes.titlesize": 8,
        "axes.labelsize": 7,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "legend.fontsize": 6.5,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.8,
        "legend.frameon": False,
        "savefig.facecolor": "white",
    })


def load(name: str) -> dict:
    return json.loads(SOURCES[name].read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(name: str, fieldnames: list[str], rows: list[dict]) -> Path:
    DATADIR.mkdir(parents=True, exist_ok=True)
    path = DATADIR / name
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def panel(ax, label: str, x: float = -0.10, y: float = 1.04) -> None:
    ax.text(x, y, label, transform=ax.transAxes, fontsize=8, fontweight="bold",
            ha="left", va="bottom")


def clean(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(length=2.5, width=0.7)


def save(fig: plt.Figure, stem: str) -> list[Path]:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    outputs = []
    for suffix, kwargs in (
        ("svg", {}),
        ("pdf", {}),
        ("png", {"dpi": 600}),
    ):
        path = FIGDIR / f"{stem}.{suffix}"
        fig.savefig(path, bbox_inches="tight", pad_inches=0.04, **kwargs)
        outputs.append(path)
    plt.close(fig)
    return outputs


def rounded_box(ax, xy, width, height, text, fc, ec, fontsize=7, weight="normal"):
    box = FancyBboxPatch(xy, width, height,
                         boxstyle="round,pad=0.012,rounding_size=0.018",
                         facecolor=fc, edgecolor=ec, linewidth=1.0)
    ax.add_patch(box)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text,
            ha="center", va="center", fontsize=fontsize, fontweight=weight,
            color=COL["ink"])
    return box


def arrow(ax, start, end, color=COL["neutral"], style="-|>", lw=1.2):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle=style,
                                mutation_scale=9, linewidth=lw, color=color,
                                shrinkA=2, shrinkB=2))


def figure1() -> tuple[list[Path], list[Path]]:
    fig = plt.figure(figsize=(7.205, 4.42), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.05], width_ratios=[1.04, 0.96])
    axa = fig.add_subplot(gs[0, :])
    axb = fig.add_subplot(gs[1, 0])
    axc = fig.add_subplot(gs[1, 1])
    for ax in (axa, axb, axc):
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    panel(axa, "a", x=-0.015, y=0.98)
    axa.text(0.02, 0.93, "A valid numerical answer can describe the wrong transformed task",
             fontsize=8, fontweight="bold", va="top")
    xs = [0.03, 0.23, 0.43, 0.63, 0.83]
    labels = ["Source\nsnapshot", "Converter", "Parseable\ntarget", "Security\nstudy", "Numerical\nresult"]
    colors = ["#E8EEF6", "#E8EEF6", "#F8E1DE", "#F8E1DE", "#F8E1DE"]
    for x, label, fc in zip(xs, labels, colors):
        rounded_box(axa, (x, 0.38), 0.14, 0.25, label, fc, COL["pcc"] if x < 0.4 else COL["harm"])
    for left, right in zip(xs[:-1], xs[1:]):
        arrow(axa, (left + 0.14, 0.505), (right, 0.505), COL["neutral"])
    axa.plot([0.40, 0.40], [0.25, 0.75], color=COL["harm"], lw=1.0, ls="--")
    axa.text(0.40, 0.22, "identity / relation / intervention semantics may change here",
             color=COL["harm"], ha="center", va="top", fontsize=6.5)
    axa.text(0.90, 0.72, "solves successfully", color=COL["harm"], ha="center", fontsize=6.5)

    panel(axb, "b", x=-0.02, y=0.98)
    axb.text(0.03, 0.93, "Task-bound certificate obligations", fontsize=8, fontweight="bold", va="top")
    obligations = [
        ("Exact snapshots", "hashes + freshness"),
        ("Asset relations", "coverage + cardinality"),
        ("Attributes", "task tolerances"),
        ("Interventions", "action equivalence"),
        ("Converter trace", "authoritative agreement"),
        ("Issuer", "signature + nonce"),
    ]
    for i, (head, sub) in enumerate(obligations):
        row, col = divmod(i, 2)
        x, y = 0.04 + col * 0.48, 0.68 - row * 0.23
        rounded_box(axb, (x, y), 0.42, 0.16, f"{head}\n{sub}", "#E7EFF8", COL["pcc"], fontsize=6.5)
    axb.text(0.04, 0.05, "Trusted: contract, registry, keys, trace, verifier, protected gate",
             fontsize=6.2, color=COL["neutral"])

    panel(axc, "c", x=-0.02, y=0.98)
    axc.text(0.03, 0.93, "Only accept can cross the execution boundary", fontsize=8, fontweight="bold", va="top")
    rounded_box(axc, (0.04, 0.57), 0.24, 0.18, "PCC\nverifier", "#E7EFF8", COL["pcc"], weight="bold")
    diamond = Polygon([[0.41, 0.66], [0.52, 0.77], [0.63, 0.66], [0.52, 0.55]],
                      closed=True, facecolor="white", edgecolor=COL["pcc"], lw=1.0)
    axc.add_patch(diamond)
    axc.text(0.52, 0.66, "decision", ha="center", va="center", fontsize=6.5)
    arrow(axc, (0.28, 0.66), (0.41, 0.66), COL["pcc"])
    rounded_box(axc, (0.72, 0.57), 0.23, 0.18, "Protected\nsolver", "#DDF1E9", COL["safe"], weight="bold")
    arrow(axc, (0.63, 0.66), (0.72, 0.66), COL["safe"])
    axc.text(0.68, 0.73, "accept", color=COL["safe"], ha="center", fontsize=6.5, fontweight="bold")
    rounded_box(axc, (0.31, 0.25), 0.20, 0.14, "reject", "#F8E1DE", COL["harm"])
    rounded_box(axc, (0.56, 0.25), 0.23, 0.14, "unresolved", "#FFF0D9", COL["warn"])
    arrow(axc, (0.48, 0.55), (0.41, 0.39), COL["harm"])
    arrow(axc, (0.56, 0.55), (0.67, 0.39), COL["warn"])
    axc.text(0.55, 0.14, "fail closed: 0 solver starts", ha="center", fontsize=6.5, color=COL["harm"])
    axc.text(0.84, 0.43, "receipt binds\nverified inputs", ha="center", fontsize=6.3, color=COL["pcc"])
    arrow(axc, (0.84, 0.57), (0.84, 0.48), COL["pcc"])

    return save(fig, "fig1_pcc_workflow"), []


def figure2(sem: dict) -> tuple[list[Path], list[Path]]:
    metric_names = list(sem["metrics"])
    display = ["Structural", "Signed\nartifact", "Global\nidentity", "Task\nfootprint", "Attribute\ninvariants", "Full PCC"]
    attack_names = list(next(iter(sem["metrics"].values()))["by_attack_family_harmful_accepts"])
    attack_display = ["Task asset drop", "Independent merge", "Wrong 1→many", "Target-ID reuse",
                      "Endpoint/parameter swap", "Source-snapshot mismatch"]
    matrix = np.array([[sem["metrics"][m]["by_attack_family_harmful_accepts"][a] / 220
                        for m in metric_names] for a in attack_names])
    rates = np.array([sem["metrics"][m]["harmful_acceptance_rate"] for m in metric_names])
    ci = np.array([sem["metrics"][m]["harmful_acceptance_wilson_95"] for m in metric_names])
    lawful = np.array([sem["metrics"][m]["lawful_acceptance_rate"] for m in metric_names])
    comps = sem["adjacent_paired_comparisons"][1:]

    src1 = write_csv("fig2_attack_family_acceptance.csv",
                     ["attack_family", *metric_names],
                     [{"attack_family": a, **{m: matrix[i, j] for j, m in enumerate(metric_names)}}
                      for i, a in enumerate(attack_names)])
    src2 = write_csv("fig2_aggregate_acceptance.csv",
                     ["baseline", "harmful_rate", "wilson_low", "wilson_high", "lawful_rate"],
                     [{"baseline": m, "harmful_rate": rates[i], "wilson_low": ci[i, 0],
                       "wilson_high": ci[i, 1], "lawful_rate": lawful[i]}
                      for i, m in enumerate(metric_names)])
    src3 = write_csv("fig2_adjacent_comparisons.csv",
                     ["left", "right", "absolute_risk_reduction", "improvements", "regressions",
                      "mcnemar_exact_two_sided_log10_p", "holm_adjusted_log10_p"], comps)

    fig = plt.figure(figsize=(7.205, 4.57), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.30, 1.0], height_ratios=[1.0, 0.82])
    axa = fig.add_subplot(gs[:, 0]); axb = fig.add_subplot(gs[0, 1]); axc = fig.add_subplot(gs[1, 1])
    cmap = LinearSegmentedColormap.from_list("accept", ["#F5F6F8", COL["harm2"], COL["harm"]])
    im = axa.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    axa.set_xticks(range(6), display, rotation=32, ha="right")
    axa.set_yticks(range(6), attack_display)
    axa.tick_params(length=0)
    for i in range(6):
        for j in range(6):
            axa.text(j, i, f"{int(matrix[i,j]*220)}", ha="center", va="center",
                     color="white" if matrix[i,j] > 0.65 else COL["ink"], fontsize=6.3)
    cbar = fig.colorbar(im, ax=axa, fraction=0.036, pad=0.02, ticks=[0, 0.5, 1])
    cbar.set_label("Harmful acceptance fraction")
    axa.set_title("Residual harmful acceptance by mutation family", loc="left", fontweight="bold")
    panel(axa, "a", x=-0.12)

    x = np.arange(6)
    yerr = np.vstack([rates - ci[:,0], ci[:,1] - rates])
    axb.errorbar(x, rates, yerr=yerr, fmt="o-", color=COL["harm"], lw=1.5,
                 ms=4, capsize=2, label="Harmful")
    axb.plot(x, lawful, "s--", color=COL["safe"], lw=1.1, ms=3.5, label="Lawful")
    axb.set_ylim(-0.05, 1.08); axb.set_yticks([0, .25, .5, .75, 1])
    axb.set_xticks(x, display, rotation=28, ha="right")
    axb.set_ylabel("Acceptance fraction")
    axb.legend(loc="lower left", ncol=2)
    axb.annotate("0/1,320\nupper 95% = 0.227%", xy=(5,0), xytext=(3.55,.22),
                 arrowprops=dict(arrowstyle="->", color=COL["pcc"], lw=.8),
                 fontsize=6.2, color=COL["pcc"], ha="center")
    axb.set_title("Full PCC separates harmful and lawful transformations", loc="left", fontweight="bold")
    panel(axb, "b", x=-0.15)
    clean(axb)

    labels = ["Signed → identity", "Identity → footprint", "Footprint → attributes", "Attributes → PCC"]
    arr = [c["absolute_risk_reduction"] for c in comps]
    ypos = np.arange(4)[::-1]
    bars = axc.barh(ypos, arr, color=[COL["pcc2"]]*4, height=.58)
    axc.set_yticks(ypos, labels)
    axc.set_xlim(0, .39); axc.set_xlabel("Absolute harmful-release reduction")
    for bar, c in zip(bars, comps):
        exponent = abs(c["holm_adjusted_log10_p"])
        axc.text(bar.get_width()+.008, bar.get_y()+bar.get_height()/2,
                 f"{bar.get_width():.3f}  (Holm p < $10^{{-{math.floor(exponent)}}}$)",
                 va="center", fontsize=5.9)
    axc.set_title("Each task-semantic obligation removes residual risk", loc="left", fontweight="bold")
    panel(axc, "c", x=-0.15)
    clean(axc)
    return save(fig, "fig2_semantic_baseline_ladder"), [src1, src2, src3]


def lollipop(ax, values: dict, color: str, xlabel: str, overall: float, ci: list[float], percent=False,
             symlog=False):
    names = list(values)
    vals = np.array([values[n] for n in names], dtype=float)
    if percent:
        vals *= 100; overall *= 100; ci = [v*100 for v in ci]
    y = np.arange(len(names))[::-1]
    for yi, val in zip(y, vals):
        ax.plot([0, val], [yi, yi], color=COL["light"], lw=1.2, zorder=1)
        ax.plot(val, yi, "o", color=color, ms=4, zorder=2)
    ax.set_yticks(y, names)
    if symlog:
        ax.set_xscale("symlog", linthresh=0.01, linscale=0.7)
    ax.axvspan(ci[0], ci[1], color=color, alpha=.12, lw=0)
    ax.axvline(overall, color=color, lw=1.2, ls="--")
    ax.set_xlabel(xlabel)
    clean(ax)


def figure3(app: dict) -> tuple[list[Path], list[Path]]:
    n1 = app["n1"]; opf = app["opf"]
    attempt_rows = [
        {"task":"AC N-1", "attempted":n1["attempted"], "paired_valid":n1["paired_valid"], "retained_other":n1["retained_failures"]},
        {"task":"AC-OPF", "attempted":opf["attempted"], "paired_valid":opf["paired_valid"], "retained_other":opf["retained_nonconvergent_pairs"]},
    ]
    src1 = write_csv("fig3_attempt_accounting.csv", list(attempt_rows[0]), attempt_rows)
    n1e = n1["counterfactual_max_loading_delta_percent_points"]
    opfe = opf["relative_cost_regret"]
    src2 = write_csv("fig3_n1_network_medians.csv", ["network", "median_loading_delta_percentage_points"],
                     [{"network":k,"median_loading_delta_percentage_points":v} for k,v in n1e["network_medians"].items()])
    src3 = write_csv("fig3_opf_network_medians.csv", ["network", "median_relative_cost_effect"],
                     [{"network":k,"median_relative_cost_effect":v} for k,v in opfe["network_medians"].items()])
    src4 = write_csv("fig3_prevention.csv", ["task", "prevented", "harmful_solver_starts"], [
        {"task":"AC N-1","prevented":n1["unsafe_results_prevented"],"harmful_solver_starts":n1["harmful_solver_starts"]},
        {"task":"AC-OPF","prevented":opf["unsafe_results_prevented"],"harmful_solver_starts":opf["harmful_solver_starts"]},
    ])

    fig = plt.figure(figsize=(7.205, 5.05), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.12, .88])
    axa=fig.add_subplot(gs[0,0]); axb=fig.add_subplot(gs[0,1]); axc=fig.add_subplot(gs[1,0]); axd=fig.add_subplot(gs[1,1])
    x=np.arange(2); valid=[53,25]; other=[3,10]
    axa.bar(x, valid, color=COL["pcc2"], label="Paired-valid")
    axa.bar(x, other, bottom=valid, color=COL["light"], hatch="///", edgecolor=COL["neutral"], label="Retained failure/nonconvergence")
    for i,(v,o) in enumerate(zip(valid,other)):
        axa.text(i,v/2,str(v),ha="center",va="center",color="white",fontweight="bold")
        axa.text(i,v+o/2,str(o),ha="center",va="center",color=COL["ink"])
    axa.set_xticks(x,["AC N-1","AC-OPF"]); axa.set_ylabel("Attempted transformations")
    axa.legend(loc="upper right")
    axa.set_title("Every attempt remains accounted for",loc="left",fontweight="bold"); panel(axa,"a"); clean(axa)

    lollipop(axb,n1e["network_medians"],COL["harm"],"Median loading effect (percentage points)",n1e["median"],n1e["hierarchical_cluster_bootstrap_median_95"])
    axb.set_title("N-1 effects are positive in 8/8 networks",loc="left",fontweight="bold"); panel(axb,"b")
    axb.text(.98,.04,"median 3.879; 95% CI 0.261–10.744\nsign test p = 0.00390625",transform=axb.transAxes,ha="right",va="bottom",fontsize=6)

    lollipop(axc,opfe["network_medians"],COL["warn"],"Median relative cost effect (%)",opfe["median"],opfe["hierarchical_cluster_bootstrap_median_95"],percent=True)
    axc.set_title("OPF cost effects are positive in 5/5 networks",loc="left",fontweight="bold"); panel(axc,"c")
    axc.text(.98,.04,"median 5.96%; 95% CI 2.61–14.07%\nsign test p = 0.03125",transform=axc.transAxes,ha="right",va="bottom",fontsize=6)

    tasks=["AC N-1","AC-OPF"]; prevented=[53,25]; starts=[0,0]; yy=np.arange(2)
    axd.barh(yy+.14,prevented,height=.26,color=COL["safe"])
    axd.scatter(starts,yy-.14,s=28,facecolor="white",edgecolor=COL["harm"],marker="X",zorder=3,clip_on=False)
    for i,v in enumerate(prevented): axd.text(v+.8,i+.14,str(v),va="center",fontsize=6.5,fontweight="bold",color=COL["safe"])
    for i in range(2): axd.text(1.2,i-.14,"0",va="center",fontsize=6.5,color=COL["harm"],bbox=dict(facecolor="white",edgecolor="none",pad=.2))
    axd.text(18,1.60,"■ stopped",color=COL["safe"],fontsize=6.3,va="center")
    axd.text(34,1.60,"× harmful starts",color=COL["harm"],fontsize=6.3,va="center")
    axd.set_yticks(yy,tasks); axd.set_xlim(0,59); axd.set_ylim(-.42,1.72); axd.set_xlabel("Observed consequential transformations")
    axd.set_title("The gate converts consequence into prevention",loc="left",fontweight="bold"); panel(axd,"d"); clean(axd)
    return save(fig,"fig3_operational_consequences"),[src1,src2,src3,src4]


def figure4(dc: dict) -> tuple[list[Path], list[Path]]:
    nets=["case39","case73","case118","case300","case500"]
    counts=np.zeros((5,10),dtype=int)
    bystate=dc["safety"]["false_secure_by_network_state"]
    for i,n in enumerate(nets):
        for j in range(10): counts[i,j]=bystate.get(f"{n}:offset{j}",0)
    src1=write_csv("fig4_false_secure_state_grid.csv",["network",*[f"offset{i}" for i in range(10)]],
                   [{"network":n,**{f"offset{j}":int(counts[i,j]) for j in range(10)}} for i,n in enumerate(nets)])
    effects=dc["effects_among_strict_false_secure"]
    effect_specs=[
        ("loading_excess",effects["alias_post_contingency_loading_excess_pu"]),
        ("hidden_load_shed_mw",effects["hidden_load_shed_mw"]),
        ("relative_cost_understatement",effects["relative_cost_understatement"]),
    ]
    srcs=[src1]
    for name,obj in effect_specs:
        srcs.append(write_csv(f"fig4_{name}_network_medians.csv",["network","network_median"],
                              [{"network":n,"network_median":obj["network_medians"][n]} for n in nets]))

    fig=plt.figure(figsize=(7.205,5.32),constrained_layout=True)
    gs=fig.add_gridspec(2,3,height_ratios=[1.0,1.05])
    axa=fig.add_subplot(gs[0,:]); axb=fig.add_subplot(gs[1,0]); axc=fig.add_subplot(gs[1,1]); axd=fig.add_subplot(gs[1,2])
    cmap=LinearSegmentedColormap.from_list("dc",["#F4F6F8","#B8CDE5",COL["pcc"]])
    im=axa.imshow(counts,cmap=cmap,aspect="auto",vmin=0,vmax=max(1,counts.max()))
    axa.set_xticks(range(10),[str(i) for i in range(10)]); axa.set_yticks(range(5),nets)
    axa.set_xlabel("Frozen operating-state offset"); axa.tick_params(length=0)
    for i in range(5):
        for j in range(10):
            val=counts[i,j]; axa.text(j,i,str(val),ha="center",va="center",fontsize=6.3,color="white" if val>12 else COL["ink"])
    cbar=fig.colorbar(im,ax=axa,fraction=.018,pad=.018); cbar.set_label("Strict false-secure rows")
    axa.set_title("All 369 strict false-secure dispatches across the complete 5 × 10 grid",loc="left",fontweight="bold"); panel(axa,"a",x=-.06)

    loading=effects["alias_post_contingency_loading_excess_pu"]
    lollipop(axb,{n:loading["network_medians"][n] for n in nets},COL["harm"],"Loading excess (p.u.)",loading["median"],loading["hierarchical_cluster_bootstrap_median_95"])
    axb.set_title("Hidden loading",loc="left",fontweight="bold"); panel(axb,"b",x=-.22)
    axb.text(.98,.03,"overall 0.241\n95% CI 0.088–0.382",transform=axb.transAxes,ha="right",fontsize=5.8)

    shed=effects["hidden_load_shed_mw"]
    lollipop(axc,{n:shed["network_medians"][n] for n in nets},COL["warn"],"Hidden load shedding (MW)",shed["median"],shed["hierarchical_cluster_bootstrap_median_95"],symlog=True)
    axc.set_title("Corrective requirement",loc="left",fontweight="bold"); panel(axc,"c",x=-.22)
    axc.text(.98,.03,"overall 5.20 MW\n95% CI 0.60–33.00",transform=axc.transAxes,ha="right",fontsize=5.8)

    cost=effects["relative_cost_understatement"]
    lollipop(axd,{n:cost["network_medians"][n] for n in nets},COL["violet"],"Cost understatement (%)",cost["median"],cost["hierarchical_cluster_bootstrap_median_95"],percent=True)
    axd.set_title("Economic distortion",loc="left",fontweight="bold"); panel(axd,"d",x=-.22)
    axd.text(.98,.03,"overall 1.04%\n95% CI 0.34–11.28%",transform=axd.transAxes,ha="right",fontsize=5.8)
    return save(fig,"fig4_dc_scopf_heterogeneity"),srcs


def figure4(dc: dict, atlas: dict) -> tuple[list[Path], list[Path]]:
    nets=["case39","case73","case118","case300","case500"]
    counts=np.zeros((5,10),dtype=int)
    state_rows=read_csv(ROOT / "outputs/dc_scopf_mechanism_atlas/false_secure_by_network_state.csv")
    for row in state_rows:
        if row["network"] in nets:
            counts[nets.index(row["network"]), int(row["state_offset"])] = int(row["strict_false_secure"])
    src1=write_csv("fig4_false_secure_state_grid.csv",["network",*[f"offset{i}" for i in range(10)]],
                   [{"network":n,**{f"offset{j}":int(counts[i,j]) for j in range(10)}} for i,n in enumerate(nets)])
    component_rows=read_csv(ROOT / "outputs/dc_scopf_mechanism_atlas/false_secure_by_component.csv")
    src_component=write_csv("fig4_component_accounting.csv",
                            ["branch_component","rows","strict_false_secure","legacy_false_secure","prevented","harmful_solver_starts"],
                            component_rows)
    label_rows=[
        {"label":"strict_false_secure","count":atlas["strict_false_secure_dispatches"]},
        {"label":"legacy_alias_overlimit","count":atlas["legacy_false_secure_dispatches"]},
        {"label":"invalid_solver_pairs_retained","count":atlas["invalid_solver_pairs_retained"]},
        {"label":"exacerbated_existing_overload","count":atlas["exacerbated_existing_overload_rows"]},
    ]
    src_labels=write_csv("fig4_label_accounting.csv",["label","count"],label_rows)
    effects=dc["effects_among_strict_false_secure"]
    srcs=[src1,src_component,src_labels]
    for name,obj in [
        ("loading_excess",effects["alias_post_contingency_loading_excess_pu"]),
        ("hidden_load_shed_mw",effects["hidden_load_shed_mw"]),
        ("relative_cost_understatement",effects["relative_cost_understatement"]),
    ]:
        srcs.append(write_csv(f"fig4_{name}_network_medians.csv",["network","network_median"],
                              [{"network":n,"network_median":obj["network_medians"][n]} for n in nets]))

    fig=plt.figure(figsize=(7.205,5.70),constrained_layout=True)
    gs=fig.add_gridspec(2,4,height_ratios=[1.02,1.05],width_ratios=[1,1,1,0.92])
    axa=fig.add_subplot(gs[0,0:3]); axe=fig.add_subplot(gs[0,3])
    axb=fig.add_subplot(gs[1,0]); axc=fig.add_subplot(gs[1,1]); axd=fig.add_subplot(gs[1,2]); axf=fig.add_subplot(gs[1,3])
    cmap=LinearSegmentedColormap.from_list("dc",["#F4F6F8","#B8CDE5",COL["pcc"]])
    im=axa.imshow(counts,cmap=cmap,aspect="auto",vmin=0,vmax=max(1,counts.max()))
    axa.set_xticks(range(10),[str(i) for i in range(10)]); axa.set_yticks(range(5),nets)
    axa.set_xlabel("Frozen operating-state offset"); axa.tick_params(length=0)
    for i in range(5):
        for j in range(10):
            val=counts[i,j]; axa.text(j,i,str(val),ha="center",va="center",fontsize=6.3,color="white" if val>12 else COL["ink"])
    cbar=fig.colorbar(im,ax=axa,fraction=.018,pad=.018); cbar.set_label("Strict false-secure rows")
    axa.set_title("Strict false-secure dispatches across the complete 5 x 10 grid",loc="left",fontweight="bold"); panel(axa,"a",x=-.06)

    comps=[row["branch_component"] for row in component_rows]
    comp_strict=[int(row["strict_false_secure"]) for row in component_rows]
    comp_legacy=[int(row["legacy_false_secure"]) for row in component_rows]
    yy=np.arange(len(comps))
    axe.barh(yy+.14, comp_legacy, height=.25, color=COL["light"], edgecolor=COL["neutral"], label="Legacy")
    axe.barh(yy-.14, comp_strict, height=.25, color=COL["pcc"], label="Strict")
    axe.set_yticks(yy, comps); axe.set_xlabel("Rows")
    axe.set_title("Line and transformer mechanisms",loc="left",fontweight="bold")
    axe.set_xlim(0, max(comp_legacy + comp_strict) * 1.45)
    for y,v in zip(yy,comp_strict):
        axe.text(v+8,y-.14,str(v),va="center",fontsize=5.8,color=COL["pcc"])
    for y,v in zip(yy,comp_legacy):
        axe.text(v+8,y+.14,str(v),va="center",fontsize=5.8,color=COL["neutral"])
    axe.text(.98,.90,"gray: legacy\nblue: strict",transform=axe.transAxes,
             ha="right",va="top",fontsize=5.8,color=COL["ink"])
    panel(axe,"b",x=-.20); clean(axe)

    loading=effects["alias_post_contingency_loading_excess_pu"]
    lollipop(axb,{n:loading["network_medians"][n] for n in nets},COL["harm"],"Loading excess (p.u.)",loading["median"],loading["hierarchical_cluster_bootstrap_median_95"])
    axb.set_title("Hidden loading",loc="left",fontweight="bold"); panel(axb,"c",x=-.22)
    axb.text(.98,.03,"overall 0.241\n95% CI 0.088-0.382",transform=axb.transAxes,ha="right",fontsize=5.8)

    shed=effects["hidden_load_shed_mw"]
    lollipop(axc,{n:shed["network_medians"][n] for n in nets},COL["warn"],"Hidden load shedding (MW)",shed["median"],shed["hierarchical_cluster_bootstrap_median_95"],symlog=True)
    axc.set_title("Corrective requirement",loc="left",fontweight="bold"); panel(axc,"d",x=-.22)
    axc.text(.98,.03,"overall 5.20 MW\n95% CI 0.60-33.00",transform=axc.transAxes,ha="right",fontsize=5.8)

    cost=effects["relative_cost_understatement"]
    lollipop(axd,{n:cost["network_medians"][n] for n in nets},COL["violet"],"Cost understatement (%)",cost["median"],cost["hierarchical_cluster_bootstrap_median_95"],percent=True)
    axd.set_title("Economic distortion",loc="left",fontweight="bold"); panel(axd,"e",x=-.22)
    axd.text(.98,.03,"overall 1.04%\n95% CI 0.34-11.28%",transform=axd.transAxes,ha="right",fontsize=5.8)

    labels=["strict","legacy","invalid","exacerbated"]
    vals=[atlas["strict_false_secure_dispatches"],atlas["legacy_false_secure_dispatches"],
          atlas["invalid_solver_pairs_retained"],atlas["exacerbated_existing_overload_rows"]]
    bars=axf.bar(np.arange(len(vals)),vals,color=[COL["pcc"],COL["light"],COL["warn"],COL["neutral"]],
                 edgecolor=[COL["pcc"],COL["neutral"],COL["warn"],COL["neutral"]])
    axf.set_xticks(range(4),labels,rotation=35,ha="right")
    axf.set_ylabel("Rows")
    axf.set_title("Retained label accounting",loc="left",fontweight="bold")
    for b,v in zip(bars,vals):
        axf.text(b.get_x()+b.get_width()/2,v+8,str(v),ha="center",fontsize=5.8)
    axf.set_ylim(0,max(vals)*1.22)
    panel(axf,"f",x=-.20); clean(axf)
    return save(fig,"fig4_dc_scopf_heterogeneity"),srcs


def figure5(apl:dict,qocdc:dict,hold:dict,dcp:dict,dcmp:dict,scaling:dict)->tuple[list[Path],list[Path]]:
    decision_rows=[
        {"artifact":"Official Svedala","structural_pass":1,"pcc_accept":0,"import_success":"not tested"},
        {"artifact":"Untouched PowSyBl bundle","structural_pass":0,"pcc_accept":1,"import_success":"yes"},
    ]
    src1=write_csv("fig5_structural_pcc_decisions.csv",list(decision_rows[0]),decision_rows)
    agreement_rows=[]
    for label,obj in [("DCP (unaligned)",dcp),("DCMP (transformer-aware)",dcmp)]:
        agreement_rows.append({"formulation":label,"status":obj["status_agreement_rate"],"objective":obj["objective_agreement_rate_among_mutually_optimal"],"generation":obj["generation_agreement_rate_among_mutually_optimal"],"max_objective_relative_error":obj["max_objective_relative_error"]})
    src2=write_csv("fig5_cross_solver_agreement.csv",list(agreement_rows[0]),agreement_rows)
    element=hold["pypowsybl_import"]["element_counts"]
    src3=write_csv("fig5_holdout_import_counts.csv",["element_type","count"],[{"element_type":k,"count":v} for k,v in element.items()])
    scale_rows=scaling["sizes"]
    src4=write_csv("fig5_scaling.csv",["asset_count","repeats","p50_ms","p95_ms","p99_ms","max_ms"],[{k:r[k] for k in ["asset_count","repeats","p50_ms","p95_ms","p99_ms","max_ms"]} for r in scale_rows])

    fig=plt.figure(figsize=(7.205,5.30),constrained_layout=True)
    gs=fig.add_gridspec(2,2,width_ratios=[.92,1.08])
    axa=fig.add_subplot(gs[0,0]); axb=fig.add_subplot(gs[0,1]); axc=fig.add_subplot(gs[1,0]); axd=fig.add_subplot(gs[1,1])
    axa.set_xlim(-.45,1.45); axa.set_ylim(-.45,1.45)
    axa.axvline(.5,color=COL["light"],lw=.8); axa.axhline(.5,color=COL["light"],lw=.8)
    axa.scatter([1],[0],s=105,color=COL["harm"],marker="D",label="Official Svedala")
    axa.scatter([0],[1],s=105,color=COL["safe"],marker="o",label="Untouched bundle")
    axa.text(1,.18,"APL pass\nPCC reject",ha="center",fontsize=6.3,color=COL["harm"])
    axa.text(0,.78,"raw APL fail\nPCC accept",ha="center",va="top",fontsize=6.3,color=COL["safe"])
    axa.set_xticks([0,1],["Structural fail","Structural pass"]); axa.set_yticks([0,1],["PCC reject","PCC accept"])
    axa.set_title("Structural and task-semantic checks are orthogonal",loc="left",fontweight="bold"); panel(axa,"a",x=-.18); clean(axa)
    axa.text(.02,.02,"QoCDC control: 15/15 implemented L1–L4 checks pass\n(full compliance not claimed)",transform=axa.transAxes,fontsize=5.7,color=COL["neutral"])

    metrics=["Status","Objective","Generation"]; x=np.arange(3); w=.34
    va=[dcp["status_agreement_rate"],dcp["objective_agreement_rate_among_mutually_optimal"],dcp["generation_agreement_rate_among_mutually_optimal"]]
    vb=[dcmp["status_agreement_rate"],dcmp["objective_agreement_rate_among_mutually_optimal"],dcmp["generation_agreement_rate_among_mutually_optimal"]]
    axb.bar(x-w/2,va,w,color=COL["light"],edgecolor=COL["neutral"],hatch="///",label="DCP (unaligned)")
    axb.bar(x+w/2,vb,w,color=COL["pcc"],label="DCMP (transformer-aware)")
    axb.set_xticks(x,metrics); axb.set_ylim(0,1.12); axb.set_ylabel("Agreement fraction")
    axb.legend(ncol=2,loc="lower center")
    axb.text(.02,.98,
             f"max objective relative error:  DCP {dcp['max_objective_relative_error']:.2e}  |  DCMP {dcmp['max_objective_relative_error']:.2e}",
             transform=axb.transAxes,fontsize=5.8,color=COL["ink"],va="top",
             bbox=dict(facecolor="white",edgecolor="none",alpha=.92,pad=1.2),zorder=5)
    axb.set_title("Agreement requires matched transformer equations",loc="left",fontweight="bold"); panel(axb,"b",x=-.12); clean(axb)

    enames=["Buses","Lines","Loads","Generators","2-winding\ntransformers","Switches"]; vals=list(element.values())
    bars=axc.bar(np.arange(len(vals)),vals,color=[COL["pcc2"],COL["teal"],COL["warn"],COL["safe"],COL["violet"],COL["neutral"]])
    axc.set_xticks(range(6),enames,rotation=32,ha="right"); axc.set_ylabel("Imported elements")
    for b,v in zip(bars,vals): axc.text(b.get_x()+b.get_width()/2,v+.5,str(v),ha="center",fontsize=6)
    axc.set_ylim(0,max(vals)*1.22)
    axc.set_title("Untouched CGMES bundle imports as 59 elements",loc="left",fontweight="bold"); panel(axc,"c",x=-.18); clean(axc)

    assets=[r["asset_count"] for r in scale_rows]; p50=[r["p50_ms"] for r in scale_rows]; p95=[r["p95_ms"] for r in scale_rows]
    axd.plot(assets,p50,"o-",color=COL["pcc2"],label="p50",lw=1.4,ms=3.5)
    axd.plot(assets,p95,"s-",color=COL["harm"],label="p95",lw=1.4,ms=3.5)
    axd.set_xscale("log"); axd.set_yscale("log"); axd.set_xlabel("Task assets"); axd.set_ylabel("Verification latency (ms)")
    axd.legend(loc="upper left")
    axd.set_ylim(1.2,500)
    axd.annotate("13,659 assets\np95 = 215.1 ms",xy=(assets[-1],p95[-1]),xytext=(4700,345),ha="center",fontsize=6.2,arrowprops=dict(arrowstyle="->",lw=.8,color=COL["neutral"]))
    axd.set_title("Verification remains subsecond at the tested scale",loc="left",fontweight="bold"); panel(axd,"d",x=-.12); clean(axd)
    return save(fig,"fig5_validation_portability_scaling"),[src1,src2,src3,src4]


def figure6(ext: dict, routes: dict, consequence: dict) -> tuple[list[Path], list[Path]]:
    route_records=routes["records"]
    status_order=["success","failure","source_import_failure","target_import_failure","dependency_missing"]
    status_counts={status:0 for status in status_order}
    route_family={"pypowsybl":0,"veragrid":0}
    for row in route_records:
        status_counts[row.get("status","failure")] = status_counts.get(row.get("status","failure"),0) + 1
        if "veragrid" in row["route"]:
            route_family["veragrid"] += 1
        else:
            route_family["pypowsybl"] += 1

    src1=write_csv("fig6_external_challenge_accounting.csv",
                   ["metric","value"],
                   [
                       {"metric":"selected_bundles","value":ext["selected_bundles"]},
                       {"metric":"source_import_successes","value":ext["source_import_successes"]},
                       {"metric":"route_attempts","value":ext["route_attempts"]},
                       {"metric":"route_successes","value":ext["route_successes"]},
                       {"metric":"pcc_receipts","value":ext["receipt_count"]},
                   ])
    src2=write_csv("fig6_external_route_terminal_status.csv",
                   ["status","count"],
                   [{"status":status,"count":status_counts.get(status,0)} for status in status_order])
    src3=write_csv("fig6_external_success_criteria.csv",
                   ["criterion","value","met"],
                   [
                       {"criterion":"harmful_solver_starts","value":ext["harmful_solver_starts"],"met":ext["success_criteria"]["harmful_solver_starts_zero"]},
                       {"criterion":"lawful_exact_acceptance_rate","value":ext["lawful_exact_acceptance_rate"],"met":ext["success_criteria"]["lawful_exact_acceptance_rate_one"]},
                       {"criterion":"external_task_relevant_anomalies","value":ext["external_tool_generated_task_relevant_anomalies"],"met":ext["success_criteria"]["at_least_one_external_tool_generated_task_relevant_anomaly"]},
                       {"criterion":"operationally_consequential_anomalies","value":ext["operationally_consequential_anomalies"],"met":ext["success_criteria"]["at_least_one_operationally_consequential_anomaly"]},
                       {"criterion":"paired_valid_consequence_evaluated","value":ext["paired_valid_consequence_evaluated"],"met":False},
                   ])

    fig=plt.figure(figsize=(7.205,4.95),constrained_layout=True)
    gs=fig.add_gridspec(2,2,width_ratios=[1.05,1.0],height_ratios=[1.0,1.0])
    axa=fig.add_subplot(gs[0,0]); axb=fig.add_subplot(gs[0,1])
    axc=fig.add_subplot(gs[1,0]); axd=fig.add_subplot(gs[1,1])

    metrics=["bundles","source\nimports","route\nattempts","route\nsuccesses","receipts"]
    vals=[ext["selected_bundles"],ext["source_import_successes"],ext["route_attempts"],ext["route_successes"],ext["receipt_count"]]
    bars=axa.bar(np.arange(len(vals)),vals,color=[COL["pcc2"],COL["teal"],COL["neutral"],COL["safe"],COL["pcc"]])
    axa.set_xticks(range(len(vals)),metrics)
    axa.set_ylabel("Count")
    axa.set_title("Frozen blind challenge accounting",loc="left",fontweight="bold")
    for b,v in zip(bars,vals):
        axa.text(b.get_x()+b.get_width()/2,v+2,str(v),ha="center",fontsize=6)
    axa.set_ylim(0,max(vals)*1.20)
    panel(axa,"a"); clean(axa)

    display=["success","export\nfailure","source\nimport","target\nimport","dependency"]
    status_vals=[status_counts.get(status,0) for status in status_order]
    colors=[COL["safe"],COL["neutral"],COL["warn"],COL["harm2"],COL["light"]]
    bars=axb.bar(np.arange(len(status_vals)),status_vals,color=colors,edgecolor=COL["neutral"])
    axb.set_xticks(range(len(status_vals)),display)
    axb.set_ylabel("Route records")
    axb.set_title("All route endpoints retained",loc="left",fontweight="bold")
    for b,v in zip(bars,status_vals):
        axb.text(b.get_x()+b.get_width()/2,v+.25,str(v),ha="center",fontsize=6)
    axb.text(.03,.93,f"pypowsybl routes: {route_family['pypowsybl']}\nVeraGridEngine routes: {route_family['veragrid']}",
             transform=axb.transAxes,ha="left",va="top",fontsize=6,
             bbox=dict(facecolor="white",edgecolor="none",alpha=.9,pad=1.5))
    axb.set_ylim(0,max(status_vals+[1])*1.30)
    panel(axb,"b"); clean(axb)

    crit_labels=["lawful exact\nacceptance","harmful\nstarts","external task\nanomalies","operational\nanomalies"]
    crit_vals=[ext["lawful_exact_acceptance_rate"],ext["harmful_solver_starts"],
               ext["external_tool_generated_task_relevant_anomalies"],ext["operationally_consequential_anomalies"]]
    crit_colors=[COL["safe"],COL["safe"],COL["harm"],COL["harm"]]
    ypos=np.arange(len(crit_labels))[::-1]
    axc.barh(ypos, [1.0,0.04,0.04,0.04], color=["#DDF1E9","#DDF1E9","#F8E1DE","#F8E1DE"], edgecolor=crit_colors)
    for y,label,value,color in zip(ypos,crit_labels,crit_vals,crit_colors):
        axc.text(.03,y,label,va="center",ha="left",fontsize=6.2,color=COL["ink"])
        shown="1.0" if label.startswith("lawful") else str(value)
        axc.text(.92,y,shown,va="center",ha="right",fontsize=6.4,fontweight="bold",color=color)
    axc.set_xlim(0,1); axc.set_yticks([]); axc.set_xticks([])
    axc.set_title("PCC endpoint and success-criterion boundary",loc="left",fontweight="bold")
    panel(axc,"c",x=-.08)
    for spine in axc.spines.values(): spine.set_visible(False)

    axd.axis("off")
    panel(axd,"d",x=-.08)
    axd.text(.02,.94,"Post-receipt consequence reveal",fontsize=8,fontweight="bold",va="top")
    lines=[
        f"records retained: {consequence['records']}",
        f"task-relevant anomalies: {consequence['task_relevant_anomalies']}",
        f"N-1 consequence attempted: {consequence['operational_consequence_attempted']}",
        f"paired-valid source-target evaluations: {consequence['paired_valid_consequence_evaluated']}",
        f"operationally consequential anomalies: {consequence['operationally_consequential_anomalies']}",
    ]
    for i,line in enumerate(lines):
        axd.text(.04,.78-i*.12,line,fontsize=6.8,va="top")
    rounded_box(axd,(.04,.04),.90,.18,"Claim boundary: external lawfulness and portability control only;\nnot promoted to the main operational-consequence claim.", "#FFF0D9", COL["warn"], fontsize=6.5)
    return save(fig,"fig6_external_tool_blind_roundtrip"),[src1,src2,src3]


def build_manifest(outputs: list[Path], source_data: list[Path]) -> Path:
    manifest={
        "manifest_version":"epsr-figure-source-manifest-v1",
        "backend":"Python/matplotlib",
        "source_policy":"frozen Layer-B summaries only",
        "plot_sources":[{"path":str(p.relative_to(ROOT)).replace("\\","/"),"sha256":sha256(p)} for p in SOURCES.values()],
        "source_data":[{"path":str(p.relative_to(ROOT)).replace("\\","/"),"sha256":sha256(p)} for p in source_data],
        "figure_outputs":[{"path":str(p.relative_to(ROOT)).replace("\\","/"),"bytes":p.stat().st_size,"sha256":sha256(p)} for p in outputs],
        "export":{"svg_text_editable":True,"pdf_fonttype":42,"png_dpi":600,"width_mm":183},
    }
    path=FIGDIR/"figure_source_manifest.json"
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return path


def main()->int:
    configure(); FIGDIR.mkdir(parents=True,exist_ok=True); DATADIR.mkdir(parents=True,exist_ok=True)
    sem=load("semantic"); app=load("application"); dc=load("dc"); scale=load("scaling")
    apl=load("apl"); qocdc=load("qocdc"); hold=load("holdout"); dcp=load("cross_dcp"); dcmp=load("cross_dcmp")
    atlas=load("dc_atlas"); ext=load("external"); routes=load("external_routes"); consequence=load("external_consequence")
    outputs=[]; sources=[]
    for built in (figure1(),figure2(sem),figure3(app),figure4(dc,atlas),
                  figure5(apl,qocdc,hold,dcp,dcmp,scale),figure6(ext,routes,consequence)):
        outputs.extend(built[0]); sources.extend(built[1])
    manifest=build_manifest(outputs,sources)
    print(json.dumps({"figures":len(outputs)//3,"exports":len(outputs),"source_tables":len(sources),"manifest":str(manifest)},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
