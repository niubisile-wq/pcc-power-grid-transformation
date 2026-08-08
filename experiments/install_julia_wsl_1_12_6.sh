#!/usr/bin/env bash
set -euo pipefail

version="1.12.6"
archive="julia-${version}-linux-x86_64.tar.gz"
expected_sha256="bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
cache_dir="/root/.cache/julia"
install_root="/root/.local"

mkdir -p "${cache_dir}" "${install_root}/bin"
cd "${cache_dir}"
curl -fL --retry 5 --retry-delay 5 -C - \
  -o "${archive}" \
  "https://julialang-s3.julialang.org/bin/linux/x64/1.12/${archive}"
actual_sha256="$(sha256sum "${archive}")"
actual_sha256="${actual_sha256%% *}"
if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
  echo "SHA-256 mismatch: ${actual_sha256}" >&2
  exit 2
fi
tar -xzf "${archive}" -C "${install_root}"
ln -sfn "${install_root}/julia-${version}/bin/julia" "${install_root}/bin/julia"
"${install_root}/bin/julia" --version
