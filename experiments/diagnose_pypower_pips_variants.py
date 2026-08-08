from __future__ import annotations

import json

import numpy as np
from pypower.api import ppoption, rundcopf
from pypower.idx_bus import PD, QD

from run_cross_solver_powermodels import CASES, SCALES, matrix


def load_case(path, scale: float) -> dict:
    import re

    text = path.read_text(encoding="utf-8", errors="replace")
    base = re.search(r"mpc\.baseMVA\s*=\s*([0-9.eE+-]+)", text)
    case = {
        "version": "2",
        "baseMVA": float(base.group(1)),
        "bus": np.asarray(matrix(text, "bus"), dtype=float),
        "gen": np.asarray(matrix(text, "gen"), dtype=float),
        "branch": np.asarray(matrix(text, "branch"), dtype=float),
        "gencost": np.asarray(matrix(text, "gencost"), dtype=float),
    }
    case["bus"][:, PD] *= scale
    case["bus"][:, QD] *= scale
    return case


def main() -> None:
    rows = []
    variants = {
        "pips_default": ppoption(VERBOSE=0, OUT_ALL=0, OPF_ALG_DC=200),
        "pips_step_control": ppoption(VERBOSE=0, OUT_ALL=0, OPF_ALG_DC=250),
        "pips_ignore_angle_limits": ppoption(
            VERBOSE=0, OUT_ALL=0, OPF_ALG_DC=200, OPF_IGNORE_ANG_LIM=True
        ),
        "pips_strict": ppoption(
            VERBOSE=0,
            OUT_ALL=0,
            OPF_ALG_DC=200,
            PDIPM_FEASTOL=1e-10,
            PDIPM_GRADTOL=1e-10,
            PDIPM_COMPTOL=1e-10,
            PDIPM_COSTTOL=1e-10,
            PDIPM_MAX_IT=300,
        ),
    }
    for network, path in CASES.items():
        for scale in SCALES:
            for variant, options in variants.items():
                result = rundcopf(load_case(path, scale), options)
                rows.append({
                    "network": network,
                    "scale": scale,
                    "variant": variant,
                    "success": bool(result["success"]),
                    "objective": float(result["f"]),
                    "total_generation_mw": float(np.sum(result["gen"][:, 1])),
                })
    output = CASES["case39"].parents[2] / "outputs" / "cross_solver_validation" / "pypower_pips_variant_diagnostic.json"
    output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
