from __future__ import annotations

import collections
import json
from pathlib import Path

from rdflib import Graph, RDF, URIRef


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "outputs" / "cgmes_untouched_holdout" / "apl111_shacl_report.ttl"
OUTPUT = ROOT / "outputs" / "cgmes_untouched_holdout" / "apl111_shacl_diagnostic.json"
SH = "http://www.w3.org/ns/shacl#"


def local(value: object) -> str:
    text = str(value)
    return text.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def main() -> None:
    graph = Graph().parse(REPORT, format="turtle")
    result_type = URIRef(SH + "ValidationResult")
    shape_pred = URIRef(SH + "sourceShape")
    component_pred = URIRef(SH + "sourceConstraintComponent")
    severity_pred = URIRef(SH + "resultSeverity")
    shapes: collections.Counter[str] = collections.Counter()
    components: collections.Counter[str] = collections.Counter()
    severities: collections.Counter[str] = collections.Counter()
    for result in graph.subjects(RDF.type, result_type):
        shapes.update(local(value) for value in graph.objects(result, shape_pred))
        components.update(local(value) for value in graph.objects(result, component_pred))
        severities.update(local(value) for value in graph.objects(result, severity_pred))
    eqbd_terminal = sum(
        count for shape, count in shapes.items()
        if shape.startswith("Terminal.ConductingEquipment")
    )
    payload = {
        "report": REPORT.relative_to(ROOT).as_posix(),
        "total_results": sum(severities.values()),
        "severity_counts": dict(severities.most_common()),
        "top_source_shapes": dict(shapes.most_common(25)),
        "constraint_components": dict(components.most_common()),
        "equipment_boundary_terminal_value_type_results": eqbd_terminal,
        "interpretation": (
            "Diagnostic only: the merged-graph run applies profile-specific "
            "EquipmentBoundary Terminal shapes to ordinary Equipment Terminal "
            "instances. The raw report is retained; a profile-scoped validation "
            "must be reported separately rather than replacing this outcome."
        ),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
