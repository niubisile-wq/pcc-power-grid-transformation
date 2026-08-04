from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

import pandas as pd
from rdflib import Graph, RDF, URIRef

from adapters.common_asset_schema import canonical_id, record, sha256


TYPE_MAP = {
    "TopologicalNode": "bus",
    "ConnectivityNode": "connectivity_node",
    "BusbarSection": "busbar",
    "ACLineSegment": "line",
    "DCLineSegment": "dc_line",
    "EnergyConsumer": "load",
    "ConformLoad": "load",
    "NonConformLoad": "load",
    "SynchronousMachine": "generator",
    "AsynchronousMachine": "motor",
    "EquivalentInjection": "equivalent_injection",
    "ExternalNetworkInjection": "external_grid",
    "PowerTransformer": "transformer",
    "LinearShuntCompensator": "shunt",
    "NonlinearShuntCompensator": "shunt",
    "Breaker": "switch",
    "Disconnector": "switch",
    "LoadBreakSwitch": "switch",
    "GroundDisconnector": "switch",
}
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def local_name(term: object) -> str:
    text = str(term)
    return text.rsplit("}", 1)[-1].rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def parse_archives(paths: Iterable[Path]) -> Graph:
    graph = Graph()
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.lower().endswith((".xml", ".rdf")):
                    graph.parse(data=archive.read(name), format="xml")
    return graph


def values(graph: Graph, subject: URIRef, predicate_name: str) -> list[object]:
    return [obj for _, pred, obj in graph.triples((subject, None, None)) if local_name(pred) == predicate_name]


def first(graph: Graph, subject: URIRef, *predicate_names: str) -> object | None:
    for predicate_name in predicate_names:
        found = values(graph, subject, predicate_name)
        if found:
            return found[0]
    return None


def load_and_extract(model: Path, boundary: Path, case_id: str, representation: str) -> pd.DataFrame:
    graph = parse_archives([model, boundary])
    terminals_by_equipment: dict[str, list[URIRef]] = {}
    for terminal, _, type_value in graph.triples((None, RDF.type, None)):
        if local_name(type_value) != "Terminal":
            continue
        equipment = first(graph, terminal, "Terminal.ConductingEquipment")
        if equipment is not None:
            terminals_by_equipment.setdefault(canonical_id(equipment), []).append(terminal)
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for subject, _, type_value in graph.triples((None, RDF.type, None)):
        class_name = local_name(type_value)
        if class_name not in TYPE_MAP:
            continue
        asset_type = TYPE_MAP[class_name]
        key = (canonical_id(subject), asset_type)
        if key in seen:
            continue
        seen.add(key)
        terminal_ids = terminals_by_equipment.get(canonical_id(subject), [])
        bus_ids: list[object] = []
        for terminal in terminal_ids:
            bus = first(graph, terminal, "Terminal.TopologicalNode", "Terminal.ConnectivityNode")
            if bus is not None:
                bus_ids.append(bus)
        if class_name == "ConnectivityNode" and not bus_ids:
            topological_node = first(graph, subject, "ConnectivityNode.TopologicalNode")
            if topological_node is not None:
                bus_ids.append(topological_node)
        records.append(
            record(
                case_id=case_id,
                tool="cgmes_rdf",
                tool_version="rdflib",
                source_path=model.as_posix(),
                source_sha256=sha256(model),
                asset_id=str(subject),
                asset_type=asset_type,
                name=first(graph, subject, "IdentifiedObject.name"),
                code=class_name,
                bus1_id=canonical_id(bus_ids[0]) if bus_ids else "",
                bus2_id=canonical_id(bus_ids[1]) if len(bus_ids) > 1 else "",
                terminal_ids=terminal_ids,
                p_mw=first(graph, subject, "EnergyConsumer.p", "RotatingMachine.p", "EquivalentInjection.p"),
                q_mvar=first(graph, subject, "EnergyConsumer.q", "RotatingMachine.q", "EquivalentInjection.q"),
                in_service=None,
                r=first(graph, subject, "ACLineSegment.r"),
                x=first(graph, subject, "ACLineSegment.x"),
                source_representation=representation,
                notes=f"rdf_class={class_name}",
            )
        )
    return pd.DataFrame(records)


def _xml_identity(element: ET.Element) -> str:
    identifier = element.attrib.get(f"{{{RDF_NS}}}about")
    if identifier is None:
        identifier = element.attrib.get(f"{{{RDF_NS}}}ID", "")
    return canonical_id(identifier)


def _xml_child_value(element: ET.Element, *predicate_names: str) -> str | None:
    wanted = set(predicate_names)
    for child in element:
        if local_name(child.tag) not in wanted:
            continue
        resource = child.attrib.get(f"{{{RDF_NS}}}resource")
        return resource if resource is not None else child.text
    return None


def load_and_extract_xml(
    model: Path, boundary: Path | None, case_id: str, representation: str
) -> pd.DataFrame:
    """Extract asset identity from raw XML without repairing invalid RDF semantics.

    XML permits duplicate rdf:ID attributes even though RDF/XML does not. This parser is
    therefore used only for a transparent asset census after the strict structural gate
    has separately recorded the RDF parse failure.
    """
    elements: list[ET.Element] = []
    paths = (model,) if boundary is None else (model, boundary)
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith((".xml", ".rdf")):
                    continue
                root = ET.fromstring(archive.read(name))
                elements.extend(list(root))

    terminal_parts: dict[str, list[ET.Element]] = {}
    for element in elements:
        if local_name(element.tag) != "Terminal":
            continue
        terminal_parts.setdefault(_xml_identity(element), []).append(element)
    terminals_by_equipment: dict[str, list[str]] = {}
    for terminal_id, parts in terminal_parts.items():
        equipment = next(
            (
                value
                for part in parts
                if (value := _xml_child_value(part, "Terminal.ConductingEquipment"))
            ),
            None,
        )
        if equipment:
            terminals_by_equipment.setdefault(canonical_id(equipment), []).append(terminal_id)

    asset_parts: dict[tuple[str, str], list[ET.Element]] = {}
    for element in elements:
        class_name = local_name(element.tag)
        if class_name not in TYPE_MAP:
            continue
        asset_id = _xml_identity(element)
        asset_parts.setdefault((asset_id, class_name), []).append(element)

    def part_value(parts: list[ET.Element], *predicate_names: str) -> str | None:
        return next(
            (
                value
                for part in parts
                if (value := _xml_child_value(part, *predicate_names)) is not None
            ),
            None,
        )

    records: list[dict[str, object]] = []
    for (asset_id, class_name), parts in asset_parts.items():
        asset_type = TYPE_MAP[class_name]
        terminal_ids = terminals_by_equipment.get(asset_id, [])
        bus_ids = [
            next(
                (
                    value
                    for part in terminal_parts[terminal_id]
                    if (value := _xml_child_value(part, "Terminal.TopologicalNode", "Terminal.ConnectivityNode"))
                ),
                None,
            )
            for terminal_id in terminal_ids
        ]
        bus_ids = [bus for bus in bus_ids if bus]
        if class_name == "ConnectivityNode" and not bus_ids:
            topological_node = part_value(parts, "ConnectivityNode.TopologicalNode")
            if topological_node:
                bus_ids.append(topological_node)
        records.append(
            record(
                case_id=case_id,
                tool="cgmes_raw_xml",
                tool_version="stdlib_etree",
                source_path=model.as_posix(),
                source_sha256=sha256(model),
                asset_id=asset_id,
                asset_type=asset_type,
                name=part_value(parts, "IdentifiedObject.name"),
                code=class_name,
                bus1_id=canonical_id(bus_ids[0]) if bus_ids else "",
                bus2_id=canonical_id(bus_ids[1]) if len(bus_ids) > 1 else "",
                terminal_ids=terminal_ids,
                p_mw=part_value(parts, "EnergyConsumer.p", "RotatingMachine.p", "EquivalentInjection.p"),
                q_mvar=part_value(parts, "EnergyConsumer.q", "RotatingMachine.q", "EquivalentInjection.q"),
                in_service=None,
                r=part_value(parts, "ACLineSegment.r"),
                x=part_value(parts, "ACLineSegment.x"),
                source_representation=representation,
                notes=f"raw_xml_class={class_name};strict_rdf_validity_checked_separately",
            )
        )
    return pd.DataFrame(records)
