from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from rdflib import Graph, Literal, RDF, URIRef


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "cgmes"
    / "corpus"
    / "extracted"
    / "cgmes24_testconfig"
    / "MicroGrid"
    / "BaseCase_BC"
    / "CGMES_v2.4.15_MicroGridTestConfiguration_BC_Assembled_v2.zip"
)
OUTPUT = ROOT / "outputs" / "qocdc_414_applicable_subset"
MD = "http://iec.ch/TC57/61970-552/ModelDescription/1#"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
FULL_MODEL = URIRef(MD + "FullModel")
MODEL_PROFILE = URIRef(MD + "Model.profile")
MODEL_CREATED = URIRef(MD + "Model.created")
MODEL_SCENARIO_TIME = URIRef(MD + "Model.scenarioTime")
MODEL_VERSION = URIRef(MD + "Model.version")
MODEL_MAS = URIRef(MD + "Model.modelingAuthoritySet")
MODEL_DEPENDENT_ON = URIRef(MD + "Model.DependentOn")
EXPECTED_SOURCE_SHA256 = "859e1b6af3d3fd7db4cf1e031c6f2675994367b3101d97fdb7448596e5c749f6"
IMPLEMENTED_LEVELS = {1, 2, 3, 4}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_name(term: object) -> str:
    return str(term).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def check(level: int, rule_id: str, passed: bool, observed: Any, scope: str) -> dict[str, Any]:
    return {
        "level": level,
        "rule_id": rule_id,
        "status": "PASS" if passed else "FAIL",
        "observed": observed,
        "scope": scope,
    }


def _is_igm(profiles: set[str]) -> bool:
    if not profiles:
        return False
    if any(marker in profile for profile in profiles for marker in ("DiagramLayout", "StateVariables")):
        return False
    return not any("Boundary" in profile for profile in profiles)


def validate_package(path: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    graphs: list[tuple[str, Graph]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            infos = archive.infolist()
            names = [info.filename for info in infos]
            xml_names = [name for name in names if name.lower().endswith((".xml", ".rdf"))]
            duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
            unsupported = sorted(
                name for name in names if not name.endswith("/") and not name.lower().endswith((".xml", ".rdf"))
            )
            checks.extend(
                [
                    check(1, "L1_archive_readable", bad_member is None, bad_member or "ok", "whole_package"),
                    check(1, "L1_xml_members_present", bool(xml_names), len(xml_names), "whole_package"),
                    check(1, "L1_duplicate_member_names_absent", not duplicates, duplicates, "whole_package"),
                    check(1, "L1_supported_member_extensions", not unsupported, unsupported, "whole_package"),
                ]
            )
            for name in sorted(xml_names):
                graph = Graph()
                try:
                    graph.parse(data=archive.read(name), format="xml")
                    graphs.append((name, graph))
                except Exception as exc:  # pragma: no cover - exercised by external malformed inputs
                    parse_errors.append(f"{name}:{type(exc).__name__}:{exc}")
    except Exception as exc:
        try:
            display_path = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            display_path = path.name
        return {
            "path": display_path,
            "checks": [check(1, "L1_archive_readable", False, f"{type(exc).__name__}:{exc}", "whole_package")],
            "passed": False,
        }

    checks.append(check(2, "L2_rdf_xml_parse", not parse_errors, parse_errors, "all_XML_members"))
    full_models: list[tuple[str, URIRef, Graph]] = []
    full_model_counts: dict[str, int] = {}
    for name, graph in graphs:
        models = list(graph.subjects(RDF.type, FULL_MODEL))
        full_model_counts[name] = len(models)
        if len(models) == 1 and isinstance(models[0], URIRef):
            full_models.append((name, models[0], graph))
    checks.append(
        check(
            2,
            "L2_one_FullModel_per_member",
            bool(graphs) and all(count == 1 for count in full_model_counts.values()),
            full_model_counts,
            "each_XML_member",
        )
    )
    model_ids = [str(model) for _, model, _ in full_models]
    duplicate_model_ids = sorted(model for model, count in Counter(model_ids).items() if count > 1)
    checks.append(
        check(2, "L2_unique_FullModel_ids", not duplicate_model_ids, duplicate_model_ids, "whole_package")
    )

    required_header_missing: dict[str, list[str]] = {}
    mas_missing: list[str] = []
    scenario_times: set[str] = set()
    profiles_by_file: dict[str, list[str]] = {}
    for name, model, graph in full_models:
        required = {
            "Model.created": MODEL_CREATED,
            "Model.profile": MODEL_PROFILE,
            "Model.scenarioTime": MODEL_SCENARIO_TIME,
            "Model.version": MODEL_VERSION,
        }
        missing = [label for label, predicate in required.items() if not list(graph.objects(model, predicate))]
        if missing:
            required_header_missing[name] = missing
        profiles = {str(value) for value in graph.objects(model, MODEL_PROFILE)}
        profiles_by_file[name] = sorted(profiles)
        scenario_times.update(str(value) for value in graph.objects(model, MODEL_SCENARIO_TIME))
        if _is_igm(profiles) and not list(graph.objects(model, MODEL_MAS)):
            mas_missing.append(name)
    checks.extend(
        [
            check(2, "L2_required_header_fields", not required_header_missing, required_header_missing, "each_FullModel"),
            check(2, "L2_IGM_modeling_authority_set", not mas_missing, mas_missing, "IGM_FullModels"),
            check(2, "L2_consistent_scenario_time", len(scenario_times) == 1, sorted(scenario_times), "whole_package"),
        ]
    )

    merged = Graph()
    for _, graph in graphs:
        merged += graph
    mrids: dict[str, set[str]] = {}
    for subject, predicate, value in merged:
        if local_name(predicate) == "IdentifiedObject.mRID" and isinstance(value, Literal):
            mrids.setdefault(str(value), set()).add(str(subject))
    duplicate_mrids = {key: sorted(values) for key, values in mrids.items() if len(values) > 1}
    base_voltages = {subject for subject, _, value in merged.triples((None, RDF.type, None)) if local_name(value) == "BaseVoltage"}
    base_voltage_missing = sorted(
        str(subject)
        for subject in base_voltages
        if not any(local_name(predicate) == "BaseVoltage.nominalVoltage" for predicate in merged.predicates(subject, None))
    )
    terminals = {subject for subject, _, value in merged.triples((None, RDF.type, None)) if local_name(value) == "Terminal"}
    terminal_missing = sorted(
        str(subject)
        for subject in terminals
        if not any(local_name(predicate) == "Terminal.ConductingEquipment" for predicate in merged.predicates(subject, None))
    )
    checks.extend(
        [
            check(3, "L3_unique_mRID", not duplicate_mrids, duplicate_mrids, "merged_package"),
            check(3, "L3_BaseVoltage_nominalVoltage", not base_voltage_missing, base_voltage_missing, "merged_package"),
            check(3, "L3_Terminal_ConductingEquipment", not terminal_missing, terminal_missing, "merged_package"),
        ]
    )

    model_id_set = set(model_ids)
    dependencies = {
        str(value)
        for _, model, graph in full_models
        for value in graph.objects(model, MODEL_DEPENDENT_ON)
    }
    unresolved_dependencies = sorted(dependencies - model_id_set)
    profile_text = "\n".join(profile for values in profiles_by_file.values() for profile in values)
    required_profile_groups = {
        "Equipment": "Equipment" in profile_text,
        "SteadyStateHypothesis": "SteadyStateHypothesis" in profile_text,
        "Topology": "Topology" in profile_text,
        "StateVariables": "StateVariables" in profile_text,
        "EquipmentBoundary": "EquipmentBoundary" in profile_text,
        "TopologyBoundary": "TopologyBoundary" in profile_text,
    }
    checks.extend(
        [
            check(4, "L4_Model_DependentOn_resolution", not unresolved_dependencies, unresolved_dependencies, "whole_package"),
            check(4, "L4_core_profile_coverage", all(required_profile_groups.values()), required_profile_groups, "assembled_power_flow_package"),
        ]
    )
    failed = [item["rule_id"] for item in checks if item["status"] == "FAIL"]
    if path.resolve() == SOURCE.resolve():
        display_path = "cgmes/corpus/extracted/cgmes24_testconfig/MicroGrid/BaseCase_BC/CGMES_v2.4.15_MicroGridTestConfiguration_BC_Assembled_v2.zip"
    else:
        try:
            display_path = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            display_path = path.name
    return {
        "path": display_path,
        "xml_members": len(graphs),
        "full_models": len(full_models),
        "rdf_triples": len(merged),
        "implemented_levels": sorted(IMPLEMENTED_LEVELS),
        "not_implemented_levels": [5, 6, 7, 8],
        "checks": checks,
        "failed_rule_ids": failed,
        "passed": not failed,
    }


def build_mutant(source: Path, target: Path, mutation: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    changed = False
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if not changed and info.filename.lower().endswith((".xml", ".rdf")):
                root = ET.fromstring(data)
                if mutation == "missing_model_profile":
                    element = root.find(f".//{{{MD}}}Model.profile")
                    if element is not None:
                        parent = root.find(f".//{{{MD}}}FullModel")
                        if parent is not None:
                            parent.remove(element)
                            changed = True
                elif mutation == "unresolved_model_dependency":
                    element = root.find(f".//{{{MD}}}Model.DependentOn")
                    if element is not None:
                        element.set(f"{{{RDF_NS}}}resource", "urn:uuid:00000000-0000-0000-0000-000000000000")
                        changed = True
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            dst.writestr(info, data)
    if not changed:
        raise RuntimeError(f"Mutation {mutation} did not find a target element")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source_digest = sha256(SOURCE)
    if source_digest != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"Positive-control digest drift: {source_digest}")
    positive = validate_package(SOURCE)
    control_specs = {
        "missing_model_profile": "L2_required_header_fields",
        "unresolved_model_dependency": "L4_Model_DependentOn_resolution",
    }
    controls: dict[str, Any] = {}
    for control_id, expected_rule in control_specs.items():
        path = OUTPUT / "negative_controls" / f"{control_id}.zip"
        build_mutant(SOURCE, path, control_id)
        result = validate_package(path)
        controls[control_id] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path),
            "expected_rule": expected_rule,
            "detected": expected_rule in result["failed_rule_ids"],
            "failed_rule_ids": result["failed_rule_ids"],
        }
    checks_path = OUTPUT / "positive_control_checks.csv"
    with checks_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["level", "rule_id", "status", "scope", "observed"])
        writer.writeheader()
        for item in positive["checks"]:
            writer.writerow({**item, "observed": json.dumps(item["observed"], ensure_ascii=False, sort_keys=True)})
    summary = {
        "protocol": "qocdc_4_1_4_applicable_subset_v1",
        "source_sha256": source_digest,
        "qocdc_version": "4.1.4",
        "cgmes_version": "2.4.15",
        "claim_scope": "applicable_subset_only_not_full_QoCDC_compliance",
        "implemented_levels": sorted(IMPLEMENTED_LEVELS),
        "not_implemented_levels": [5, 6, 7, 8],
        "implemented_check_count": len(positive["checks"]),
        "positive_control": {key: value for key, value in positive.items() if key != "checks"},
        "negative_controls": controls,
        "negative_controls_detected": all(control["detected"] for control in controls.values()),
        "ready": positive["passed"] and all(control["detected"] for control in controls.values()),
        "disclaimer": "Not a full QoCDC compliance assessment or OPDM publication decision.",
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
