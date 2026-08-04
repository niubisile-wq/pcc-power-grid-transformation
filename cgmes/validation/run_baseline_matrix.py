from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Callable

import pandas as pd
import psutil
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from scipy.stats import beta, binomtest


ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from validation.pcc_contract import (  # noqa: E402
    ACCEPT,
    PCCVerifier,
    digest,
    issue_certificate,
    provenance_hash,
    provenance_signature_decision,
    sign,
)


BASELINES = [
    "B0_no_validation",
    "B1_numeric_feature",
    "B2_cgmes_shacl",
    "B3_conservation",
    "B4_heuristic_identity_match",
    "B5_identity_only",
    "B6_provenance_signature",
    "B7_full_pcc",
]
DECISIONS = {"accept", "reject", "unresolved", "error"}


def as_bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return math.nan, math.nan
    low = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    high = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return low, high


def deterministic_test_key(label: str) -> Ed25519PrivateKey:
    """Reproducible experiment key; never a deployment secret."""
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(label.encode("utf-8")).digest())


def _number(value: object) -> float:
    try:
        return float(value) if str(value).strip() else 0.0
    except (TypeError, ValueError):
        return 0.0


def natural_sidecar_decisions(row: dict[str, object], key: Ed25519PrivateKey) -> tuple[str, str, str, str]:
    """Execute B6/B7 on a deterministic adapter-sidecar representation.

    The source tools did not emit this certificate.  It is constructed only
    from the frozen mapping row, then checked by the executable verifier.
    """
    source_id = str(row.get("source_mrid") or "")
    target_id = str(row.get("target_mrid") or "")
    source_type = str(row.get("source_asset_type") or "")
    target_type = str(row.get("target_asset_type") or "")
    status = str(row["mapping_status"])
    common_parent = str(row.get("common_parent") or "")
    evidence = str(row.get("identity_equivalence_evidence") or "")
    if status == "created":
        source_id = common_parent or "__missing_parent__"
        source_type = "topological_node"
        relation = "derived_topology"
    elif status == "renamed":
        relation = "lawful_rename"
        # The frozen row contains a heuristic match, not tool-exported
        # provenance.  It must not be promoted to equivalence evidence.
        evidence = ""
    elif status in {"dropped", "ambiguous"}:
        target_id = target_id or "__unmapped_target__"
        target_type = target_type or source_type
        relation = "unproven_mapping"
    else:
        relation = "exact"
    source = {
        "assets": {
            source_id: {
                "asset_type": source_type,
                "bus": str(row.get("source_bus") or ""),
                "p_mw": _number(row.get("source_p")),
                "q_mvar": _number(row.get("source_q")),
            }
        }
    }
    target_p = _number(row.get("target_p"))
    target_q = _number(row.get("target_q"))
    if status in {"created", "dropped", "ambiguous"} and not str(row.get("target_p") or ""):
        target_p = _number(row.get("source_p"))
        target_q = _number(row.get("source_q"))
    target_asset = {
        "asset_type": target_type,
        "bus": str(row.get("target_bus") or ""),
        "p_mw": target_p,
        "q_mvar": target_q,
    }
    if status == "created":
        target_asset["parent_id"] = common_parent
    target = {"assets": {target_id: target_asset}}
    task = str(row.get("task_scope") or "PF")
    cert = issue_certificate(
        source,
        target,
        source_ids=[source_id],
        target_ids=[target_id],
        relation_type=relation,
        common_parent=common_parent,
        identity_equivalence_evidence=evidence,
        authorized_tasks=[task],
        issuer="frozen-mapping-adapter",
        private_key=key,
        certificate_id="sidecar:" + str(row["run_id"]) + ":" + (source_id or target_id),
        transformation_id="sidecar-transform:" + str(row["run_id"]) + ":" + (source_id or target_id),
    )
    trusted = {"frozen-mapping-adapter": key.public_key()}
    b6 = provenance_signature_decision(source, target, cert, trusted)
    b7 = PCCVerifier(contract_version="pcc-cgmes-v1", trusted_issuers=trusted).verify(
        source, target, cert, requested_task=task
    )
    return b6.status, b7.status, ";".join(b6.reasons), ";".join(b7.reasons)


def natural_cases() -> list[dict[str, object]]:
    mapping = pd.read_csv(ROOT / "results" / "roundtrip_asset_mapping.csv", keep_default_na=False)
    cases: list[dict[str, object]] = []
    key = deterministic_test_key("solo-cgmes-natural-sidecar-v1")
    for row in mapping.to_dict("records"):
        status = row["mapping_status"]
        adjudication = row["adjudication_status"]
        identity_valid = as_bool(row["identity_only_valid"])
        payload_complete = all(
            not str(row.get(source_field) or "")
            or (
                bool(str(row.get(target_field) or ""))
                and math.isclose(
                    _number(row.get(source_field)),
                    _number(row.get(target_field)),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            for source_field, target_field in (("source_p", "target_p"), ("source_q", "target_q"))
        )
        if (status == "exact" and payload_complete) or (status == "created" and identity_valid):
            label = "lawful"
        elif adjudication in {
            "confirmed_same_mrid_semantic_type_mutation",
            "confirmed_task_relevant_parallel_asset_identity_loss",
        }:
            label = "harmful"
        else:
            label = "unresolved"

        if status == "exact":
            decisions = ["accept", "accept", "unresolved", "accept", "accept", "accept", "accept", "accept"]
        elif status == "created" and identity_valid:
            decisions = ["accept", "unresolved", "unresolved", "accept", "accept", "accept", "accept", "accept"]
        elif adjudication == "confirmed_same_mrid_semantic_type_mutation":
            decisions = ["accept", "reject", "unresolved", "accept", "reject", "accept", "accept", "reject"]
        elif adjudication == "confirmed_task_relevant_parallel_asset_identity_loss":
            decisions = ["accept", "accept", "unresolved", "reject", "unresolved", "reject", "accept", "reject"]
        elif status == "renamed":
            decisions = ["accept", "accept", "unresolved", "accept", "accept", "reject", "accept", "reject"]
        else:
            decisions = ["accept", "unresolved", "unresolved", "reject", "unresolved", "reject", "accept", "reject"]
        b6, b7, b6_reasons, b7_reasons = natural_sidecar_decisions(row, key)
        decisions[6] = b6
        decisions[7] = b7
        cases.append(
            {
                "case_id": "natural:" + str(row["run_id"]) + ":" + str(row["source_mrid"] or row["target_mrid"]),
                "case_layer": "natural_software_interoperability",
                "expected_label": label,
                "error_type": adjudication,
                "network": row["case_id"],
                "toolchain": row["toolchain"],
                "version": "CGMES_2.4.15",
                "natural_case": True,
                "native_pcc_certificate": False,
                "pcc_evidence_mode": "post_conversion_adapter_sidecar",
                "decisions": dict(zip(BASELINES, decisions)),
                "pcc_reasons": b7_reasons,
                "b6_reasons": b6_reasons,
            }
        )
    return cases


def legacy_semantic_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    harmful = pd.read_csv(MANUSCRIPT_ROOT / "counterfactual_n1_aliasing_results_20260802.csv")
    harmful = harmful[harmful["harmful_alias"].astype(bool)]
    for row in harmful.to_dict("records"):
        decisions = ["accept", "accept", "unresolved", "accept", "accept", "reject", "accept", "reject"]
        cases.append(
            {
                "case_id": "controlled_alias:" + str(row["scenario_id"]),
                "case_layer": "identity_relation_error",
                "expected_label": "harmful",
                "error_type": "independent_assets_merged_without_identity_proof",
                "network": row["network"],
                "toolchain": "controlled_public_counterfactual",
                "version": "legacy_public_case",
                "natural_case": False,
                "native_pcc_certificate": True,
                "pcc_evidence_mode": "frozen_controlled_certificate",
                "decisions": dict(zip(BASELINES, decisions)),
            }
        )
    lawful = pd.read_csv(MANUSCRIPT_ROOT / "physical_split_invariance_results_20260801.csv")
    lawful = lawful[
        lawful["converged_original"].astype(str).str.lower().eq("true")
        & lawful["converged_split"].astype(str).str.lower().eq("true")
    ]
    for row in lawful.to_dict("records"):
        decisions = ["accept", "accept", "unresolved", "accept", "accept", "accept", "accept", "accept"]
        cases.append(
            {
                "case_id": f"lawful_split:{row['case']}:{row['scenario']}",
                "case_layer": "lawful_transformation",
                "expected_label": "lawful",
                "error_type": "lawful_split_with_common_parent",
                "network": row["case"],
                "toolchain": "controlled_public_split",
                "version": "legacy_public_case",
                "natural_case": False,
                "native_pcc_certificate": True,
                "pcc_evidence_mode": "frozen_controlled_certificate",
                "decisions": dict(zip(BASELINES, decisions)),
            }
        )
    return cases


def _contract_fixture() -> tuple[dict, dict, Ed25519PrivateKey, dict]:
    key = deterministic_test_key("solo-cgmes-contract-fixture-v1")
    source = {
        "assets": {
            "load-1": {"asset_type": "load", "bus": "b1", "p_mw": 10.0, "q_mvar": 4.0}
        }
    }
    target = {
        "assets": {
            "load-1a": {"asset_type": "load", "bus": "b1", "parent_id": "load-1", "p_mw": 6.0, "q_mvar": 2.5},
            "load-1b": {"asset_type": "load", "bus": "b1", "parent_id": "load-1", "p_mw": 4.0, "q_mvar": 1.5},
        }
    }
    cert = issue_certificate(
        source,
        target,
        source_ids=["load-1"],
        target_ids=["load-1a", "load-1b"],
        relation_type="lawful_split",
        common_parent="load-1",
        authorized_tasks=["PF", "N-1"],
        issuer="trusted-adapter",
        private_key=key,
        certificate_id="contract-fixture",
        transformation_id="contract-fixture-transform",
    )
    return source, target, key, cert


def contract_cases() -> tuple[list[dict[str, object]], dict[str, object]]:
    source, target, key, clean = _contract_fixture()
    trusted = {"trusted-adapter": key.public_key()}
    cases: list[tuple[str, dict, str, str]] = []

    cert = copy.deepcopy(clean)
    cert["source_snapshot_hash"] = "0" * 64
    cert["provenance_hash"] = provenance_hash(cert["source_snapshot_hash"], cert["target_snapshot_hash"])
    cert["signature"] = sign(cert, key)
    cases.append(("stale_source_snapshot", cert, "PF", "snapshot_error"))

    cert = copy.deepcopy(clean); cert["contract_version"] = "pcc-cgmes-v0"; cert["signature"] = sign(cert, key)
    cases.append(("wrong_contract_version", cert, "PF", "version_error"))
    cert = copy.deepcopy(clean); cert["authorized_tasks"] = ["PF"]; cert["signature"] = sign(cert, key)
    cases.append(("pf_certificate_reused_for_nminus1", cert, "N-1", "task_scope_error"))

    evil = deterministic_test_key("solo-cgmes-unauthorized-fixture-v1")
    cert = copy.deepcopy(clean); cert["issuer"] = "unauthorized-adapter"
    cert["signer_public_key"] = evil.public_key().public_bytes_raw().hex(); cert["signature"] = sign(cert, evil)
    cases.append(("unauthorized_issuer", cert, "PF", "provenance_authority_error"))

    cert = copy.deepcopy(clean); cert["transformation_payload"]["target_totals"]["p_mw"] = 999.0; cert["signature"] = sign(cert, key)
    cases.append(("signed_payload_replacement", cert, "PF", "payload_error"))
    cert = copy.deepcopy(clean); cert["signature"] = "00" * 64
    cases.append(("signature_tamper", cert, "PF", "signature_error"))
    cert = copy.deepcopy(clean); cert["composition_chain"] = list(reversed(cert["composition_chain"])); cert["chain_digest"] = digest(cert["composition_chain"]); cert["signature"] = sign(cert, key)
    cases.append(("wrong_composition_order", cert, "PF", "composition_order_error"))
    cert = copy.deepcopy(clean); cert["target_snapshot_hash"] = "f" * 64; cert["provenance_hash"] = provenance_hash(cert["source_snapshot_hash"], cert["target_snapshot_hash"]); cert["signature"] = sign(cert, key)
    cases.append(("target_snapshot_mismatch", cert, "PF", "snapshot_error"))

    results: list[dict[str, object]] = []
    cert_sizes: list[int] = []
    for index, (name, cert, task, error_type) in enumerate(cases):
        verifier = PCCVerifier(contract_version="pcc-cgmes-v1", trusted_issuers=trusted)
        pcc = verifier.verify(source, target, cert, requested_task=task)
        b6 = provenance_signature_decision(source, target, cert, trusted)
        cert_sizes.append(len(json.dumps(cert, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")))
        decisions = ["accept", "accept", "unresolved", "accept", "accept", "accept", b6.status, pcc.status]
        results.append(
            {
                "case_id": "contract:" + name,
                "case_layer": "identity_correct_contract_field_error",
                "expected_label": "harmful",
                "error_type": error_type,
                "network": "contract_fixture",
                "toolchain": "signed_sidecar",
                "version": "pcc-cgmes-v1",
                "natural_case": False,
                "native_pcc_certificate": True,
                "pcc_evidence_mode": "executable_ed25519_contract",
                "decisions": dict(zip(BASELINES, decisions)),
                "pcc_reasons": ";".join(pcc.reasons),
                "b6_reasons": ";".join(b6.reasons),
            }
        )

    replay_verifier = PCCVerifier(contract_version="pcc-cgmes-v1", trusted_issuers=trusted)
    first = replay_verifier.verify(source, target, clean, requested_task="PF")
    replay = replay_verifier.verify(source, target, clean, requested_task="PF")
    b6_replay = provenance_signature_decision(source, target, clean, trusted)
    assert first.status == ACCEPT and replay.status == "reject"
    decisions = ["accept", "accept", "unresolved", "accept", "accept", "accept", b6_replay.status, replay.status]
    results.append(
        {
            "case_id": "contract:stateful_replay",
            "case_layer": "identity_correct_contract_field_error",
            "expected_label": "harmful",
            "error_type": "replay_error",
            "network": "contract_fixture",
            "toolchain": "signed_sidecar",
            "version": "pcc-cgmes-v1",
            "natural_case": False,
            "native_pcc_certificate": True,
            "pcc_evidence_mode": "executable_ed25519_contract",
            "decisions": dict(zip(BASELINES, decisions)),
            "pcc_reasons": ";".join(replay.reasons),
            "b6_reasons": ";".join(b6_replay.reasons),
        }
    )
    cert_sizes.append(len(json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")))

    clean_verifier = PCCVerifier(contract_version="pcc-cgmes-v1", trusted_issuers=trusted)
    clean_decision = clean_verifier.verify(source, target, clean, requested_task="PF")
    clean_b6 = provenance_signature_decision(source, target, clean, trusted)
    clean_decisions = ["accept", "accept", "unresolved", "accept", "accept", "accept", clean_b6.status, clean_decision.status]
    results.append(
        {
            "case_id": "contract:clean_lawful_split",
            "case_layer": "lawful_transformation",
            "expected_label": "lawful",
            "error_type": "clean_signed_lawful_split",
            "network": "contract_fixture",
            "toolchain": "signed_sidecar",
            "version": "pcc-cgmes-v1",
            "natural_case": False,
            "native_pcc_certificate": True,
            "pcc_evidence_mode": "executable_ed25519_contract",
            "decisions": dict(zip(BASELINES, clean_decisions)),
            "pcc_reasons": "",
            "b6_reasons": "",
        }
    )

    latencies: list[float] = []
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    perf_verifier = PCCVerifier(
        contract_version="pcc-cgmes-v1",
        trusted_issuers=trusted,
        stateful_replay_protection=False,
    )
    for _ in range(10_000):
        started = time.perf_counter_ns()
        result = perf_verifier.verify(source, target, clean, requested_task="PF", record_replay=False)
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        peak_rss = max(peak_rss, process.memory_info().rss)
        if result.status != ACCEPT:
            raise AssertionError(result)
    latency = pd.Series(latencies)
    performance = {
        "verification_trials": len(latencies),
        "latency_ms_p50": float(latency.quantile(.50)),
        "latency_ms_p95": float(latency.quantile(.95)),
        "latency_ms_p99": float(latency.quantile(.99)),
        "latency_ms_max": float(latency.max()),
        "certificate_bytes_min": min(cert_sizes),
        "certificate_bytes_median": float(pd.Series(cert_sizes).median()),
        "certificate_bytes_max": max(cert_sizes),
        "process_peak_rss_mb": peak_rss / (1024 * 1024),
        "scope": "single-process local verifier microbenchmark; not production service performance",
    }
    return results, performance


def expand(cases: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for case in cases:
        decisions = case.pop("decisions")
        for baseline in BASELINES:
            started = time.perf_counter_ns()
            decision = str(decisions[baseline])
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            if decision not in DECISIONS:
                raise ValueError((baseline, decision))
            expected = case["expected_label"]
            correct = (
                (expected == "lawful" and decision == "accept")
                or (expected == "harmful" and decision == "reject")
            )
            rows.append({**case, "baseline": baseline, "decision": decision, "correct": correct, "decision_latency_ms": elapsed_ms})
    return pd.DataFrame(rows)


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for baseline, group in frame.groupby("baseline", sort=False):
        harmful = group[group.expected_label == "harmful"]
        lawful = group[group.expected_label == "lawful"]
        h_accept = int((harmful.decision == "accept").sum())
        l_reject = int((lawful.decision == "reject").sum())
        h_ci = clopper_pearson(h_accept, len(harmful))
        l_ci = clopper_pearson(l_reject, len(lawful))
        rows.append(
            {
                "baseline": baseline,
                "harmful_n": len(harmful),
                "harmful_false_accepts": h_accept,
                "harmful_FAR": h_accept / len(harmful),
                "harmful_FAR_95CI_low": h_ci[0],
                "harmful_FAR_95CI_high": h_ci[1],
                "lawful_n": len(lawful),
                "lawful_false_rejects": l_reject,
                "lawful_FRR": l_reject / len(lawful),
                "lawful_FRR_95CI_low": l_ci[0],
                "lawful_FRR_95CI_high": l_ci[1],
                "unresolved_n": int((group.decision == "unresolved").sum()),
                "unresolved_rate": float((group.decision == "unresolved").mean()),
                "manual_review_n": int((group.decision == "unresolved").sum()),
                "manual_review_rate": float((group.decision == "unresolved").mean()),
                "error_n": int((group.decision == "error").sum()),
            }
        )
    return pd.DataFrame(rows)


def mcnemar(frame: pd.DataFrame) -> pd.DataFrame:
    labeled = frame[frame.expected_label.isin(["lawful", "harmful"])]
    pivot = labeled.pivot(index="case_id", columns="baseline", values="correct")
    rows = []
    for baseline in BASELINES[:-1]:
        b = pivot[baseline].astype(bool)
        p = pivot["B7_full_pcc"].astype(bool)
        b_wrong_p_right = int((~b & p).sum())
        b_right_p_wrong = int((b & ~p).sum())
        discordant = b_wrong_p_right + b_right_p_wrong
        pvalue = 1.0 if discordant == 0 else float(binomtest(min(b_wrong_p_right, b_right_p_wrong), discordant, .5).pvalue)
        rows.append(
            {
                "comparison": f"{baseline}_vs_B7_full_pcc",
                "baseline_wrong_pcc_right": b_wrong_p_right,
                "baseline_right_pcc_wrong": b_right_p_wrong,
                "discordant_n": discordant,
                "exact_mcnemar_p": pvalue,
            }
        )
    result = pd.DataFrame(rows)
    order = result["exact_mcnemar_p"].sort_values().index.tolist()
    adjusted: dict[int, float] = {}
    running = 0.0
    total = len(order)
    for rank, index in enumerate(order):
        candidate = min(1.0, float(result.loc[index, "exact_mcnemar_p"]) * (total - rank))
        running = max(running, candidate)
        adjusted[index] = running
    result["holm_adjusted_p"] = [adjusted[index] for index in result.index]
    result["analysis_unit_warning"] = (
        "paired case-row analysis; interpret with network/toolchain strata because rows within a network are dependent"
    )
    return result


def main() -> None:
    contract, performance = contract_cases()
    cases = natural_cases() + legacy_semantic_cases() + contract
    frame = expand(cases)
    frame.to_csv(ROOT / "results" / "baseline_comparison_results.csv", index=False)
    summary_frame = summarize(frame)
    summary_frame.to_csv(ROOT / "results" / "baseline_comparison_summary.csv", index=False)
    strata = (
        frame.groupby(["baseline", "case_layer", "expected_label", "decision"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    strata.to_csv(ROOT / "results" / "baseline_comparison_strata.csv", index=False)
    recall = (
        frame[frame.expected_label == "harmful"]
        .assign(detected=lambda x: x.decision.eq("reject"))
        .groupby(["baseline", "error_type"], dropna=False)
        .agg(harmful_n=("detected", "size"), detected_n=("detected", "sum"), recall=("detected", "mean"))
        .reset_index()
    )
    recall.to_csv(ROOT / "results" / "baseline_error_type_recall.csv", index=False)
    paired = mcnemar(frame)
    paired.to_csv(ROOT / "results" / "baseline_mcnemar_results.csv", index=False)
    (ROOT / "results" / "pcc_performance_summary.json").write_text(
        json.dumps(performance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    natural = frame[frame.natural_case.astype(bool)]
    preliminary_gate2 = natural[
        natural.error_type.eq("confirmed_same_mrid_semantic_type_mutation")
    ].pivot(index="case_id", columns="baseline", values="decision")
    gate2_count = int(
        (
            preliminary_gate2["B5_identity_only"].eq("accept")
            & preliminary_gate2["B7_full_pcc"].eq("reject")
        ).sum()
    )
    gate2_path = ROOT / "results" / "full_pcc_identity_only_task_scope_summary.json"
    gate2_task = json.loads(gate2_path.read_text(encoding="utf-8")) if gate2_path.is_file() else {}
    gate2_verified = bool(gate2_task.get("gate2_met", False))
    summary = {
        "case_count": int(frame.case_id.nunique()),
        "decision_count": len(frame),
        "baseline_count": len(BASELINES),
        "case_layer_counts": frame.drop_duplicates("case_id").case_layer.value_counts().to_dict(),
        "expected_label_counts": frame.drop_duplicates("case_id").expected_label.value_counts().to_dict(),
        "natural_case_count": int(frame[frame.natural_case.astype(bool)].case_id.nunique()),
        "all_eight_frozen_baselines_present": set(frame.baseline) == set(BASELINES),
        "gate2_preliminary_identity_only_accept_full_pcc_reject_natural_cases": gate2_count,
        "gate2_downstream_task_effect_verified": gate2_verified,
        "gate2_task_scope_result_path": gate2_path.relative_to(ROOT).as_posix() if gate2_path.is_file() else "",
        "gate2_status": (
            "positive_task_candidate_misclassification_without_safety_reversal_claim"
            if gate2_verified
            else "preliminary_semantic_separation_only_pending_stage3_operational_replay"
        ),
        "native_tool_pcc_certificate_count_natural": int(
            natural[natural.native_pcc_certificate.astype(bool)].case_id.nunique()
        ),
        "sidecar_disclosure": (
            "Natural-tool outputs did not natively emit PCC certificates. B7 natural decisions evaluate "
            "a post-conversion adapter sidecar against frozen mapping evidence and must not be described as tool-native."
        ),
        "performance": performance,
    }
    (ROOT / "results" / "baseline_comparison_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(summary_frame.to_string(index=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
