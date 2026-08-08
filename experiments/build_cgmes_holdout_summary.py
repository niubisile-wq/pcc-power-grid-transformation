from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "cgmes_untouched_holdout"
SELECTION = ROOT / "cgmes" / "corpus" / "holdout" / "powsybl_core_holdout_selection.json"
OUTPUT = BASE / "holdout_summary.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def optional(path: Path) -> dict | None:
    return load(path) if path.is_file() else None


def main() -> None:
    selection = load(SELECTION)
    pcc = load(BASE / "pcc_summary.json")
    shacl = optional(BASE / "apl111_shacl_result.json")
    shacl_diagnostic = optional(BASE / "apl111_shacl_diagnostic.json")
    shacl_scoped = optional(BASE / "apl111_profile_scoped_result.json")
    shacl_scoped_rdfs = optional(BASE / "apl111_profile_scoped_rdfs_result.json")
    imported = optional(BASE / "pypowsybl_import.json")
    outcomes = pcc["outcomes"]
    pcc_ready = (
        outcomes["lawful_complete_proof"]["decision"] == "accept"
        and outcomes["lawful_complete_proof"]["solver_starts"] == 1
        and outcomes["harmful_missing_proof"]["decision"] != "accept"
        and outcomes["harmful_missing_proof"]["solver_starts"] == 0
    )
    summary = {
        "protocol": "cgmes_untouched_holdout_powsybl_core_v1",
        "frozen_before_inspection": True,
        "frozen_commit": "4e8024eaf07a43673c68226aefc8b57dae4c4ffb",
        "artifacts": len(selection["selected_members"]),
        "bundle_sha256": pcc["artifact_sha256"],
        "selection_manifest": SELECTION.relative_to(ROOT).as_posix(),
        "pcc_reported_separately": True,
        "pcc": outcomes,
        "pcc_ready": pcc_ready,
        "official_shacl_reported_separately": shacl is not None,
        "official_shacl": shacl,
        "official_shacl_merged_graph_diagnostic": shacl_diagnostic,
        "official_shacl_profile_scoped_diagnostic": shacl_scoped,
        "official_shacl_profile_scoped_rdfs_diagnostic": shacl_scoped_rdfs,
        "official_shacl_interpretation": (
            "Raw merged-graph outcome is retained. Profile scoping removes cross-profile "
            "target contamination, while full RDFS closure is incompatible with the "
            "published sh:in value-type shapes because every inferred superclass becomes "
            "a separately checked path value. Diagnostics do not replace the raw result."
        ),
        "pypowsybl_import_reported_separately": imported is not None,
        "pypowsybl_import": imported,
        "full_qocdc_compliance_claim": False,
        "ready": pcc_ready and shacl is not None and imported is not None,
    }
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
