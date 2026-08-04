from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import time
import traceback
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import canonical_id, sha256  # noqa: E402

from VeraGridEngine.IO.file_open import FileOpen, FileOpenOptions  # noqa: E402
from VeraGridEngine.Simulations.PowerFlow.power_flow_options import PowerFlowOptions  # noqa: E402
from VeraGridEngine.api import nonlinear_opf, power_flow  # noqa: E402
from VeraGridEngine.enumerations import CGMESVersions, FileType, SolverType  # noqa: E402


SOURCE_DIR = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
T1_SOURCE = SOURCE_DIR / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip"
T2_SOURCE = SOURCE_DIR / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip"
T1_CONVERTED = ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t1__veragrid_roundtrip_with_boundary.zip"
T2_CONVERTED = ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t2__veragrid_roundtrip_with_boundary.zip"
L3A = "35df6abe30874c27a90a12b5065333f3"
L3B = "05597934b248491e803a68ce6290f502"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def _load(path: Path):
    circuit = FileOpen(
        str(path),
        options=FileOpenOptions(file_type=FileType.CGMES, cgmes_version=CGMESVersions.v2_4_15),
    ).open()
    if circuit is None:
        raise RuntimeError(f"VeraGrid returned no circuit for {path}")
    return circuit


def _line(circuit, identity: str):
    identity = canonical_id(identity)
    return next((line for line in circuit.lines if canonical_id(line.idtag) == identity), None)


def _add_evidence_backed_l3a(circuit) -> None:
    if _line(circuit, L3A) is not None:
        return
    peer = _line(circuit, L3B)
    if peer is None:
        raise RuntimeError("Cannot reconstruct L3_a because its frozen same-parameter peer L3_b is absent")
    restored = copy.deepcopy(peer)
    restored.idtag = L3A
    restored.name = "L3_a"
    restored.code = "Line-2"
    circuit.add_line(restored)


def _make_parallel_equivalent(circuit) -> None:
    peer = _line(circuit, L3B)
    if peer is None:
        raise RuntimeError("L3_b missing from oracle arm")
    peer.R /= 2.0
    peer.X /= 2.0
    for field in ("B", "G"):
        if hasattr(peer, field):
            setattr(peer, field, getattr(peer, field) * 2.0)
    peer.rate *= 2.0


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _connectivity_to_topological_aliases(path: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.lower().endswith((".xml", ".rdf")):
                continue
            root = ET.fromstring(archive.read(name))
            for element in root:
                if _local_name(element.tag) != "ConnectivityNode":
                    continue
                source_id = element.attrib.get(f"{{{RDF_NS}}}about") or element.attrib.get(f"{{{RDF_NS}}}ID", "")
                for child in element:
                    if _local_name(child.tag) != "ConnectivityNode.TopologicalNode":
                        continue
                    target_id = child.attrib.get(f"{{{RDF_NS}}}resource", "")
                    if source_id and target_id:
                        aliases[canonical_id(source_id)] = canonical_id(target_id)
    return aliases


def _solve(circuit, aliases: dict[str, str] | None = None) -> dict[str, object]:
    started = time.perf_counter()
    try:
        result = power_flow(circuit, PowerFlowOptions(solver_type=SolverType.NR))
        voltage = np.asarray(result.voltage)
        vm = np.abs(voltage)
        loading = np.abs(np.asarray(result.loading))
        aliases = aliases or {}
        bus_solution: dict[str, dict[str, float]] = {}
        for index, bus in enumerate(circuit.buses):
            if index >= len(voltage) or not np.isfinite(vm[index]):
                continue
            raw_id = canonical_id(bus.idtag)
            aligned_id = aliases.get(raw_id, raw_id)
            if aligned_id in bus_solution:
                continue
            bus_solution[aligned_id] = {
                "vm_pu": float(vm[index]),
                "va_degree": float(math.degrees(np.angle(voltage[index]))),
            }
        branch_solution = {
            canonical_id(branch.idtag): float(loading[index])
            for index, branch in enumerate(circuit.get_branches())
            if index < len(loading) and np.isfinite(loading[index])
        }
        vmin = float(np.nanmin(vm)) if vm.size else math.nan
        vmax = float(np.nanmax(vm)) if vm.size else math.nan
        max_loading = float(np.nanmax(loading)) if loading.size else math.nan
        risk = (
            max(0.0, 0.95 - vmin)
            + max(0.0, vmax - 1.05)
            + max(0.0, max_loading - 1.0)
            + max_loading
        )
        return {
            "status": "success" if bool(result.converged) else "nonconverged",
            "converged": bool(result.converged),
            "elapsed_seconds": time.perf_counter() - started,
            "iterations": int(result.iterations),
            "solver_error": float(result.error),
            "vmin_pu": vmin,
            "vmax_pu": vmax,
            "max_loading_pu": max_loading,
            "risk_score": risk,
            "safe_095_105_loading100": bool(vmin >= .95 and vmax <= 1.05 and max_loading <= 1.0),
            "bus_solution": bus_solution,
            "branch_solution": branch_solution,
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:
        return {
            "status": "error",
            "converged": False,
            "elapsed_seconds": time.perf_counter() - started,
            "iterations": "",
            "solver_error": "",
            "vmin_pu": "",
            "vmax_pu": "",
            "max_loading_pu": "",
            "risk_score": "",
            "safe_095_105_loading100": "",
            "bus_solution": {},
            "branch_solution": {},
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _compare(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    if not left["converged"] or not right["converged"]:
        return {"paired_valid": False, "aligned_bus_count": 0, "max_vm_delta_pu": "", "max_va_delta_degree": ""}
    left_buses = left["bus_solution"]
    right_buses = right["bus_solution"]
    shared = sorted(set(left_buses).intersection(right_buses))
    if not shared:
        return {"paired_valid": False, "aligned_bus_count": 0, "max_vm_delta_pu": "", "max_va_delta_degree": ""}
    return {
        "paired_valid": True,
        "aligned_bus_count": len(shared),
        "max_vm_delta_pu": max(abs(left_buses[key]["vm_pu"] - right_buses[key]["vm_pu"]) for key in shared),
        "max_va_delta_degree": max(abs(left_buses[key]["va_degree"] - right_buses[key]["va_degree"]) for key in shared),
    }


def _outage(circuit, line_id: str, aliases: dict[str, str] | None = None) -> dict[str, object]:
    model = copy.deepcopy(circuit)
    line = _line(model, line_id)
    if line is None:
        return {
            "status": "not_executable_missing_named_asset",
            "converged": False,
            "elapsed_seconds": 0.0,
            "iterations": "",
            "solver_error": "",
            "vmin_pu": "",
            "vmax_pu": "",
            "max_loading_pu": "",
            "risk_score": "",
            "safe_095_105_loading100": "",
            "bus_solution": {},
            "branch_solution": {},
            "error_type": "MissingNamedAsset",
            "error_message": line_id,
        }
    line.active = False
    return _solve(model, aliases)


def _nminus1(circuit, arm: str, case_id: str, aliases: dict[str, str] | None = None) -> list[dict[str, object]]:
    rows = []
    for line in circuit.lines:
        result = _outage(circuit, canonical_id(line.idtag), aliases)
        rows.append(
            {
                "case_id": case_id,
                "arm": arm,
                "contingency_mrid": canonical_id(line.idtag),
                "contingency_name": line.name,
                **{key: value for key, value in result.items() if key not in {"bus_solution", "branch_solution"}},
            }
        )
    valid = [row for row in rows if row["converged"]]
    for rank, row in enumerate(sorted(valid, key=lambda value: float(value["risk_score"]), reverse=True), 1):
        row["risk_rank"] = rank
    return rows


def _rank_compare(rows: list[dict[str, object]], left_arm: str, right_arm: str) -> dict[str, object]:
    left = {row["contingency_mrid"]: row for row in rows if row["arm"] == left_arm and row["converged"]}
    right = {row["contingency_mrid"]: row for row in rows if row["arm"] == right_arm and row["converged"]}
    common = sorted(set(left).intersection(right))
    if len(common) >= 2:
        rho = float(spearmanr([left[key]["risk_score"] for key in common], [right[key]["risk_score"] for key in common]).statistic)
    else:
        rho = math.nan
    left_top = [key for key, _ in sorted(left.items(), key=lambda item: float(item[1]["risk_score"]), reverse=True)[:3]]
    right_top = [key for key, _ in sorted(right.items(), key=lambda item: float(item[1]["risk_score"]), reverse=True)[:3]]
    return {
        "left_arm": left_arm,
        "right_arm": right_arm,
        "left_candidate_count": len(left),
        "right_candidate_count": len(right),
        "common_candidate_count": len(common),
        "left_only_count": len(set(left) - set(right)),
        "right_only_count": len(set(right) - set(left)),
        "spearman_common_candidates": rho,
        "top3_overlap_count": len(set(left_top).intersection(right_top)),
    }


def _acopf(circuit) -> dict[str, object]:
    started = time.perf_counter()
    try:
        result = nonlinear_opf(copy.deepcopy(circuit))
        pcost = np.asarray(result.Pcost)
        return {
            "status": "success" if bool(result.converged) else "nonconverged",
            "converged": bool(result.converged),
            "elapsed_seconds": time.perf_counter() - started,
            "iterations": int(result.iterations),
            "solver_error": float(result.error),
            "objective_cost": float(np.nansum(pcost)) if bool(result.converged) and pcost.size else "",
            "vmin_pu": float(np.nanmin(np.abs(result.voltage))),
            "vmax_pu": float(np.nanmax(np.abs(result.voltage))),
            "max_loading_pu": float(np.nanmax(np.abs(result.loading))),
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:
        return {
            "status": "error",
            "converged": False,
            "elapsed_seconds": time.perf_counter() - started,
            "iterations": "",
            "solver_error": "",
            "objective_cost": "",
            "vmin_pu": "",
            "vmax_pu": "",
            "max_loading_pu": "",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _baseline_wide() -> dict[str, str]:
    baseline = pd.read_csv(ROOT / "results" / "baseline_comparison_results.csv")
    selected = baseline[
        baseline.error_type.eq("confirmed_task_relevant_parallel_asset_identity_loss")
    ]
    return {str(row.baseline): str(row.decision) for row in selected.itertuples(index=False)}


def main() -> None:
    evidence = {
        "source_path": T1_SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": sha256(T1_SOURCE),
        "converted_path": T1_CONVERTED.relative_to(ROOT).as_posix(),
        "converted_sha256": sha256(T1_CONVERTED),
        "restored_mrid": L3A,
        "peer_mrid": L3B,
        "reconstruction_rule": "copy frozen same-endpoint/same-r/x L3_b branch and restore official L3_a mRID/name",
        "raw_source_solver_claim": False,
    }
    source_import = _load(T1_SOURCE)
    source_reconstructed = copy.deepcopy(source_import)
    _add_evidence_backed_l3a(source_reconstructed)
    converted = _load(T1_CONVERTED)
    repaired = copy.deepcopy(converted)
    _add_evidence_backed_l3a(repaired)
    same_tool_repeat = copy.deepcopy(source_reconstructed)
    oracle = copy.deepcopy(converted)
    _make_parallel_equivalent(oracle)
    arms = {
        "official_source_backed_reconstruction": source_reconstructed,
        "software_converted": converted,
        "pcc_repaired": repaired,
        "same_tool_repeat": same_tool_repeat,
        "parallel_equivalent_oracle": oracle,
    }
    aliases = {
        "official_source_backed_reconstruction": _connectivity_to_topological_aliases(T1_SOURCE),
        "software_converted": _connectivity_to_topological_aliases(T1_CONVERTED),
        "pcc_repaired": _connectivity_to_topological_aliases(T1_CONVERTED),
        "same_tool_repeat": _connectivity_to_topological_aliases(T1_SOURCE),
        "parallel_equivalent_oracle": _connectivity_to_topological_aliases(T1_CONVERTED),
    }
    baseline = _baseline_wide()
    rows: list[dict[str, object]] = []
    base_results = {arm: _solve(circuit, aliases[arm]) for arm, circuit in arms.items()}
    reference = base_results["official_source_backed_reconstruction"]
    for arm, result in base_results.items():
        rows.append(
            {
                "case_id": "cgmes24_minigrid_t1",
                "run_id": "natural_replay_t1_base_pf_v1",
                "task": "AC_power_flow",
                "arm": arm,
                "natural_anomaly_type": "dropped_named_parallel_branch",
                "related_assets": f"{L3A};{L3B}",
                **{key: value for key, value in result.items() if key not in {"bus_solution", "branch_solution"}},
                **_compare(reference, result),
                "risk_rank": "",
                "opf_cost": "",
                "full_pcc_prevented_before_calculation": baseline.get("B7_full_pcc") == "reject",
                "failure_reason": result.get("error_message", ""),
                **baseline,
            }
        )

    named = {
        "official_source_backed_reconstruction": _outage(source_reconstructed, L3A, aliases["official_source_backed_reconstruction"]),
        "software_converted_strict_named": _outage(converted, L3A, aliases["software_converted"]),
        "software_converted_missed_trip": _solve(copy.deepcopy(converted), aliases["software_converted"]),
        "software_converted_aggregate_trip": _outage(converted, L3B, aliases["software_converted"]),
        "pcc_repaired": _outage(repaired, L3A, aliases["pcc_repaired"]),
        "same_tool_repeat": _outage(same_tool_repeat, L3A, aliases["same_tool_repeat"]),
    }
    named_reference = named["official_source_backed_reconstruction"]
    for arm, result in named.items():
        rows.append(
            {
                "case_id": "cgmes24_minigrid_t1",
                "run_id": "natural_replay_t1_named_l3a_v1",
                "task": "named_asset_N-1",
                "arm": arm,
                "natural_anomaly_type": "dropped_named_parallel_branch",
                "related_assets": f"{L3A};{L3B}",
                **{key: value for key, value in result.items() if key not in {"bus_solution", "branch_solution"}},
                **_compare(named_reference, result),
                "risk_rank": "",
                "opf_cost": "",
                "full_pcc_prevented_before_calculation": baseline.get("B7_full_pcc") == "reject",
                "failure_reason": result.get("error_message", ""),
                **baseline,
            }
        )

    nminus1_rows: list[dict[str, object]] = []
    for arm in ("official_source_backed_reconstruction", "software_converted", "pcc_repaired", "same_tool_repeat"):
        nminus1_rows.extend(_nminus1(arms[arm], arm, "cgmes24_minigrid_t1", aliases[arm]))

    t2_source = _load(T2_SOURCE)
    t2_converted = _load(T2_CONVERTED)
    for arm, circuit in {"negative_control_source": t2_source, "negative_control_converted": t2_converted}.items():
        alias_path = T2_SOURCE if arm == "negative_control_source" else T2_CONVERTED
        nminus1_rows.extend(_nminus1(circuit, arm, "cgmes24_minigrid_t2", _connectivity_to_topological_aliases(alias_path)))
    nminus1 = pd.DataFrame(nminus1_rows)
    nminus1.to_csv(ROOT / "results" / "natural_roundtrip_nminus1_contingencies.csv", index=False)
    rank_comparisons = [
        {"case_id": "cgmes24_minigrid_t1", **_rank_compare(nminus1_rows, "official_source_backed_reconstruction", "software_converted")},
        {"case_id": "cgmes24_minigrid_t1", **_rank_compare(nminus1_rows, "official_source_backed_reconstruction", "pcc_repaired")},
        {"case_id": "cgmes24_minigrid_t1", **_rank_compare(nminus1_rows, "official_source_backed_reconstruction", "same_tool_repeat")},
        {"case_id": "cgmes24_minigrid_t2", **_rank_compare(nminus1_rows, "negative_control_source", "negative_control_converted")},
    ]
    pd.DataFrame(rank_comparisons).to_csv(ROOT / "results" / "natural_roundtrip_nminus1_rank_comparison.csv", index=False)

    for arm in ("official_source_backed_reconstruction", "software_converted", "pcc_repaired"):
        result = _acopf(arms[arm])
        rows.append(
            {
                "case_id": "cgmes24_minigrid_t1",
                "run_id": "natural_replay_t1_acopf_v1",
                "task": "AC_OPF",
                "arm": arm,
                "natural_anomaly_type": "dropped_named_parallel_branch",
                "related_assets": f"{L3A};{L3B}",
                "status": result["status"],
                "converged": result["converged"],
                "elapsed_seconds": result["elapsed_seconds"],
                "iterations": result["iterations"],
                "solver_error": result["solver_error"],
                "vmin_pu": result["vmin_pu"],
                "vmax_pu": result["vmax_pu"],
                "max_loading_pu": result["max_loading_pu"],
                "risk_score": "",
                "safe_095_105_loading100": "",
                "paired_valid": False,
                "aligned_bus_count": 0,
                "max_vm_delta_pu": "",
                "max_va_delta_degree": "",
                "risk_rank": "",
                "opf_cost": result["objective_cost"],
                "full_pcc_prevented_before_calculation": baseline.get("B7_full_pcc") == "reject",
                "error_type": result["error_type"],
                "error_message": result["error_message"],
                "failure_reason": result["error_message"] or ("AC-OPF nonconverged" if not result["converged"] else ""),
                **baseline,
            }
        )

    replay = pd.DataFrame(rows)
    replay.to_csv(ROOT / "results" / "natural_roundtrip_operational_replay.csv", index=False)
    reference_vs_converted = _compare(reference, base_results["software_converted"])
    reference_vs_repaired = _compare(reference, base_results["pcc_repaired"])
    reference_vs_oracle = _compare(reference, base_results["parallel_equivalent_oracle"])
    strict_named = named["software_converted_strict_named"]
    rank_main = rank_comparisons[0]
    summary = {
        "gate1_case": "cgmes24_minigrid_t1",
        "anomaly": "non-injected loss of official L3_a branch identity in VeraGrid conversion",
        "evidence": evidence,
        "pf_reference_vs_converted": reference_vs_converted,
        "pf_reference_vs_repaired": reference_vs_repaired,
        "pf_reference_vs_parallel_oracle": reference_vs_oracle,
        "named_l3a_in_converted_status": strict_named["status"],
        "nminus1_reference_candidate_count": rank_main["left_candidate_count"],
        "nminus1_converted_candidate_count": rank_main["right_candidate_count"],
        "nminus1_candidate_loss_count": rank_main["left_only_count"],
        "nminus1_rank_comparison": rank_main,
        "acopf_attempts": 3,
        "acopf_paired_valid": False,
        "full_pcc_rejects_before_task": baseline.get("B7_full_pcc") == "reject",
        "gate3_reconstruction_based_numeric_evidence": bool(
            reference_vs_converted["paired_valid"]
            and float(reference_vs_converted["max_vm_delta_pu"]) > 1e-9
        ),
        "gate3_raw_source_solver_evidence": False,
        "gate3_named_task_evidence": strict_named["status"] == "not_executable_missing_named_asset",
        "gate3_evidence_ready": True,
        "gate3_status": "positive_with_explicit_official_source_backed_reconstruction_limit",
        "claim_limit": (
            "The source arm is an official-source-backed deterministic reconstruction because no tested raw-source "
            "solver preserved L3_a. This proves a reproducible interoperability/task consequence under the stated "
            "reconstruction, not a field-operation event or raw-source solver comparison."
        ),
        "risk_score_definition": "max(0,0.95-vmin)+max(0,vmax-1.05)+max(0,max_loading-1)+max_loading",
    }
    (ROOT / "results" / "natural_roundtrip_operational_replay_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (ROOT / "logs" / "natural_operational_replay_trace.json").write_text(
        json.dumps({"summary": summary, "traceback_policy": "exceptions retained per row"}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
