from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def main() -> None:
    frame = pd.read_csv(
        RESULTS / "cgmes_shacl_validation_results.csv", keep_default_na=False
    )
    if len(frame) != 20 or frame.case_id.nunique() != 20:
        raise RuntimeError("CGMES 3.0 source SHACL denominator is incomplete")
    successful = frame[frame.status == "success"]
    summary = {
        "evidence_role": "internal_validation_not_untouched_final_holdout",
        "official_shapes": True,
        "official_shapes_source": (
            "ENTSO-E CGMES Conformity Assessment Scheme Application Profiles "
            "v3.0.2, SHACL v3.0.0"
        ),
        "validation_engine": "pyshacl",
        "expected_artifacts": 20,
        "recorded_artifacts": len(frame),
        "complete_denominator": True,
        "successful_validations": len(successful),
        "execution_failures": int(frame.status.ne("success").sum()),
        "conforming_artifacts": int(
            successful.shacl_conforms.astype(str).str.lower().eq("true").sum()
        ),
        "nonconforming_artifacts": int(
            successful.shacl_conforms.astype(str).str.lower().eq("false").sum()
        ),
        "total_validation_results": int(
            pd.to_numeric(successful.validation_result_count, errors="coerce")
            .fillna(0)
            .sum()
        ),
        "timeouts": int(frame.timed_out.astype(str).str.lower().eq("true").sum()),
        "selection_policy": (
            "declared-profile-matched official constraints on a merged package graph; "
            "Explicit-CrossProfile selected and Implicit alternative excluded"
        ),
        "datatype_policy": (
            "untyped CIM/XML literals enriched only in the in-memory validation view "
            "from selected official Simple SHACL sh:path/sh:datatype declarations; "
            "source archives remain byte-identical"
        ),
        "finalization_note": (
            "The long-running parent lost its attached output channel after the external "
            "orchestrator wait expired. All 20 endpoint rows had already been written; "
            "this summary was deterministically rebuilt from that preserved CSV without "
            "rerunning any model."
        ),
    }
    (RESULTS / "cgmes_shacl_validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
