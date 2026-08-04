from __future__ import annotations

import contextlib
import cmath
import csv
import io
import json
import math
import sys
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandapower as pandapower
import pypowsybl as pypowsybl
from pandapower.converter.cim.cim2pp.from_cim import from_cim


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import canonical_id, sha256  # noqa: E402

from VeraGridEngine.IO.file_open import FileOpen, FileOpenOptions  # noqa: E402
from VeraGridEngine.Simulations.PowerFlow.power_flow_options import PowerFlowOptions  # noqa: E402
from VeraGridEngine.api import power_flow as veragrid_power_flow  # noqa: E402
from VeraGridEngine.enumerations import CGMESVersions, FileType, SolverType  # noqa: E402


SOURCE_BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
CASES = {
    "cgmes24_minigrid_t1": {
        "source": SOURCE_BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip",
        "veragrid_roundtrip": ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t1__veragrid_roundtrip_with_boundary.zip",
        "pypowsybl_roundtrip": ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t1__pypowsybl_roundtrip.zip",
    },
    "cgmes24_minigrid_t2": {
        "source": SOURCE_BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip",
        "veragrid_roundtrip": ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t2__veragrid_roundtrip_with_boundary.zip",
        "pypowsybl_roundtrip": ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t2__pypowsybl_roundtrip.zip",
    },
}
TOOLS = ("pandapower", "pypowsybl", "veragrid")
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def _finite_values(values: Any) -> list[float]:
    answer: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            answer.append(number)
    return answer


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


def _run_pandapower(path: Path) -> tuple[dict[str, object], list[str]]:
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        network = from_cim(
            str(path),
            cgmes_version="2.4.15",
            ignore_errors=False,
            run_powerflow=False,
            use_sv_data_for_assets=False,
        )
        imported_counts = {
            name: len(getattr(network, name))
            for name in ("bus", "line", "trafo", "trafo3w", "load", "gen", "sgen", "ext_grid")
        }
        pandapower.runpp(network, calculate_voltage_angles=True, init="auto")
    voltages = _finite_values(network.res_bus.vm_pu.tolist()) if network.converged else []
    return (
        {
            "imported_counts": imported_counts,
            "component_count": 1,
            "component_statuses": ["CONVERGED" if network.converged else "NOT_CONVERGED"],
            "solver_status_text": "pandapower.runpp returned",
            "converged": bool(network.converged),
            "iteration_count": int(network._ppc.get("iterations", -1)) if network.converged else 0,
            "finite_voltage_count": len(voltages),
            "voltage_min_pu": min(voltages) if voltages else "",
            "voltage_max_pu": max(voltages) if voltages else "",
        },
        [line for line in capture.getvalue().splitlines() if line.strip()],
    )


def _run_pypowsybl(path: Path) -> tuple[dict[str, object], list[str]]:
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        network = pypowsybl.network.load(str(path))
        imported_counts = {
            "bus": len(network.get_buses()),
            "line": len(network.get_lines()),
            "load": len(network.get_loads()),
            "generator": len(network.get_generators()),
            "transformer_2w": len(network.get_2_windings_transformers()),
            "transformer_3w": len(network.get_3_windings_transformers()),
        }
        components = pypowsybl.loadflow.run_ac(network)
    statuses = [component.status.name for component in components]
    converged = bool(components) and all(status == "CONVERGED" for status in statuses)
    status_text = " | ".join(component.status_text for component in components)
    iterations = sum(int(component.iteration_count) for component in components)
    buses = network.get_buses()
    voltage_column = "v" if "v" in buses.columns else "voltage"
    voltages = _finite_values(buses[voltage_column].tolist()) if voltage_column in buses.columns else []
    return (
        {
            "imported_counts": imported_counts,
            "component_count": len(components),
            "component_statuses": statuses,
            "solver_status_text": status_text,
            "converged": converged,
            "iteration_count": iterations,
            "finite_voltage_count": len(voltages),
            "voltage_min_pu": "",
            "voltage_max_pu": "",
        },
        [line for line in capture.getvalue().splitlines() if line.strip()],
    )


def _run_veragrid(path: Path) -> tuple[dict[str, object], list[str]]:
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        circuit = FileOpen(
            str(path),
            options=FileOpenOptions(
                file_type=FileType.CGMES,
                cgmes_version=CGMESVersions.v2_4_15,
            ),
        ).open()
        if circuit is None:
            raise RuntimeError("VeraGrid returned no circuit")
        result = veragrid_power_flow(
            circuit,
            PowerFlowOptions(solver_type=SolverType.NR),
        )
    voltages = list(result.voltage)
    finite_magnitudes = _finite_values(abs(value) for value in voltages)
    aliases = _connectivity_to_topological_aliases(path)
    solution: dict[str, dict[str, float]] = {}
    alias_collisions = 0
    for bus, voltage in zip(circuit.buses, voltages):
        if not math.isfinite(float(abs(voltage))):
            continue
        raw_id = canonical_id(bus.idtag)
        aligned_id = aliases.get(raw_id, raw_id)
        if aligned_id in solution:
            alias_collisions += 1
            continue
        solution[aligned_id] = {
            "vm_pu": float(abs(voltage)),
            "va_degree": float(math.degrees(cmath.phase(voltage))),
        }
    return (
        {
            "imported_counts": {
                "bus": len(circuit.buses),
                "branch": len(circuit.get_branches()),
            },
            "component_count": len(result.convergence_reports),
            "component_statuses": ["CONVERGED" if bool(result.converged) else "NOT_CONVERGED"],
            "solver_status_text": f"VeraGrid NR error={float(result.error):.12g}",
            "converged": bool(result.converged),
            "iteration_count": int(result.iterations),
            "finite_voltage_count": len(finite_magnitudes),
            "voltage_min_pu": min(finite_magnitudes) if finite_magnitudes else "",
            "voltage_max_pu": max(finite_magnitudes) if finite_magnitudes else "",
            "bus_solution": solution,
            "topology_alias_count": sum(canonical_id(bus.idtag) in aliases for bus in circuit.buses),
            "topology_alias_collision_count": alias_collisions,
        },
        [line for line in capture.getvalue().splitlines() if line.strip()],
    )


RUNNERS = {
    "pandapower": _run_pandapower,
    "pypowsybl": _run_pypowsybl,
    "veragrid": _run_veragrid,
}


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    rows: list[dict[str, object]] = []
    solutions: dict[tuple[str, str, str], dict[str, dict[str, float]]] = {}
    for case_id, artifacts in CASES.items():
        for artifact_role, path in artifacts.items():
            if not path.is_file():
                raise SystemExit(f"Missing preregistered artifact: {path}")
            for tool in TOOLS:
                started_at = datetime.now(timezone.utc).isoformat()
                started = time.perf_counter()
                outcome = "solver_error"
                error_stage = ""
                error_type = ""
                error_message = ""
                details: dict[str, object] = {}
                messages: list[str] = []
                try:
                    details, messages = RUNNERS[tool](path)
                    outcome = "converged" if details["converged"] else "not_converged"
                    solutions[(case_id, artifact_role, tool)] = details.get("bus_solution", {})  # type: ignore[assignment]
                except Exception as exc:  # every case/tool/artifact remains in the denominator
                    error_type = type(exc).__name__
                    error_message = str(exc)
                    trace = traceback.format_exc()
                    messages.append(trace)
                    lower_trace = trace.lower()
                    error_stage = "import" if "network.load" in lower_trace or "from_cim" in lower_trace else "solve"
                    outcome = f"{error_stage}_error"
                row: dict[str, object] = {
                    "case_id": case_id,
                    "artifact_role": artifact_role,
                    "tool": tool,
                    "outcome": outcome,
                    "converged": bool(details.get("converged", False)),
                    "source_path": path.relative_to(ROOT).as_posix(),
                    "source_sha256": sha256(path),
                    "elapsed_seconds": time.perf_counter() - started,
                    "component_count": details.get("component_count", 0),
                    "component_statuses": json.dumps(details.get("component_statuses", [])),
                    "solver_status_text": details.get("solver_status_text", ""),
                    "iteration_count": details.get("iteration_count", 0),
                    "finite_voltage_count": details.get("finite_voltage_count", 0),
                    "voltage_min_pu": details.get("voltage_min_pu", ""),
                    "voltage_max_pu": details.get("voltage_max_pu", ""),
                    "error_stage": error_stage,
                    "error_type": error_type,
                    "error_message": error_message,
                }
                log_path = LOGS / f"powerflow__{case_id}__{artifact_role}__{tool}.json"
                log_path.write_text(
                    json.dumps(
                        {
                            **row,
                            "started_utc": started_at,
                            "imported_counts": details.get("imported_counts", {}),
                            "bus_solution": details.get("bus_solution", {}),
                            "topology_alias_count": details.get("topology_alias_count", 0),
                            "topology_alias_collision_count": details.get("topology_alias_collision_count", 0),
                            "messages": messages,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                row["log_path"] = log_path.relative_to(ROOT).as_posix()
                rows.append(row)
                print(case_id, artifact_role, tool, outcome)

    output = RESULTS / "minimum_roundtrip_powerflow_results.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    paired_valid = 0
    paired_denominator = 0
    pair_rows: list[dict[str, object]] = []
    for case_id in CASES:
        for tool in TOOLS:
            source_row = next(
                row for row in rows
                if row["case_id"] == case_id and row["tool"] == tool and row["artifact_role"] == "source"
            )
            for target_role in ("veragrid_roundtrip", "pypowsybl_roundtrip"):
                target_row = next(
                    row for row in rows
                    if row["case_id"] == case_id and row["tool"] == tool and row["artifact_role"] == target_role
                )
                paired_denominator += 1
                is_valid = bool(source_row["converged"]) and bool(target_row["converged"])
                paired_valid += int(is_valid)
                source_solution = solutions.get((case_id, "source", tool), {})
                target_solution = solutions.get((case_id, target_role, tool), {})
                common_ids = sorted(set(source_solution) & set(target_solution))
                vm_deltas = [
                    abs(source_solution[bus_id]["vm_pu"] - target_solution[bus_id]["vm_pu"])
                    for bus_id in common_ids
                ]
                va_deltas = [
                    abs(source_solution[bus_id]["va_degree"] - target_solution[bus_id]["va_degree"])
                    for bus_id in common_ids
                ]
                pair_rows.append(
                    {
                        "case_id": case_id,
                        "target_role": target_role,
                        "tool": tool,
                        "paired_valid": is_valid,
                        "raw_source_fidelity_for_gate1_anomaly": tool != "veragrid",
                        "gate3_eligible": is_valid and tool != "veragrid",
                        "source_bus_count": len(source_solution),
                        "target_bus_count": len(target_solution),
                        "aligned_bus_count": len(common_ids),
                        "source_only_bus_count": len(set(source_solution) - set(target_solution)),
                        "target_only_bus_count": len(set(target_solution) - set(source_solution)),
                        "max_abs_vm_delta_pu": max(vm_deltas) if is_valid and vm_deltas else "",
                        "max_abs_va_delta_degree": max(va_deltas) if is_valid and va_deltas else "",
                    }
                )
    with (RESULTS / "minimum_roundtrip_powerflow_pair_comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pair_rows[0]))
        writer.writeheader()
        writer.writerows(pair_rows)
    outcomes = {name: sum(row["outcome"] == name for row in rows) for name in sorted({str(row["outcome"]) for row in rows})}
    summary = {
        "attempts": len(rows),
        "converged_runs": sum(bool(row["converged"]) for row in rows),
        "paired_denominator": paired_denominator,
        "paired_valid": paired_valid,
        "gate3_eligible_pairs": sum(bool(row["gate3_eligible"]) for row in pair_rows),
        "paired_valid_by_tool": {
            tool: sum(row["tool"] == tool and bool(row["paired_valid"]) for row in pair_rows)
            for tool in TOOLS
        },
        "outcomes": outcomes,
        "gate_downstream_replay_ready": paired_valid > 0,
        "gate3_evidence_ready": any(bool(row["gate3_eligible"]) for row in pair_rows),
        "interpretation": "Import success is not convergence; no failed or non-converged run is removed. The converged VeraGrid source arm is a post-import representation that already omits the Gate-1 L3_a asset, so its near-zero round-trip deltas do not establish raw-source conservation or Gate 3.",
    }
    (RESULTS / "minimum_roundtrip_powerflow_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
