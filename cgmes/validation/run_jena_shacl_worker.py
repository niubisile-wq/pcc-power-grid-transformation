from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

from rdflib import Graph, RDF, URIRef

from run_shacl_worker import _profiles, _select_shapes, _sha256


SH = "http://www.w3.org/ns/shacl#"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--shapes-root", type=Path, required=True)
    parser.add_argument("--jena-home", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    args.result_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    payload: dict[str, object] = {
        "case_id": args.case_id,
        "status": "error",
        "source_path": args.source.as_posix(),
        "source_sha256": _sha256(args.source),
        "engine": "Apache Jena SHACL CLI",
        "jena_home": args.jena_home.as_posix(),
        "error_type": "",
        "error_message": "",
    }
    try:
        data_graph = Graph()
        xml_entries: list[str] = []
        with zipfile.ZipFile(args.source) as archive:
            for entry in sorted(archive.namelist()):
                if entry.lower().endswith((".xml", ".rdf")):
                    xml_entries.append(entry)
                    data_graph.parse(data=archive.read(entry), format="xml")
        profiles = _profiles(data_graph)
        shape_paths, selection = _select_shapes(args.shapes_root, profiles)
        shapes_graph = Graph()
        for path in shape_paths:
            shapes_graph.parse(path, format="turtle")
        sh_sparql = URIRef(SH + "sparql")
        sparql_constraint = URIRef(SH + "SPARQLConstraint")
        sparql_attachment_count = sum(1 for _ in shapes_graph.triples((None, sh_sparql, None)))
        sparql_constraint_count = sum(
            1 for _ in shapes_graph.triples((None, RDF.type, sparql_constraint))
        )
        with tempfile.TemporaryDirectory(prefix="cgmes_jena_shacl_") as temp_name:
            temp = Path(temp_name)
            data_path = temp / "data.ttl"
            shapes_path = temp / "shapes.ttl"
            data_graph.serialize(data_path, format="turtle")
            shapes_graph.serialize(shapes_path, format="turtle")
            bat = args.jena_home / "bat" / "shacl.bat"
            environment = os.environ.copy()
            environment["JENA_HOME"] = str(args.jena_home)
            command = [
                "cmd.exe",
                "/d",
                "/c",
                str(bat),
                "validate",
                "--shapes",
                shapes_path.resolve().as_uri(),
                "--data",
                data_path.resolve().as_uri(),
            ]
            completed = subprocess.run(
                command,
                cwd=args.jena_home,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        args.report_output.write_text(completed.stdout, encoding="utf-8")
        payload.update(
            {
                "status": "success" if completed.returncode == 0 else "engine_error",
                "worker_exit_code": completed.returncode,
                "xml_file_count": len(xml_entries),
                "data_triple_count": len(data_graph),
                "declared_profiles": sorted(profiles),
                "shape_file_count": len(shape_paths),
                "shape_triple_count": len(shapes_graph),
                "sparql_attachment_count": sparql_attachment_count,
                "sparql_constraint_count": sparql_constraint_count,
                "shape_selection_policy": selection["selection_policy"],
                "report_path": args.report_output.as_posix(),
                "report_size_bytes": args.report_output.stat().st_size,
                "stdout_head": completed.stdout[:2000],
            }
        )
        if completed.returncode != 0:
            payload["error_type"] = "JenaNonzeroExit"
            payload["error_message"] = completed.stdout[-2000:]
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
                    "worker_exit_code",
                    "sparql_constraint_count",
                    "error_type",
                )
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
