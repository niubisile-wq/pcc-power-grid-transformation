#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="${repo_root}/julia/cross_solver"
julia="/root/.local/bin/julia"
export JULIA_NUM_THREADS=1
export JULIA_NUM_PRECOMPILE_TASKS=1

"${julia}" --project="${project}" -e '
using Pkg
Pkg.instantiate()
Pkg.precompile()
Pkg.status()
'
