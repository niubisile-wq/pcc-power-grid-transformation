#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="${repo_root}/julia/cross_solver"
export JULIA_NUM_THREADS=1
export JULIA_NUM_PRECOMPILE_TASKS=1

/root/.local/bin/julia --project="${project}" -e '
using Pkg
Pkg.add("HiGHS")
Pkg.precompile()
Pkg.status()
'
