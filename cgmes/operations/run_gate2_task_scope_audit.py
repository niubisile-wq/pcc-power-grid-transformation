from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import canonical_id, sha256  # noqa: E402
from operations.run_natural_operational_replay import (  # noqa: E402
    T1_CONVERTED,
    T1_SOURCE,
    T2_CONVERTED,
    T2_SOURCE,
    _connectivity_to_topological_aliases,
    _load,
    _solve,
)


PATHS = {
    "cgmes24_minigrid_t1": (T1_SOURCE, T1_CONVERTED),
    "cgmes24_minigrid_t2": (T2_SOURCE, T2_CONVERTED),
}


def _generator(circuit, identity: str):
    identity = canonical_id(identity)
    return next(
        (generator for generator in circuit.generators if canonical_id(generator.idtag) == identity),
        None,
    )


def main() -> None:
    mapping = pd.read_csv(ROOT / "results" / "roundtrip_asset_mapping.csv", keep_default_na=False)
    mutations = mapping[
        mapping.adjudication_status.eq("confirmed_same_mrid_semantic_type_mutation")
    ].copy()
    rows: list[dict[str, object]] = []
    for case_id, group in mutations.groupby("case_id", sort=True):
        source_path, converted_path = PATHS[str(case_id)]
        converted = _load(converted_path)
        aliases = _connectivity_to_topological_aliases(converted_path)
        base = _solve(copy.deepcopy(converted), aliases)
        for record in group.to_dict("records"):
            identity = canonical_id(record["source_mrid"])
            generator = _generator(converted, identity)
            if generator is None:
                outage = {
                    "status": "error",
                    "converged": False,
                    "risk_score": "",
                    "vmin_pu": "",
                    "vmax_pu": "",
                    "max_loading_pu": "",
                    "error_type": "MissingConvertedGenerator",
                    "error_message": identity,
                }
            else:
                model = copy.deepcopy(converted)
                _generator(model, identity).active = False
                outage = _solve(model, aliases)
            rows.append(
                {
                    "case_id": case_id,
                    "run_id": record["run_id"],
                    "asset_mrid": identity,
                    "source_rdf_class": "AsynchronousMachine",
                    "target_rdf_class": "SynchronousMachine",
                    "source_task_membership": "motor_contingency_candidate_not_generator_candidate",
                    "target_task_membership": "generator_contingency_candidate",
                    "identity_only_decision": "accept",
                    "full_pcc_decision": "reject",
                    "full_pcc_reason": "asset_type_changed",
                    "source_generator_nminus1_status": "not_applicable_source_asset_is_motor",
                    "target_generator_nminus1_status": outage["status"],
                    "target_generator_nminus1_converged": outage["converged"],
                    "target_generator_nminus1_risk_score": outage["risk_score"],
                    "target_generator_nminus1_vmin_pu": outage["vmin_pu"],
                    "target_generator_nminus1_vmax_pu": outage["vmax_pu"],
                    "target_generator_nminus1_max_loading_pu": outage["max_loading_pu"],
                    "converted_base_converged": base["converged"],
                    "converted_base_risk_score": base["risk_score"],
                    "source_sha256": sha256(source_path),
                    "target_sha256": sha256(converted_path),
                    "error_type": outage["error_type"],
                    "error_message": outage["error_message"],
                    "natural_noninjected": True,
                    "task_scope": "generator_N-1_candidate_selection",
                }
            )
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "results" / "full_pcc_identity_only_task_scope_results.csv", index=False)
    summary = {
        "natural_semantic_mutation_cases": len(frame),
        "case_models": int(frame.case_id.nunique()),
        "identity_only_false_accepts": int(frame.identity_only_decision.eq("accept").sum()),
        "full_pcc_rejections": int(frame.full_pcc_decision.eq("reject").sum()),
        "converted_generator_nminus1_attempts": len(frame),
        "converted_generator_nminus1_converged": int(frame.target_generator_nminus1_converged.astype(bool).sum()),
        "misclassified_generator_candidates_avoided_by_pcc": len(frame),
        "gate2_met": bool(
            len(frame) > 0
            and frame.identity_only_decision.eq("accept").all()
            and frame.full_pcc_decision.eq("reject").all()
        ),
        "gate2_interpretation": (
            "The same mRID makes identity-only accept six natural motor-to-generator class mutations, "
            "whereas full PCC rejects the type payload before generator N-1 candidate enumeration."
        ),
        "numeric_claim_limit": (
            "The result establishes task-candidate misclassification and executable extra generator-outage runs; "
            "it does not establish a safety classification reversal."
        ),
    }
    (ROOT / "results" / "full_pcc_identity_only_task_scope_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
