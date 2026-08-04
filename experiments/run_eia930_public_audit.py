"""Fetch official EIA-930 hourly operating data and run a profile stress test.

The EIA data are balancing-area aggregates.  They are intentionally injected
into a separate public benchmark topology and are not presented as PJM
node-level measurements.
"""
from __future__ import annotations

import copy
import contextlib
import csv
import hashlib
import io
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd
import pandapower as pp
import simbench as sb

ROOT = Path(__file__).resolve().parent
OUTDIR = ROOT / "model_assets" / "real_time_series"
CODE = "1-HVMVLV-urban-all-0-sw"
API = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
START, END, RESPONDENT = "2024-01-01", "2024-12-31", "PJM"
TYPES = {"D": "demand_mwh", "NG": "net_generation_mwh", "TI": "net_interchange_mwh"}
SEED, N_SNAPSHOTS = 20260801, 200


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(kind: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        params = {
            "api_key": "DEMO_KEY", "frequency": "hourly", "data[0]": "value",
            "facets[respondent][0]": RESPONDENT, "facets[type][0]": kind,
            "start": START, "end": END, "sort[0][column]": "period",
            "sort[0][direction]": "asc", "offset": str(offset), "length": "5000",
        }
        url = API + "?" + urlencode(params)
        # curl is used here because the Windows Python TLS stack occasionally
        # resets this public endpoint while the same request is stable in curl.
        proc = subprocess.run(["curl.exe", "-L", "--fail", "--retry", "3", "--max-time", "120", "-sS", url],
                              check=True, capture_output=True)
        payload = json.loads(proc.stdout.decode("utf-8"))
        batch = payload["response"]["data"]
        rows.extend(batch)
        if len(rows) >= int(payload["response"]["total"]) or not batch:
            break
        offset += len(batch)
    for row in rows:
        row["period"] = pd.to_datetime(row["period"], utc=True).isoformat()
        row["value"] = float(row["value"]) if row["value"] is not None else None
    return rows


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    raw_rows = []
    for kind, name in TYPES.items():
        for row in fetch(kind):
            raw_rows.append({"period": row["period"], "type": kind, "metric": name,
                             "value": row["value"], "respondent": row.get("respondent"),
                             "respondent_name": row.get("respondent-name"),
                             "value_units": row.get("value-units")})
    raw = pd.DataFrame(raw_rows).sort_values(["period", "type"])
    raw_file = OUTDIR / "eia930_pjm_2024_hourly_operating_data.csv"
    raw.to_csv(raw_file, index=False)
    demand = raw[raw["type"] == "D"][["period", "value"]].rename(columns={"value": "demand_mwh"})
    demand = demand.dropna().reset_index(drop=True)
    median = float(demand["demand_mwh"].median())
    demand["relative_to_median"] = demand["demand_mwh"] / median
    demand["injected_factor"] = demand["relative_to_median"].clip(0.75, 1.25)
    rng = np.random.default_rng(SEED)
    idx = np.sort(rng.choice(len(demand), size=min(N_SNAPSHOTS, len(demand)), replace=False))
    chosen = demand.iloc[idx]
    base = sb.get_simbench_net(CODE)
    rows = []
    for _, rec in chosen.iterrows():
        net = copy.deepcopy(base)
        factor = float(rec["injected_factor"])
        net.load["p_mw"] *= factor
        net.load["q_mvar"] *= factor
        t0 = time.perf_counter()
        row = {"period": rec["period"], "pjm_demand_mwh": float(rec["demand_mwh"]),
               "relative_to_median": float(rec["relative_to_median"]),
               "injected_factor": factor, "converged": False, "min_vm_pu": None,
               "max_line_loading_percent": None, "runtime_s": None, "error": None}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                pp.runpp(net, algorithm="nr", init="dc", calculate_voltage_angles=True,
                         max_iteration=80, tolerance_mva=1e-8, trafo_model="t")
            row["converged"] = True
            row["min_vm_pu"] = float(net.res_bus.vm_pu.min())
            row["max_line_loading_percent"] = float(net.res_line.loading_percent.max()) if len(net.res_line) else None
        except Exception as exc:
            row["error"] = type(exc).__name__ + ": " + str(exc)[:180]
        row["runtime_s"] = time.perf_counter() - t0
        rows.append(row)
    out_csv = ROOT / "eia930_pjm_profile_injection_results_20260801.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    ok = [r for r in rows if r["converged"]]
    summary = {
        "dataset": "EIA-930 Hourly Electric Grid Monitor, PJM, 2024",
        "api_url": API,
        "query": {"respondent": RESPONDENT, "start": START, "end": END, "types": list(TYPES)},
        "raw_csv_sha256": sha256(raw_file), "raw_rows": len(raw),
        "demand_rows": len(demand), "demand_median_mwh": median,
        "demand_min_mwh": float(demand.demand_mwh.min()), "demand_max_mwh": float(demand.demand_mwh.max()),
        "benchmark": {"simbench_code": CODE, "buses": len(base.bus), "loads": len(base.load), "lines": len(base.line)},
        "sampling": {"seed": SEED, "requested": N_SNAPSHOTS, "used": len(rows), "factor_clip": [0.75, 1.25]},
        "convergence": {"n_converged": len(ok), "n_failed": len(rows)-len(ok), "rate": len(ok)/len(rows) if rows else 0.0},
        "converged_min_vm_pu": {"min": float(min(r["min_vm_pu"] for r in ok)) if ok else None,
                                 "median": float(np.median([r["min_vm_pu"] for r in ok])) if ok else None},
        "converged_max_line_loading_percent": {"max": float(max(r["max_line_loading_percent"] for r in ok)) if ok else None,
                                                 "median": float(np.median([r["max_line_loading_percent"] for r in ok])) if ok else None},
        "interpretation": "official PJM balancing-area operating aggregates injected into an unrelated public SimBench topology; not PJM node-level validation",
    }
    (ROOT / "eia930_pjm_profile_injection_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
