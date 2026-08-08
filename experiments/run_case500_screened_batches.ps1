param(
    [ValidateRange(0,9)]
    [int]$StartOffset = 0,
    [ValidateRange(1,10)]
    [int]$StateCount = 10,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repo '.venv_pcc_v2\Scripts\python.exe'
$runner = Join-Path $repo 'experiments\run_pcc_v2_dc_scopf_case500_screened.py'
if ($StartOffset + $StateCount -gt 10) {
    throw 'StartOffset + StateCount exceeds the frozen ten-state grid.'
}
$env:PYTHONPATH = (Resolve-Path (Join-Path $repo 'cgmes')).Path
$env:PYTHONWARNINGS = 'ignore'
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
foreach ($offset in $StartOffset..($StartOffset + $StateCount - 1)) {
    Write-Host "RUN screened case=case500 offset=$offset"
    $arguments = @($runner, '--state-offset', $offset)
    if ($Force) { $arguments += '--force' }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Screened case500 state failed: offset=$offset exit=$LASTEXITCODE"
    }
}
