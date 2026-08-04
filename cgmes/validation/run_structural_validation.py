from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
from rdflib import Graph, Literal, RDF, URIRef


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
BOUNDARY = BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_Boundary_v3.zip"
CASES = {
    "cgmes24_minigrid_t1": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip",
    "cgmes24_minigrid_t2": BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip",
}
EXPORTS = ROOT / "results" / "roundtrip_exports"


def local_name(term: object) -> str:
    text = str(term)
    return text.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def parse_archives(paths: Iterable[Path]) -> tuple[Graph, int, list[str]]:
    graph = Graph()
    xml_count = 0
    errors: list[str] = []
    for path in paths:
        try:
            with zipfile.ZipFile(path) as archive:
                for entry in sorted(archive.namelist()):
                    if not entry.lower().endswith((".xml", ".rdf")):
                        continue
                    xml_count += 1
                    try:
                        graph.parse(data=archive.read(entry), format="xml")
                    except Exception as exc:
                        errors.append(f"{path.name}:{entry}:{type(exc).__name__}:{exc}")
        except Exception as exc:
            errors.append(f"{path.name}:archive:{type(exc).__name__}:{exc}")
    return graph, xml_count, errors


def subjects_of_type(graph: Graph, type_name: str) -> set[URIRef]:
    return {subject for subject, _, value in graph.triples((None, RDF.type, None)) if local_name(value) == type_name}


def predicate_values(graph: Graph, subject: URIRef, predicate_name: str) -> list[object]:
    return [value for _, predicate, value in graph.triples((subject, None, None)) if local_name(predicate) == predicate_name]


def validate(case_id: str, artifact_kind: str, path: Path) -> dict[str, object]:
    graph, xml_count, parse_errors = parse_archives([path, BOUNDARY])
    base_voltages = subjects_of_type(graph, "BaseVoltage")
    base_voltage_missing = [
        str(subject)
        for subject in base_voltages
        if not predicate_values(graph, subject, "BaseVoltage.nominalVoltage")
    ]
    terminals = subjects_of_type(graph, "Terminal")
    terminal_missing_equipment = [
        str(subject)
        for subject in terminals
        if not predicate_values(graph, subject, "Terminal.ConductingEquipment")
    ]
    busbar_sections = subjects_of_type(graph, "BusbarSection")
    busbar_missing_container = [
        str(subject)
        for subject in busbar_sections
        if not predicate_values(graph, subject, "Equipment.EquipmentContainer")
    ]
    mrids: dict[str, list[str]] = {}
    for subject, predicate, value in graph:
        if local_name(predicate) == "IdentifiedObject.mRID" and isinstance(value, Literal):
            mrids.setdefault(str(value), []).append(str(subject))
    duplicate_mrids = {key: values for key, values in mrids.items() if len(set(values)) > 1}
    return {
        "case_id": case_id,
        "artifact_kind": artifact_kind,
        "artifact_path": path.relative_to(ROOT).as_posix(),
        "xml_file_count_with_boundary": xml_count,
        "rdf_triple_count": len(graph),
        "rdf_parse_valid": not parse_errors,
        "rdf_parse_error_count": len(parse_errors),
        "base_voltage_count": len(base_voltages),
        "base_voltage_missing_nominal_count": len(base_voltage_missing),
        "base_voltage_nominal_valid": not base_voltage_missing,
        "terminal_count": len(terminals),
        "terminal_missing_equipment_count": len(terminal_missing_equipment),
        "terminal_equipment_reference_present": not terminal_missing_equipment,
        "busbar_section_count": len(busbar_sections),
        "busbar_missing_container_count": len(busbar_missing_container),
        "busbar_container_valid": not busbar_missing_container,
        "busbar_container_requirement": "diagnostic_only_official_rdfs_multiplicity_0_to_1",
        "duplicate_mrid_count": len(duplicate_mrids),
        "mrid_unique_valid": not duplicate_mrids,
        "official_shacl_status": "not_run_no_version_matched_cgmes_2_4_grid_shapes_in_local_package",
        "official_shacl_valid": None,
        "structural_gate_valid": not parse_errors and not base_voltage_missing and not terminal_missing_equipment and not duplicate_mrids,
        "details_json": json.dumps(
            {
                "parse_errors": parse_errors,
                "base_voltage_missing_nominal": base_voltage_missing,
                "terminal_missing_equipment": terminal_missing_equipment,
                "busbar_missing_container": busbar_missing_container,
                "duplicate_mrids": duplicate_mrids,
            },
            ensure_ascii=False,
        ),
    }


def main() -> None:
    rows: list[dict[str, object]] = []
    for case_id, source in CASES.items():
        rows.append(validate(case_id, "official_source", source))
        export = EXPORTS / f"{case_id}__veragrid_roundtrip.zip"
        if export.is_file():
            rows.append(validate(case_id, "veragrid_roundtrip_export", export))
        pypowsybl_export = EXPORTS / f"{case_id}__pypowsybl_roundtrip.zip"
        if pypowsybl_export.is_file():
            rows.append(validate(case_id, "pypowsybl_roundtrip_export", pypowsybl_export))
    result = pd.DataFrame(rows)
    result.to_csv(ROOT / "results" / "cgmes_structural_validation_results.csv", index=False)
    summary = {
        "artifacts": len(result),
        "structural_gate_passes": int(result["structural_gate_valid"].sum()),
        "structural_gate_failures": int((~result["structural_gate_valid"]).sum()),
        "official_shacl_executed": False,
        "scope_note": "The local official CGMES 3.0 SHACL shapes are not version-compatible with these CGMES 2.4.15 development models. The reported structural gate is an explicit local check, not an official SHACL result. Boundary data are included consistently. BusbarSection container absence is diagnostic only because the matched ENTSO-E 2.4.15 RDFS declares Equipment.EquipmentContainer multiplicity 0..1; pypowsybl nevertheless rejects the VeraGrid exports on this condition.",
    }
    (ROOT / "results" / "cgmes_structural_validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(result.drop(columns=["details_json"]).to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
