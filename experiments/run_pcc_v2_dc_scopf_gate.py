"""PCC v2 gate around native PyPSA/HiGHS security-constrained DC OPF."""

from __future__ import annotations

import argparse
import copy
import csv
import gc
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
import re
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import networkx as nx
import numpy as np
import pandas as pd
import pypsa

logging.getLogger("pypsa").setLevel(logging.ERROR)
logging.getLogger("linopy").setLevel(logging.ERROR)


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_pcc_v2_semantic_benchmark import download_case  # noqa: E402
from validation.execution_gate import ExecutionGate  # noqa: E402
from validation.evidence_schema import EvidenceRow  # noqa: E402
from validation.pcc_v2 import PCCV2Verifier, TaskContract, issue_v2_certificate  # noqa: E402


CASE_FILES = {
    "case39": "pglib_opf_case39_epri.m",
    "case73": "pglib_opf_case73_ieee_rts.m",
    "case162": "pglib_opf_case162_ieee_dtc.m",
    "case179": "pglib_opf_case179_goc.m",
    "case197": "pglib_opf_case197_snem.m",
    "case200": "pglib_opf_case200_activ.m",
    "case240": "pglib_opf_case240_pserc.m",
    "case118": "pglib_opf_case118_ieee.m",
    "case300": "pglib_opf_case300_ieee.m",
    "case500": "pglib_opf_case500_goc.m",
    "case588": "pglib_opf_case588_sdet.m",
    "case793": "pglib_opf_case793_goc.m",
}
LOAD_SCALES = tuple(np.linspace(0.90, 1.10, 10))
OUTPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_gate"
PROTOCOL_VERSION = "pcc_v2_native_dc_scopf_confirmatory_v1"
RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v2"
LOADER_REVISION = "pglib-pypsa-transformer-explicit-v2"
ENVIRONMENT_ID = (
    f"windows-pypsa-{pypsa.__version__}-"
    f"highs-{importlib.metadata.version('highspy')}"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def experiment_key() -> Ed25519PrivateKey:
    """Use a reproducible, experiment-only signing key for stable receipts."""
    seed = hashlib.sha256(PROTOCOL_VERSION.encode("utf-8")).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _matrix(text: str, name: str) -> list[list[float]]:
    uncommented = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
    match = re.search(rf"mpc\.{name}\s*=\s*\[(.*?)\];", uncommented, flags=re.DOTALL)
    if not match:
        raise ValueError(f"matrix_missing:{name}")
    rows = []
    for raw in match.group(1).split(";"):
        raw = raw.strip()
        if raw:
            rows.append([float(value) for value in raw.split()])
    return rows


def load_pglib(path: Path, load_scale: float) -> pypsa.Network:
    text = path.read_text(encoding="utf-8", errors="replace")
    base_match = re.search(r"mpc\.baseMVA\s*=\s*([0-9.eE+-]+)", text)
    if not base_match:
        raise ValueError("base_mva_missing")
    base_mva = float(base_match.group(1))
    buses = _matrix(text, "bus")
    generators = _matrix(text, "gen")
    branches = _matrix(text, "branch")
    costs = _matrix(text, "gencost")

    network = pypsa.Network()
    network.set_snapshots(pd.Index(["now"]))
    bus_voltage = {}
    for row in buses:
        bus_id = str(int(row[0]))
        bus_voltage[bus_id] = max(float(row[9]), 1.0)
        network.add("Bus", bus_id, v_nom=bus_voltage[bus_id])
        if row[2] > 0:
            demand = float(row[2]) * load_scale
            network.add("Load", "load-" + bus_id, bus=bus_id, p_set=demand)
            network.add(
                "Generator",
                "shed-" + bus_id,
                bus=bus_id,
                p_nom=demand,
                p_min_pu=0.0,
                p_max_pu=1.0,
                marginal_cost=100000.0,
            )

    for index, row in enumerate(generators):
        if int(row[7]) <= 0 or row[8] <= 0:
            continue
        p_nom = float(row[8])
        p_min = max(float(row[9]), 0.0)
        cost = costs[index] if index < len(costs) else []
        marginal_cost = float(cost[-2]) if len(cost) >= 2 else float(index + 1)
        quadratic_cost = float(cost[-3]) if len(cost) >= 3 and int(cost[0]) == 2 else 0.0
        network.add(
            "Generator",
            f"gen-{index:04d}",
            bus=str(int(row[0])),
            p_nom=p_nom,
            p_min_pu=p_min / p_nom,
            p_max_pu=1.0,
            marginal_cost=marginal_cost,
            marginal_cost_quadratic=max(quadratic_cost, 0.0),
        )

    for index, row in enumerate(branches):
        if int(row[10]) <= 0 or abs(row[3]) < 1e-12:
            continue
        bus0, bus1 = str(int(row[0])), str(int(row[1]))
        voltage = bus_voltage[bus0]
        x_ohm = abs(float(row[3])) * voltage * voltage / base_mva
        rating = float(row[5])
        if rating <= 0:
            rating = 10.0 * sum(load.p_set for _name, load in network.loads.iterrows())
        branch_name = f"branch-{index:05d}"
        ratio = float(row[8])
        phase_shift = float(row[9])
        if abs(ratio) > 1e-12 or abs(phase_shift) > 1e-12:
            # MATPOWER transformer reactance/resistance are per-unit on the
            # branch base. PyPSA's transformer representation also uses
            # per-unit impedance, while tap and phase shift remain explicit.
            network.add(
                "Transformer",
                branch_name,
                bus0=bus0,
                bus1=bus1,
                x=max(abs(float(row[3])), 1e-8),
                r=max(abs(float(row[2])), 1e-8),
                s_nom=rating,
                tap_ratio=ratio if abs(ratio) > 1e-12 else 1.0,
                phase_shift=phase_shift,
            )
        else:
            network.add(
                "Line",
                branch_name,
                bus0=bus0,
                bus1=bus1,
                x=x_ohm,
                r=max(abs(float(row[2])) * voltage * voltage / base_mva, 1e-6),
                s_nom=rating,
            )
    return network


def non_islanding_branches(network: pypsa.Network) -> list[tuple[str, str]]:
    graph = nx.MultiGraph()
    branches: list[tuple[str, str, str, str]] = []
    for component in ("Line", "Transformer"):
        frame = network.lines if component == "Line" else network.transformers
        for name, row in frame.iterrows():
            graph.add_edge(row.bus0, row.bus1, key=(component, name))
            branches.append((component, str(name), str(row.bus0), str(row.bus1)))
    candidates = []
    for component, name, bus0, bus1 in branches:
        graph.remove_edge(bus0, bus1, key=(component, name))
        if nx.is_connected(graph):
            candidates.append((component, name))
        graph.add_edge(bus0, bus1, key=(component, name))
    return candidates


def branch_index(candidates: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Return a tuple to bypass PyPSA 1.0.4's list-to-Line coercion bug."""
    return tuple(candidates)


def branch_loading(network: pypsa.Network, candidates: list[tuple[str, str]]) -> pd.Series:
    frames = []
    for component in ("Line", "Transformer"):
        names = [name for current, name in candidates if current == component]
        if not names:
            continue
        frame = network.lines_t.p0 if component == "Line" else network.transformers_t.p0
        ratings = network.lines.s_nom if component == "Line" else network.transformers.s_nom
        values = (frame.loc["now", names].abs() / ratings.loc[names].replace(0.0, np.nan))
        values.index = pd.MultiIndex.from_tuples(
            [(component, name) for name in names], names=["component", "name"]
        )
        frames.append(values)
    return pd.concat(frames) if frames else pd.Series(dtype=float)


def solve_scopf(network: pypsa.Network, outages: list[tuple[str, str]]) -> dict:
    started = time.perf_counter()
    status, condition = network.optimize.optimize_security_constrained(
        branch_outages=branch_index(outages) if outages else None,
        solver_name="highs",
        log_to_console=False,
        time_limit=300.0,
    )
    elapsed = time.perf_counter() - started
    if status != "ok":
        raise RuntimeError(f"scopf:{status}:{condition}")
    result = {
        "status": status,
        "condition": condition,
        "objective": float(network.objective),
        "elapsed_s": elapsed,
        "dispatch": {str(key): float(value) for key, value in network.generators_t.p.loc["now"].items()},
        "load_shed_mw": float(
            network.generators_t.p.loc["now"].filter(like="shed-").clip(lower=0.0).sum()
        ),
    }
    # PyPSA retains the complete Linopy model and the native solver object on
    # the Network after optimization.  A confirmatory state solves one full
    # model and one leave-one-out model per candidate, so retaining those
    # objects can exhaust memory even though all required solution values have
    # already been copied into the Network tables and ``result`` above.
    if network.model is not None:
        network.model.solver_model = None
        del network.model
    gc.collect()
    return result


def post_contingency_loading(
    network: pypsa.Network, dispatch: dict[str, float], outage: tuple[str, str]
) -> float:
    post = copy.deepcopy(network)
    post.generators["p_set"] = pd.Series(dispatch)
    post.remove(outage[0], outage[1])
    post.lpf()
    remaining = [("Line", str(name)) for name in post.lines.index]
    remaining += [("Transformer", str(name)) for name in post.transformers.index]
    return float(branch_loading(post, remaining).max())


def semantic_bundle(branch_ids: list[str], omitted: str | None):
    source = {
        "assets": {
            line_id: {"asset_type": "line", "outage_capable": True}
            for line_id in branch_ids
        }
    }
    target = {"assets": {}}
    relations = []
    trace = []
    for line_id in branch_ids:
        target_id = "target-" + line_id
        if line_id == omitted:
            continue
        target["assets"][target_id] = {"asset_type": "line", "outage_capable": True}
        relations.append(
            {
                "source_ids": [line_id],
                "target_ids": [target_id],
                "relation_type": "rename",
                "authoritative_evidence": {"kind": "signed_converter_trace"},
                "intervention_map": {line_id: [target_id]},
            }
        )
        trace.append(
            {
                "source_id": line_id,
                "target_ids": [target_id],
                "relation_type": "rename",
                "authoritative": True,
                "evidence_kind": "signed_converter_trace",
            }
        )
    return source, target, relations, trace


def run_scenario(
    case_name: str,
    path: Path,
    input_hash: str,
    state_offset: int,
    load_scale: float,
    key,
    candidate_mode: str = "stratified",
) -> list[dict]:
    base = load_pglib(path, load_scale)
    candidates = non_islanding_branches(base)
    if len(candidates) < 3:
        raise RuntimeError("insufficient_non_islanding_candidates")
    base_probe = copy.deepcopy(base)
    base_result = solve_scopf(base_probe, [])
    pre_loading = branch_loading(base_probe, candidates).fillna(0.0).sort_values()
    if candidate_mode == "all":
        selected = list(pre_loading.index)
        rank_labels = [
            f"q{index / max(len(selected) - 1, 1):.3f}" for index in range(len(selected))
        ]
    else:
        ranks = [0.20, 0.50, 1.00]
        selected = [pre_loading.index[round((len(pre_loading) - 1) * rank)] for rank in ranks]
        selected = list(dict.fromkeys(selected))
        rank_labels = ["low", "mid", "high"][: len(selected)]

    full_network = copy.deepcopy(base)
    full_result = solve_scopf(full_network, candidates)
    rows = []
    for rank, omitted in zip(rank_labels, selected):
        omitted_frame = base.lines if omitted[0] == "Line" else base.transformers
        omitted_row = omitted_frame.loc[omitted[1]]
        alias_candidates = [branch for branch in candidates if branch != omitted]
        alias_network = copy.deepcopy(base)
        alias_result = solve_scopf(alias_network, alias_candidates)
        alias_post = post_contingency_loading(alias_network, alias_result["dispatch"], omitted)
        full_post = post_contingency_loading(full_network, full_result["dispatch"], omitted)
        candidate_ids = [f"{component}:{name}" for component, name in candidates]
        omitted_id = f"{omitted[0]}:{omitted[1]}"
        source, harmful_target, harmful_relations, harmful_trace = semantic_bundle(
            candidate_ids, omitted_id
        )
        task = TaskContract(
            task_id=f"{case_name}:{load_scale:.4f}:{omitted_id}",
            task_kind="DC_SCOPF",
            source_assets=tuple(candidate_ids),
            target_assets=tuple("target-" + branch_id for branch_id in candidate_ids),
            intervention_type="constraint",
            required_attributes=("asset_type",),
        )
        cert = issue_v2_certificate(
            source,
            harmful_target,
            task_contract=task,
            relations=harmful_relations,
            converter_trace=harmful_trace,
            issuer="pypsa-adapter",
            private_key=key,
            certificate_id="harmful:" + task.task_id,
            transformation_id="harmful:" + task.task_id,
            issued_at="2026-08-06T00:00:00Z",
            nonce="harmful:" + task.task_id,
        )
        solver_calls = []

        def forbidden_solver(_snapshot):
            solver_calls.append(task.task_id)
            network = copy.deepcopy(base)
            return solve_scopf(network, alias_candidates)

        gate = ExecutionGate(
            PCCV2Verifier(trusted_issuers={"pypsa-adapter": key.public_key()})
        ).execute(
            source,
            harmful_target,
            cert,
            requested_task="DC_SCOPF",
            converter_trace=harmful_trace,
            solver=forbidden_solver,
        )
        rows.append(
            {
                "result_schema": RESULT_SCHEMA,
                "protocol_version": PROTOCOL_VERSION,
                "loader_revision": LOADER_REVISION,
                "environment_id": ENVIRONMENT_ID,
                "solver_stack": "PyPSA/HiGHS",
                "input_hash": input_hash,
                "network": case_name,
                "state_offset": state_offset,
                "load_scale": load_scale,
                "loading_rank": rank,
                "omitted_candidate": omitted_id,
                "branch_component": omitted[0],
                "branch_id": omitted[1],
                "tap_ratio": float(omitted_row.get("tap_ratio", 1.0)),
                "phase_shift": float(omitted_row.get("phase_shift", 0.0)),
                "candidate_count": len(candidates),
                "pre_contingency_loading_pu": float(pre_loading.loc[omitted]),
                "base_objective": base_result["objective"],
                "full_objective": full_result["objective"],
                "alias_objective": alias_result["objective"],
                "full_load_shed_mw": full_result["load_shed_mw"],
                "alias_load_shed_mw": alias_result["load_shed_mw"],
                "relative_cost_understatement": max(
                    0.0, (full_result["objective"] - alias_result["objective"]) / max(abs(full_result["objective"]), 1e-12)
                ),
                "full_post_contingency_max_loading_pu": full_post,
                "alias_post_contingency_max_loading_pu": alias_post,
                "false_secure_dispatch": bool(alias_post > 1.0001),
                "gate_decision": gate.receipt.decision,
                "gate_reasons": ";".join(gate.receipt.reasons),
                "gate_verification_us": gate.receipt.verification_us,
                "gate_solver_status": gate.receipt.solver_status,
                "source_hash": gate.receipt.source_input_hash,
                "target_hash": gate.receipt.target_input_hash,
                "certificate_hash": gate.receipt.certificate_hash,
                "harmful_solver_starts": len(solver_calls),
                "unsafe_result_prevented": bool(alias_post > 1.0001 and not solver_calls),
                "full_solver_s": full_result["elapsed_s"],
                "alias_solver_s": alias_result["elapsed_s"],
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="+", choices=CASE_FILES, default=list(CASE_FILES))
    parser.add_argument("--states", type=int, default=len(LOAD_SCALES))
    parser.add_argument("--state-offset", type=int, default=0)
    parser.add_argument("--candidate-mode", choices=("stratified", "all"), default="stratified")
    parser.add_argument("--output-tag", default="")
    args = parser.parse_args()
    if args.output_tag and not all(character.isalnum() or character in "-_" for character in args.output_tag):
        raise ValueError("output tag must contain only letters, digits, hyphen, or underscore")
    if not 1 <= args.states <= len(LOAD_SCALES):
        raise ValueError("states must be between 1 and 10")
    if args.state_offset < 0 or args.state_offset + args.states > len(LOAD_SCALES):
        raise ValueError("state offset and count exceed the frozen state grid")
    output = OUTPUT if not args.output_tag else ROOT / "outputs" / f"pcc_v2_dc_scopf_gate_{args.output_tag}"
    output.mkdir(parents=True, exist_ok=True)
    key = experiment_key()
    rows = []
    failures = []
    run_id = (
        f"{args.candidate_mode}_{'-'.join(args.cases)}_"
        f"offset{args.state_offset}_{args.states}states"
    )
    for case_name in args.cases:
        path, downloaded_sha256 = download_case(CASE_FILES[case_name])
        input_hash = sha256_file(path)
        if input_hash != downloaded_sha256:
            raise RuntimeError(f"download_hash_mismatch:{case_name}")
        selected_scales = LOAD_SCALES[args.state_offset : args.state_offset + args.states]
        for relative_offset, load_scale in enumerate(selected_scales):
            state_offset = args.state_offset + relative_offset
            try:
                rows.extend(
                    run_scenario(
                        case_name,
                        path,
                        input_hash,
                        state_offset,
                        float(load_scale),
                        key,
                        candidate_mode=args.candidate_mode,
                    )
                )
            except Exception as exc:
                failures.append(
                    {
                        "network": case_name,
                        "state_offset": state_offset,
                        "load_scale": float(load_scale),
                        "input_hash": input_hash,
                        "included_in_denominator": True,
                        "error": type(exc).__name__ + ": " + str(exc)[:500],
                    }
                )
            (output / f"dc_scopf_gate_{run_id}_checkpoint.json").write_text(
                json.dumps(
                    {
                        "completed_rows": len(rows),
                        "result_schema": RESULT_SCHEMA,
                        "protocol_version": PROTOCOL_VERSION,
                        "loader_revision": LOADER_REVISION,
                        "rows": rows,
                        "failed_states": failures,
                        "last_network": case_name,
                        "last_load_scale": float(load_scale),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    if rows:
        fields = list(rows[0])
        with (output / f"dc_scopf_gate_{run_id}_results.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        evidence = []
        for index, row in enumerate(rows):
            evidence.append(
                EvidenceRow(
                    experiment_id="pcc-v2-native-pypsa-highs-dc-scopf-v1",
                    scenario_id=(
                        f"{row['network']}:{float(row['load_scale']):.4f}:"
                        f"{row['omitted_candidate']}"
                    ),
                    network=str(row["network"]),
                    data_split="public_pglib_operational",
                    environment=ENVIRONMENT_ID,
                    solver="PyPSA/HiGHS",
                    task_kind="DC_SCOPF",
                    state_id=f"load-{float(row['load_scale']):.4f}",
                    transform_class="harmful",
                    attack_family="contingency_candidate_omission",
                    baseline="pcc_v2",
                    decision=str(row["gate_decision"]),
                    solver_status=str(row["gate_solver_status"]),
                    solver_started=bool(row["harmful_solver_starts"]),
                    source_hash=str(row["source_hash"]),
                    target_hash=str(row["target_hash"]),
                    certificate_hash=str(row["certificate_hash"]),
                    consequence_observed=bool(row["false_secure_dispatch"]),
                    unsafe_result_prevented=bool(row["unsafe_result_prevented"]),
                    reasons=tuple(str(row["gate_reasons"]).split(";")),
                    verification_us=float(row["gate_verification_us"]),
                    metrics={
                        "candidate_count": int(row["candidate_count"]),
                        "pre_contingency_loading_pu": float(row["pre_contingency_loading_pu"]),
                        "full_post_contingency_max_loading_pu": float(row["full_post_contingency_max_loading_pu"]),
                        "alias_post_contingency_max_loading_pu": float(row["alias_post_contingency_max_loading_pu"]),
                        "full_load_shed_mw": float(row["full_load_shed_mw"]),
                        "alias_load_shed_mw": float(row["alias_load_shed_mw"]),
                        "relative_cost_understatement": float(row["relative_cost_understatement"]),
                    },
                ).to_dict()
            )
        with (output / f"dc_scopf_gate_{run_id}_evidence.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(evidence[0]))
            writer.writeheader()
            writer.writerows(evidence)
    consequential = [row for row in rows if row["false_secure_dispatch"]]
    summary = {
        "experiment": "pcc_v2_native_pypsa_highs_dc_scopf_gate",
        "result_schema": RESULT_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "loader_revision": LOADER_REVISION,
        "branch_components": ["Line", "Transformer"],
        "pypsa_version": pypsa.__version__,
        "highs_version": importlib.metadata.version("highspy"),
        "environment_id": ENVIRONMENT_ID,
        "cases_requested": args.cases,
        "states_per_case_requested": args.states,
        "state_offset": args.state_offset,
        "candidate_mode": args.candidate_mode,
        "rows": len(rows),
        "requested_state_denominator": len(args.cases) * args.states,
        "completed_state_denominator": len(args.cases) * args.states - len(failures),
        "failed_states": len(failures),
        "false_secure_dispatches": len(consequential),
        "harmful_solver_starts": sum(row["harmful_solver_starts"] for row in rows),
        "unsafe_results_prevented": sum(row["unsafe_result_prevented"] for row in rows),
        "prevention_rate_among_false_secure": (
            sum(row["unsafe_result_prevented"] for row in rows) / len(consequential)
            if consequential else None
        ),
        "failures": failures,
        "scope": "linear SCOPF with non-islanding line and transformer candidates and post-contingency LPF",
    }
    (output / f"dc_scopf_gate_{run_id}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
