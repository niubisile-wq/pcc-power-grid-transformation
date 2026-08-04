from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import traceback
import zipfile
from pathlib import Path

from pyshacl import validate
from pyshacl.helper.sparql_query_helper import SPARQLQueryHelper
from rdflib import Graph, Literal, RDF, URIRef


ROOT = Path(__file__).resolve().parents[1]
SH = "http://www.w3.org/ns/shacl#"
MD_PROFILE_SUFFIX = "Model.profile"


PROFILE_FILE_TOKENS = {
    "CoreEquipment": "Equipment",
    "EquipmentBoundary": "EquipmentBoundary",
    "Operation": "Operation",
    "ShortCircuit": "ShortCircuit",
    "SteadyStateHypothesis": "SteadyStateHypothesis",
    "StateVariables": "StateVariables",
    "Topology": "Topology",
    "DiagramLayout": "DiagramLayout",
    "GeographicalLocation": "GeographicalLocation",
    "Dynamics": "Dynamics",
}


def _install_pyshacl_service_keyword_guard_hotfix() -> None:
    """Avoid pySHACL 0.30.1 mistaking cim:*.inService for SERVICE.

    The upstream guard's optional leading ``S`` can match the suffix of the
    ordinary CGMES predicate ``inService``. This replacement still rejects an
    actual SPARQL SERVICE (including SERVICE SILENT) while requiring a keyword
    boundary. It changes only the engine's safety guard, never the official
    query, shapes, or instance graph.
    """

    SPARQLQueryHelper.has_service_regex = re.compile(
        r"(?<![\w:])SERVICE(?:\s+SILENT)?\s*<", flags=re.M | re.I
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _profiles(graph: Graph) -> set[str]:
    return {
        str(value)
        for _, predicate, value in graph
        if str(predicate).endswith(MD_PROFILE_SUFFIX)
    }


def _active_tokens(profiles: set[str]) -> set[str]:
    active: set[str] = set()
    joined = "\n".join(profiles)
    # Match EquipmentBoundary first so it does not accidentally activate the
    # separate Equipment profile.
    for marker, token in PROFILE_FILE_TOKENS.items():
        if marker in joined:
            active.add(token)
    return active


def _profile_token_in_filename(name: str, token: str) -> bool:
    return f"_{token}-AP-" in name or f"_{token}_AP-" in name


def _select_shapes(
    shapes_root: Path, profiles: set[str]
) -> tuple[list[Path], dict[str, object]]:
    candidates = sorted(shapes_root.rglob("*.ttl"))
    tokens = _active_tokens(profiles)
    solved = "StateVariables" in tokens
    selected: list[Path] = []
    for path in candidates:
        name = path.name
        if "NotSolvedMAS" in name and solved:
            continue
        if "SolvedMAS" in name and not solved:
            continue
        # The complete package is loaded as one merged data graph, so the
        # official Explicit-CrossProfile constraints are applicable. The
        # Implicit alternative is deliberately not unioned with it.
        if "Implicit-CrossProfile" in name:
            continue
        always = any(
            marker in name
            for marker in ("Header", "AllProfiles", "IdentifiedObjectCommon")
        )
        profile_specific = any(
            _profile_token_in_filename(name, token) for token in tokens
        )
        if always or profile_specific:
            selected.append(path)
    policy = {
        "active_profile_tokens": sorted(tokens),
        "solved_mas": solved,
        "selection_policy": (
            "official TTL constraints matching declared FullModel profiles, "
            "plus Header, AllProfiles and IdentifiedObjectCommon; SolvedMAS or "
            "NotSolvedMAS chosen from StateVariables presence; merged graph uses "
            "Explicit-CrossProfile and excludes the Implicit alternative"
        ),
        "candidate_ttl_count": len(candidates),
        "selected_ttl_count": len(selected),
        "selected_ttl": [path.relative_to(ROOT).as_posix() for path in selected],
        "selected_sha256": {
            path.relative_to(ROOT).as_posix(): _sha256(path) for path in selected
        },
    }
    return selected, policy


def _severity_counts(report: Graph) -> dict[str, int]:
    result_type = URIRef(SH + "ValidationResult")
    severity_predicate = URIRef(SH + "resultSeverity")
    counts = {"Violation": 0, "Warning": 0, "Info": 0, "Other": 0}
    for result in report.subjects(RDF.type, result_type):
        severities = list(report.objects(result, severity_predicate))
        key = str(severities[0]).rsplit("#", 1)[-1] if severities else "Other"
        counts[key if key in counts else "Other"] += 1
    return counts


def _apply_shape_declared_datatypes(
    data_graph: Graph, shapes_graph: Graph
) -> dict[str, object]:
    """Build the schema-aware validation view expected by CGMES validators.

    CIM/XML serializes attribute values without rdf:datatype. The official
    Simple SHACL shapes carry the authoritative predicate-to-XSD datatype
    mapping. ModShape and other CGMES-aware loaders apply that mapping while
    parsing; a generic RDF/XML parser does not. We enrich only untyped
    literals in memory and never rewrite the source archive.
    """

    sh_path = URIRef(SH + "path")
    sh_datatype = URIRef(SH + "datatype")
    declarations: dict[URIRef, set[URIRef]] = {}
    for property_shape, _, path in shapes_graph.triples((None, sh_path, None)):
        if not isinstance(path, URIRef):
            continue
        for datatype in shapes_graph.objects(property_shape, sh_datatype):
            if isinstance(datatype, URIRef):
                declarations.setdefault(path, set()).add(datatype)
    ambiguous = {
        str(path): sorted(map(str, datatypes))
        for path, datatypes in declarations.items()
        if len(datatypes) != 1
    }
    mapping = {
        path: next(iter(datatypes))
        for path, datatypes in declarations.items()
        if len(datatypes) == 1
    }
    replacements: list[tuple[URIRef, URIRef, Literal, Literal]] = []
    invalid_lexical: list[str] = []
    for predicate, datatype in mapping.items():
        for subject, _, value in data_graph.triples((None, predicate, None)):
            if not isinstance(value, Literal) or value.datatype is not None or value.language:
                continue
            typed = Literal(str(value), datatype=datatype, normalize=False)
            if getattr(typed, "ill_typed", False):
                invalid_lexical.append(f"{subject}|{predicate}|{value}|{datatype}")
            replacements.append((subject, predicate, value, typed))
    for subject, predicate, old, new in replacements:
        data_graph.remove((subject, predicate, old))
        data_graph.add((subject, predicate, new))
    return {
        "datatype_mapping_source": "selected official Simple SHACL sh:path + sh:datatype declarations",
        "datatype_enrichment_scope": "in_memory_validation_view_only_source_archive_unchanged",
        "datatype_mapping_property_count": len(mapping),
        "datatype_mapping_ambiguous_property_count": len(ambiguous),
        "datatype_mapping_ambiguous": ambiguous,
        "datatype_enriched_literal_count": len(replacements),
        "datatype_invalid_lexical_count": len(invalid_lexical),
        "datatype_invalid_lexical": invalid_lexical,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--shapes-root", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    parser.add_argument("--report-graph-output", type=Path, required=True)
    parser.add_argument("--report-text-output", type=Path, required=True)
    parser.add_argument("--selection-output", type=Path, required=True)
    args = parser.parse_args()
    for path in (
        args.result_output,
        args.report_graph_output,
        args.report_text_output,
        args.selection_output,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    payload: dict[str, object] = {
        "case_id": args.case_id,
        "status": "error",
        "source_path": args.source.as_posix(),
        "source_sha256": _sha256(args.source),
        "official_shapes": True,
        "official_shapes_version": "CGMES CAS Application Profiles 3.0.2 / SHACL 3.0.0",
        "validation_engine": "pyshacl",
        "inference": "none",
        "advanced": True,
        "engine_hotfix": (
            "pyshacl_service_keyword_guard_requires_word_boundary_to_avoid_"
            "false_match_on_cim_inService"
        ),
        "error_type": "",
        "error_message": "",
    }
    try:
        data_graph = Graph()
        parse_errors: list[str] = []
        xml_entries: list[str] = []
        with zipfile.ZipFile(args.source) as archive:
            for entry in sorted(archive.namelist()):
                if not entry.lower().endswith((".xml", ".rdf")):
                    continue
                xml_entries.append(entry)
                try:
                    data_graph.parse(data=archive.read(entry), format="xml")
                except Exception as exc:
                    parse_errors.append(f"{entry}: {type(exc).__name__}: {exc}")
        profiles = _profiles(data_graph)
        shape_paths, selection = _select_shapes(args.shapes_root, profiles)
        args.selection_output.write_text(
            json.dumps(
                {
                    "case_id": args.case_id,
                    "declared_profiles": sorted(profiles),
                    "xml_entries": xml_entries,
                    **selection,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if parse_errors:
            raise RuntimeError("RDF/XML parse failures: " + " | ".join(parse_errors))
        if not profiles:
            raise RuntimeError("No FullModel Model.profile declarations found")
        if not shape_paths:
            raise RuntimeError("No applicable official SHACL shape files selected")
        shapes_graph = Graph()
        for shape_path in shape_paths:
            shapes_graph.parse(shape_path, format="turtle")
        datatype_enrichment = _apply_shape_declared_datatypes(data_graph, shapes_graph)
        _install_pyshacl_service_keyword_guard_hotfix()
        conforms, report_graph, report_text = validate(
            data_graph,
            shacl_graph=shapes_graph,
            inference=None,
            abort_on_first=False,
            allow_infos=False,
            allow_warnings=False,
            advanced=True,
            meta_shacl=False,
            js=False,
            debug=False,
        )
        args.report_text_output.write_text(str(report_text), encoding="utf-8")
        common_result = {
            "rdf_parse_valid": True,
            "xml_file_count": len(xml_entries),
            "data_triple_count": len(data_graph),
            "declared_profiles": sorted(profiles),
            "shape_file_count": len(shape_paths),
            "shape_triple_count": len(shapes_graph),
            **datatype_enrichment,
            "report_text_path": args.report_text_output.as_posix(),
            "selection_path": args.selection_output.as_posix(),
        }
        if not isinstance(report_graph, Graph):
            payload.update(
                {
                    "status": "processor_failure",
                    **common_result,
                    "error_type": type(report_graph).__name__,
                    "error_message": str(report_text),
                }
            )
        else:
            report_graph.serialize(args.report_graph_output, format="turtle")
            severities = _severity_counts(report_graph)
            payload.update(
                {
                    "status": "success",
                    **common_result,
                    "shacl_conforms": bool(conforms),
                    "validation_result_count": sum(severities.values()),
                    "violation_count": severities["Violation"],
                    "warning_count": severities["Warning"],
                    "info_count": severities["Info"],
                    "other_severity_count": severities["Other"],
                    "report_graph_path": args.report_graph_output.as_posix(),
                }
            )
    except Exception as exc:
        payload.update(
            {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    payload["worker_elapsed_seconds"] = time.perf_counter() - started
    args.result_output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: payload.get(key)
                for key in (
                    "case_id",
                    "status",
                    "shacl_conforms",
                    "validation_result_count",
                    "error_type",
                )
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
