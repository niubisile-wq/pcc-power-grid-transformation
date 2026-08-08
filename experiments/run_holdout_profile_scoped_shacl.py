from __future__ import annotations

import json
import sys
import time
import zipfile
from pathlib import Path

from pyshacl import validate
from rdflib import Graph, URIRef
from owlrl import DeductiveClosure, RDFS_Semantics


ROOT = Path(__file__).resolve().parents[1]
CGMES = ROOT / "cgmes"
if str(CGMES) not in sys.path:
    sys.path.insert(0, str(CGMES))

from validation.run_shacl_worker import (  # noqa: E402
    _apply_shape_declared_datatypes,
    _install_pyshacl_service_keyword_guard_hotfix,
    _profiles,
    _select_shapes,
    _severity_counts,
)


SOURCE = CGMES / "corpus" / "holdout" / "powsybl_core_holdout_bundle.zip"
SHAPES_ROOT = (
    CGMES
    / "apl111"
    / "application-profiles-library_v1-1-1"
    / "application-profiles-library-main"
    / "CGMES"
    / "CurrentRelease"
    / "SHACL"
    / "TTL"
)
RDFS_ROOT = SHAPES_ROOT.parents[1] / "RDFS"
OUTPUT_ROOT = ROOT / "outputs" / "cgmes_untouched_holdout" / "apl111_profile_scoped_rdfs"
SUMMARY = ROOT / "outputs" / "cgmes_untouched_holdout" / "apl111_profile_scoped_rdfs_result.json"

PROFILE_MARKERS = {
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


def tokens(profiles: set[str]) -> set[str]:
    joined = "\n".join(profiles)
    return {token for marker, token in PROFILE_MARKERS.items() if marker in joined}


def profile_file(name: str, token: str) -> bool:
    return f"_{token}-AP-" in name or f"_{token}_AP-" in name


def load_shapes(paths: list[Path]) -> Graph:
    graph = Graph()
    for path in paths:
        graph.parse(path, format="turtle")
    return graph


def run_scope(
    label: str,
    data: Graph,
    shape_paths: list[Path],
    focus_nodes: list[str] | None,
) -> dict[str, object]:
    started = time.perf_counter()
    shapes = load_shapes(shape_paths)
    conforms, report, text = validate(
        data,
        shacl_graph=shapes,
        inference=None,
        abort_on_first=False,
        allow_infos=False,
        allow_warnings=False,
        advanced=True,
        meta_shacl=False,
        js=False,
        debug=False,
        focus_nodes=focus_nodes,
    )
    report_path = OUTPUT_ROOT / f"{label}_report.ttl"
    text_path = OUTPUT_ROOT / f"{label}_report.txt"
    report.serialize(report_path, format="turtle")
    text_path.write_text(str(text), encoding="utf-8")
    severities = _severity_counts(report)
    return {
        "scope": label,
        "focus_node_count": len(focus_nodes) if focus_nodes is not None else None,
        "shape_file_count": len(shape_paths),
        "shape_files": [path.name for path in shape_paths],
        "conforms": bool(conforms),
        "validation_result_count": sum(severities.values()),
        "severity_counts": severities,
        "report_graph": report_path.relative_to(ROOT).as_posix(),
        "report_text": text_path.relative_to(ROOT).as_posix(),
        "elapsed_seconds": time.perf_counter() - started,
    }


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    union = Graph()
    focus_by_token: dict[str, set[URIRef]] = {}
    all_profiles: set[str] = set()
    with zipfile.ZipFile(SOURCE) as archive:
        for member in sorted(archive.namelist()):
            if not member.lower().endswith((".xml", ".rdf")):
                continue
            graph = Graph().parse(data=archive.read(member), format="xml")
            member_profiles = _profiles(graph)
            all_profiles.update(member_profiles)
            member_subjects = {subject for subject in graph.subjects() if isinstance(subject, URIRef)}
            for token in tokens(member_profiles):
                focus_by_token.setdefault(token, set()).update(member_subjects)
            union += graph

    selected, selection = _select_shapes(SHAPES_ROOT, all_profiles)
    active_tokens = tokens(all_profiles)
    ontology_paths = sorted(
        path for path in RDFS_ROOT.glob("*Voc-RDFS2020.rdf")
        if "Header" in path.name or any(profile_file(path.name, token) for token in active_tokens)
    )
    ontology = Graph()
    for path in ontology_paths:
        ontology.parse(path, format="xml")
    original_subjects = set(union.subjects())
    closure = union + ontology
    DeductiveClosure(RDFS_Semantics).expand(closure)
    inferred = 0
    for triple in closure:
        if triple[0] in original_subjects and triple not in union:
            union.add(triple)
            inferred += 1
    all_shapes = load_shapes(selected)
    enrichment = _apply_shape_declared_datatypes(union, all_shapes)
    _install_pyshacl_service_keyword_guard_hotfix()

    global_markers = ("CrossProfile", "AllProfiles", "IdentifiedObjectCommon", "Header")
    global_paths = [path for path in selected if any(marker in path.name for marker in global_markers)]
    outcomes: list[dict[str, object]] = []
    for token_name, focus in sorted(focus_by_token.items()):
        paths = [
            path for path in selected
            if profile_file(path.name, token_name)
            and not any(marker in path.name for marker in global_markers)
        ]
        if paths:
            outcomes.append(run_scope(token_name, union, paths, sorted(map(str, focus))))
    if global_paths:
        outcomes.append(run_scope("global_cross_profile", union, global_paths, None))

    total_results = sum(int(item["validation_result_count"]) for item in outcomes)
    payload = {
        "protocol": "cgmes_untouched_holdout_powsybl_core_v1",
        "analysis_status": "post_outcome_scope_and_rdfs_correction_reported_alongside_raw_runs",
        "reason": (
            "ENTSO-E documents distinguish profile-derived constraints from CrossProfile "
            "constraints. Profile-specific shapes retain access to the full model graph "
            "but their target selection is restricted to subjects originating in members "
            "that declare that profile. Global/header/cross-profile shapes run on the union. "
            "The frozen official RDFS2020 vocabularies supply superclass and subproperty "
            "entailments before validation."
        ),
        "source_member_count": 10,
        "data_triple_count": len(union),
        "selected_shape_file_count": selection["selected_ttl_count"],
        "official_rdfs_files": [path.name for path in ontology_paths],
        "official_rdfs_triple_count": len(ontology),
        "inferred_instance_triple_count": inferred,
        "datatype_enrichment": enrichment,
        "scopes": outcomes,
        "validation_result_count": total_results,
        "conforms": all(bool(item["conforms"]) for item in outcomes),
    }
    SUMMARY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "scopes": len(outcomes),
        "validation_result_count": total_results,
        "conforms": payload["conforms"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
