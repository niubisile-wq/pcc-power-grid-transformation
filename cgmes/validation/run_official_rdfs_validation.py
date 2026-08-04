from __future__ import annotations

import csv
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable

from rdflib import Graph, RDF, RDFS, URIRef


ROOT = Path(__file__).resolve().parents[1]
RDFS_ROOT = (
    ROOT
    / "corpus"
    / "extracted"
    / "cgmes2415_rdfs"
    / "ENTSOE_CGMES_v2.4.15_16Feb2016_RDFS"
)
BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig" / "MiniGrid" / "BusBranch"
BOUNDARY = BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_Boundary_v3.zip"
ARTIFACTS = {
    ("cgmes24_minigrid_t1", "official_source"): BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T1_Complete_v3.zip",
    ("cgmes24_minigrid_t1", "veragrid_roundtrip_export"): ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t1__veragrid_roundtrip.zip",
    ("cgmes24_minigrid_t1", "pypowsybl_roundtrip_export"): ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t1__pypowsybl_roundtrip.zip",
    ("cgmes24_minigrid_t2", "official_source"): BASE / "CGMES_v2.4.15_MiniGridTestConfiguration_T2_Complete_v3.zip",
    ("cgmes24_minigrid_t2", "veragrid_roundtrip_export"): ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t2__veragrid_roundtrip.zip",
    ("cgmes24_minigrid_t2", "pypowsybl_roundtrip_export"): ROOT / "results" / "roundtrip_exports" / "cgmes24_minigrid_t2__pypowsybl_roundtrip.zip",
}
CIMS = "http://iec.ch/TC57/1999/rdf-schema-extensions-19990926#"
MD_NAMESPACE = "http://iec.ch/TC57/61970-552/ModelDescription/1#"
INSTANCE_NAMESPACES = (
    "http://iec.ch/TC57/2013/CIM-schema-cim16#",
    "http://entsoe.eu/CIM/SchemaExtension/3/1#",
)


def _schema_path(name_fragment: str) -> Path:
    matches = sorted(
        path
        for path in RDFS_ROOT.glob("*.rdf")
        if name_fragment in path.name and "noAbstract" not in path.name
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one schema for {name_fragment}, found {matches}")
    return matches[0]


SCHEMAS = {
    "diagram": _schema_path("DiagramLayoutProfile"),
    "eq_boundary": _schema_path("EquipmentBoundaryProfile"),
    "eq_core": _schema_path("EquipmentProfileCoreRDF"),
    "eq_core_operation": _schema_path("EquipmentProfileCoreOperation"),
    "eq_core_short_circuit": _schema_path("EquipmentProfileCoreShortCircuitRDF"),
    "eq_core_short_circuit_operation": _schema_path("EquipmentProfileCoreShortCircuitOperation"),
    "geographical": _schema_path("GeographicalLocationProfile"),
    "state_variables": _schema_path("StateVariablesProfile"),
    "steady_state": _schema_path("SteadyStateHypothesisProfile"),
    "topology_boundary": _schema_path("TopologyBoundaryProfile"),
    "topology": _schema_path("TopologyProfile"),
}


def _profiles(graph: Graph) -> set[str]:
    return {
        str(value)
        for _, predicate, value in graph
        if str(predicate).startswith(MD_NAMESPACE) and str(predicate).endswith("Model.profile")
    }


def _select_schema(profiles: set[str]) -> tuple[str, Path] | None:
    joined = "\n".join(sorted(profiles))
    if "EquipmentBoundary" in joined:
        return "eq_boundary", SCHEMAS["eq_boundary"]
    if "TopologyBoundary" in joined:
        return "topology_boundary", SCHEMAS["topology_boundary"]
    if "EquipmentCore" in joined:
        short_circuit = "EquipmentShortCircuit" in joined
        operation = "EquipmentOperation" in joined
        # The published variant files are not additive supersets (for example,
        # the short-circuit variant omits core Equipment properties). Use the
        # full published combined schema for Core+SC files so both declared
        # profile vocabularies are checked in one graph.
        if short_circuit:
            key = "eq_core_short_circuit_operation"
        elif operation:
            key = "eq_core_short_circuit_operation"
        else:
            key = "eq_core"
        return key, SCHEMAS[key]
    routes = {
        "DiagramLayout": "diagram",
        "GeographicalLocation": "geographical",
        "StateVariables": "state_variables",
        "SteadyStateHypothesis": "steady_state",
        "Topology": "topology",
    }
    for marker, key in routes.items():
        if marker in joined:
            return key, SCHEMAS[key]
    return None


def _superclasses(schema: Graph, class_uri: URIRef) -> set[URIRef]:
    found = {class_uri}
    frontier = [class_uri]
    while frontier:
        current = frontier.pop()
        for parent in schema.objects(current, RDFS.subClassOf):
            if isinstance(parent, URIRef) and parent not in found:
                found.add(parent)
                frontier.append(parent)
    return found


def _bounds(value: object) -> tuple[int, int | None]:
    match = re.search(r"M:(\d+)(?:\.\.(\d+|\*))?$", str(value))
    if not match:
        return 0, None
    minimum = int(match.group(1))
    maximum_text = match.group(2)
    maximum = minimum if maximum_text is None else (None if maximum_text == "*" else int(maximum_text))
    return minimum, maximum


def _validate_file(data: bytes, archive_name: str, entry_name: str) -> dict[str, object]:
    instance = Graph()
    try:
        instance.parse(data=data, format="xml")
    except Exception as exc:
        return {
            "archive": archive_name,
            "entry": entry_name,
            "profiles": "",
            "schema_key": "",
            "schema_path": "",
            "rdf_parse_valid": False,
            "unknown_class_count": 0,
            "unknown_property_count": 0,
            "multiplicity_violation_count": 0,
            "rdfs_conforms": False,
            "details_json": json.dumps({"parse_error": f"{type(exc).__name__}: {exc}"}),
        }
    profiles = _profiles(instance)
    selected = _select_schema(profiles)
    if selected is None:
        return {
            "archive": archive_name,
            "entry": entry_name,
            "profiles": " | ".join(sorted(profiles)),
            "schema_key": "",
            "schema_path": "",
            "rdf_parse_valid": True,
            "unknown_class_count": 0,
            "unknown_property_count": 0,
            "multiplicity_violation_count": 0,
            "rdfs_conforms": False,
            "details_json": json.dumps({"schema_error": "No profile-matched official RDFS"}),
        }
    schema_key, schema_path = selected
    schema = Graph()
    schema.parse(schema_path)
    schema_classes = set(schema.subjects(RDF.type, RDFS.Class))
    schema_properties = set(schema.subjects(RDF.type, RDF.Property))
    instance_types: dict[URIRef, set[URIRef]] = {}
    unknown_classes: list[str] = []
    for subject, class_uri in instance.subject_objects(RDF.type):
        if not isinstance(subject, URIRef) or not isinstance(class_uri, URIRef):
            continue
        if str(class_uri).startswith(MD_NAMESPACE):
            continue
        instance_types.setdefault(subject, set()).add(class_uri)
        if str(class_uri).startswith(INSTANCE_NAMESPACES) and class_uri not in schema_classes:
            unknown_classes.append(f"{subject}|{class_uri}")
    unknown_properties = sorted(
        {
            str(predicate)
            for _, predicate, _ in instance
            if predicate != RDF.type
            and str(predicate).startswith(INSTANCE_NAMESPACES)
            and predicate not in schema_properties
        }
    )
    association_used = URIRef(CIMS + "AssociationUsed")
    multiplicity = URIRef(CIMS + "multiplicity")
    requirements: list[tuple[URIRef, URIRef, int, int | None]] = []
    for property_uri in schema_properties:
        domains = [domain for domain in schema.objects(property_uri, RDFS.domain) if isinstance(domain, URIRef)]
        multiplicities = list(schema.objects(property_uri, multiplicity))
        if not domains or not multiplicities:
            continue
        used_values = {str(value).strip().lower() for value in schema.objects(property_uri, association_used)}
        if "no" in used_values:
            continue
        minimum, maximum = _bounds(multiplicities[0])
        requirements.extend((domain, property_uri, minimum, maximum) for domain in domains)
    multiplicity_violations: list[str] = []
    for subject, classes in instance_types.items():
        class_closure: set[URIRef] = set()
        for class_uri in classes:
            class_closure.update(_superclasses(schema, class_uri))
        for domain, property_uri, minimum, maximum in requirements:
            if domain not in class_closure:
                continue
            count = sum(1 for _ in instance.objects(subject, property_uri))
            if count < minimum or (maximum is not None and count > maximum):
                multiplicity_violations.append(
                    f"{subject}|{property_uri}|count={count}|expected={minimum}..{maximum if maximum is not None else '*'}"
                )
    conforms = not unknown_classes and not unknown_properties and not multiplicity_violations
    return {
        "archive": archive_name,
        "entry": entry_name,
        "profiles": " | ".join(sorted(profiles)),
        "schema_key": schema_key,
        "schema_path": schema_path.relative_to(ROOT).as_posix(),
        "rdf_parse_valid": True,
        "unknown_class_count": len(unknown_classes),
        "unknown_property_count": len(unknown_properties),
        "multiplicity_violation_count": len(multiplicity_violations),
        "rdfs_conforms": conforms,
        "details_json": json.dumps(
            {
                "unknown_classes": unknown_classes,
                "unknown_properties": unknown_properties,
                "multiplicity_violations": multiplicity_violations,
            },
            ensure_ascii=False,
        ),
    }


def _archive_rows(path: Path) -> Iterable[dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        for entry in sorted(archive.namelist()):
            if entry.lower().endswith((".xml", ".rdf")):
                yield _validate_file(archive.read(entry), path.name, entry)


def _validate_artifact(paths: Iterable[Path]) -> dict[str, object]:
    instance = Graph()
    schema = Graph()
    parse_errors: list[str] = []
    unmatched_profiles: list[str] = []
    schema_paths: set[str] = set()
    file_count = 0
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for entry in sorted(archive.namelist()):
                if not entry.lower().endswith((".xml", ".rdf")):
                    continue
                file_count += 1
                file_graph = Graph()
                try:
                    file_graph.parse(data=archive.read(entry), format="xml")
                except Exception as exc:
                    parse_errors.append(f"{path.name}:{entry}:{type(exc).__name__}:{exc}")
                    continue
                selected = _select_schema(_profiles(file_graph))
                if selected is None:
                    unmatched_profiles.append(f"{path.name}:{entry}:{sorted(_profiles(file_graph))}")
                else:
                    _, schema_path = selected
                    schema_paths.add(schema_path.relative_to(ROOT).as_posix())
                    schema.parse(schema_path)
                instance += file_graph

    schema_classes = set(schema.subjects(RDF.type, RDFS.Class))
    schema_properties = set(schema.subjects(RDF.type, RDF.Property))
    instance_types: dict[URIRef, set[URIRef]] = {}
    unknown_classes: list[str] = []
    for subject, class_uri in instance.subject_objects(RDF.type):
        if not isinstance(subject, URIRef) or not isinstance(class_uri, URIRef):
            continue
        if str(class_uri).startswith(MD_NAMESPACE):
            continue
        instance_types.setdefault(subject, set()).add(class_uri)
        if str(class_uri).startswith(INSTANCE_NAMESPACES) and class_uri not in schema_classes:
            unknown_classes.append(f"{subject}|{class_uri}")
    unknown_properties = sorted(
        {
            str(predicate)
            for _, predicate, _ in instance
            if predicate != RDF.type
            and str(predicate).startswith(INSTANCE_NAMESPACES)
            and predicate not in schema_properties
        }
    )
    association_used = URIRef(CIMS + "AssociationUsed")
    multiplicity = URIRef(CIMS + "multiplicity")
    requirements: set[tuple[URIRef, URIRef, int, int | None]] = set()
    for property_uri in schema_properties:
        domains = [domain for domain in schema.objects(property_uri, RDFS.domain) if isinstance(domain, URIRef)]
        multiplicities = list(schema.objects(property_uri, multiplicity))
        if not domains or not multiplicities:
            continue
        used_values = {str(value).strip().lower() for value in schema.objects(property_uri, association_used)}
        if "no" in used_values:
            continue
        minimum, maximum = _bounds(multiplicities[0])
        requirements.update((domain, property_uri, minimum, maximum) for domain in domains)
    multiplicity_violations: list[str] = []
    for subject, classes in instance_types.items():
        class_closure: set[URIRef] = set()
        for class_uri in classes:
            class_closure.update(_superclasses(schema, class_uri))
        for domain, property_uri, minimum, maximum in requirements:
            if domain not in class_closure:
                continue
            count = sum(1 for _ in instance.objects(subject, property_uri))
            if count < minimum or (maximum is not None and count > maximum):
                multiplicity_violations.append(
                    f"{subject}|{property_uri}|count={count}|expected={minimum}..{maximum if maximum is not None else '*'}"
                )
    conforms = not (
        parse_errors
        or unmatched_profiles
        or unknown_classes
        or unknown_properties
        or multiplicity_violations
    )
    return {
        "file_count_with_boundary": file_count,
        "rdf_parse_valid": not parse_errors,
        "rdfs_conforms": conforms,
        "unknown_class_count": len(unknown_classes),
        "unknown_property_count": len(unknown_properties),
        "multiplicity_violation_count": len(multiplicity_violations),
        "violation_count": len(parse_errors)
        + len(unmatched_profiles)
        + len(unknown_classes)
        + len(unknown_properties)
        + len(multiplicity_violations),
        "schema_paths": " | ".join(sorted(schema_paths)),
        "details_json": json.dumps(
            {
                "parse_errors": parse_errors,
                "unmatched_profiles": unmatched_profiles,
                "unknown_classes": unknown_classes,
                "unknown_properties": unknown_properties,
                "multiplicity_violations": multiplicity_violations,
            },
            ensure_ascii=False,
        ),
    }


def main() -> None:
    rows: list[dict[str, object]] = []
    for (case_id, artifact_kind), artifact in ARTIFACTS.items():
        artifact_rows = list(_archive_rows(artifact)) + list(_archive_rows(BOUNDARY))
        for row in artifact_rows:
            rows.append({"case_id": case_id, "artifact_kind": artifact_kind, **row})
    output = ROOT / "results" / "official_rdfs_validation_results.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    artifact_summary: list[dict[str, object]] = []
    for (case_id, artifact_kind), artifact in ARTIFACTS.items():
        artifact_summary.append(
            {
                "case_id": case_id,
                "artifact_kind": artifact_kind,
                **_validate_artifact([artifact, BOUNDARY]),
            }
        )
    with (ROOT / "results" / "official_rdfs_validation_artifact_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(artifact_summary[0]))
        writer.writeheader()
        writer.writerows(artifact_summary)
    summary = {
        "official_schema_source": "ENTSO-E CGMES 2.4.15 RDFS package dated 04Jul2016",
        "official_schema_sha256": "7565DC0EF46ACD13F4FE6DFF30EE85999C3B8169701F171140BE54BAB654729F",
        "validation_engine": "local deterministic RDF/XML + RDFS profile/multiplicity validator",
        "not_shacl": True,
        "artifacts": len(artifact_summary),
        "conforming_artifacts": sum(bool(row["rdfs_conforms"]) for row in artifact_summary),
        "nonconforming_artifacts": sum(not bool(row["rdfs_conforms"]) for row in artifact_summary),
    }
    (ROOT / "results" / "official_rdfs_validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    for row in artifact_summary:
        print(row)


if __name__ == "__main__":
    main()
