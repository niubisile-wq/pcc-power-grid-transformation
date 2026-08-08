from __future__ import annotations

import csv
import json
import math
import random
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "pcc_v2_application_statistics"
N1_RESULTS = ROOT / "outputs" / "pcc_v2_n1_gate" / "pcc_v2_n1_gate_results.csv"
OPF_RESULTS = ROOT / "outputs" / "pcc_v2_opf_gate" / "pcc_v2_opf_gate_results.csv"
OPF_EXTENSION_RESULTS = (
    ROOT / "outputs" / "pcc_v2_opf_gate_case9_extension" / "pcc_v2_opf_gate_results.csv"
)


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def hierarchical_cluster_bootstrap(
    rows: list[dict[str, str]], field: str, *, seed: int = 20260807, repetitions: int = 20000
) -> list[float]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row["network"], []).append(float(row[field]))
    networks = sorted(grouped)
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(repetitions):
        values: list[float] = []
        for network in rng.choices(networks, k=len(networks)):
            cluster = grouped[network]
            values.extend(rng.choices(cluster, k=len(cluster)))
        samples.append(statistics.median(values))
    return samples


def summarize_effect(rows: list[dict[str, str]], field: str) -> dict:
    values = [float(row[field]) for row in rows]
    network_medians: dict[str, float] = {}
    for network in sorted({row["network"] for row in rows}):
        network_medians[network] = statistics.median(
            float(row[field]) for row in rows if row["network"] == network
        )
    positive_clusters = sum(value > 0 for value in network_medians.values())
    nonzero_clusters = sum(value != 0 for value in network_medians.values())
    one_sided_sign_p = (
        sum(math.comb(nonzero_clusters, k) for k in range(positive_clusters, nonzero_clusters + 1))
        / (2**nonzero_clusters)
        if nonzero_clusters
        else 1.0
    )
    bootstrap = hierarchical_cluster_bootstrap(rows, field)
    return {
        "n": len(values),
        "networks": len(network_medians),
        "median": statistics.median(values),
        "iqr": [quantile(values, 0.25), quantile(values, 0.75)],
        "range": [min(values), max(values)],
        "positive_rows": sum(value > 0 for value in values),
        "network_medians": network_medians,
        "positive_network_medians": positive_clusters,
        "exact_one_sided_network_sign_p": one_sided_sign_p,
        "hierarchical_cluster_bootstrap_median_95": [quantile(bootstrap, 0.025), quantile(bootstrap, 0.975)],
        "bootstrap_seed": 20260807,
        "bootstrap_repetitions": 20000,
    }


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    n1_all = read_rows(N1_RESULTS)
    n1 = [row for row in n1_all if row["completed"] == "True"]
    opf_all = read_rows(OPF_RESULTS)
    if OPF_EXTENSION_RESULTS.exists():
        opf_all.extend(read_rows(OPF_EXTENSION_RESULTS))
    opf = [row for row in opf_all if row["correct_converged"] == "True" and row["alias_converged"] == "True"]
    summary = {
        "protocol": "pcc_v2_application_statistics_v1",
        "n1": {
            "attempted": len(n1_all),
            "paired_valid": len(n1),
            "retained_failures": len(n1_all) - len(n1),
            "harmful_solver_starts": sum(int(row["harmful_solver_calls"] or 0) for row in n1_all),
            "unsafe_results_prevented": sum(row["unsafe_result_prevented"] == "True" for row in n1_all),
            "counterfactual_max_loading_delta_percent_points": summarize_effect(n1, "counterfactual_max_loading_delta"),
            "counterfactual_max_voltage_delta_pu": summarize_effect(n1, "counterfactual_max_voltage_delta"),
            "nominal_identity_control_max_loading_delta": summarize_effect(n1, "nominal_max_loading_delta"),
        },
        "opf": {
            "attempted": len(opf_all),
            "paired_valid": len(opf),
            "retained_nonconvergent_pairs": len(opf_all) - len(opf),
            "paired_networks": len({row["network"] for row in opf}),
            "nonconvergent_networks": sorted(
                {row["network"] for row in opf_all if row["correct_converged"] != "True" or row["alias_converged"] != "True"}
            ),
            "harmful_solver_starts": sum(int(row["harmful_solver_calls"] or 0) for row in opf_all),
            "unsafe_results_prevented": sum(row["unsafe_result_prevented"] == "True" for row in opf_all),
            "relative_cost_regret": summarize_effect(opf, "relative_cost_regret"),
            "absolute_cost_regret": summarize_effect(opf, "absolute_cost_regret"),
        },
        "interpretation": {
            "confirmatory_unit": "network",
            "row_level_effects": "descriptive_repeated_stress_states",
            "failure_policy": "all_attempts_retained; no outcome-dependent deletion",
            "solver_launch_policy": "harmful transformations fail closed before solver start",
        },
        "ready": (
            len(n1) == 53
            and len(opf) >= 25
            and len({row["network"] for row in opf}) >= 5
        ),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
