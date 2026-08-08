$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $repositoryRoot 'cgmes\corpus\holdout\powsybl-core-4e8024eaf07a43673c68226aefc8b57dae4c4ffb.tar.gz'
$download = $target + '.complete-download'
$url = 'https://github.com/powsybl/powsybl-core/archive/4e8024eaf07a43673c68226aefc8b57dae4c4ffb.tar.gz'
& curl.exe -fL --retry 5 --retry-delay 5 -o $download $url
if ($LASTEXITCODE -ne 0) {
    throw "curl failed with exit code $LASTEXITCODE"
}
& tar.exe -tzf $download *> $null
if ($LASTEXITCODE -ne 0) {
    throw "downloaded archive failed tar integrity check"
}
Move-Item -LiteralPath $download -Destination $target -Force
$item = Get-Item -LiteralPath $target
$hash = Get-FileHash -LiteralPath $target -Algorithm SHA256
Write-Output "bytes=$($item.Length)"
Write-Output "sha256=$($hash.Hash.ToLowerInvariant())"
