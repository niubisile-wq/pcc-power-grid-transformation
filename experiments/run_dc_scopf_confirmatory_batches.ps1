param(
    [ValidateSet('case39','case73','case118','case300','case500')]
    [string[]]$Cases = @('case39','case73','case118','case300','case500'),
    [ValidateRange(0,9)]
    [int]$StartOffset = 0,
    [ValidateRange(1,10)]
    [int]$StateCount = 10,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repo '.venv_pcc_v2\Scripts\python.exe'
$experiment = Join-Path $repo 'experiments\run_pcc_v2_dc_scopf_gate.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing isolated Python environment: $python"
}
if ($StartOffset + $StateCount -gt 10) {
    throw 'StartOffset + StateCount exceeds the frozen ten-state grid.'
}

$env:PYTHONPATH = (Resolve-Path (Join-Path $repo 'cgmes')).Path
$env:PYTHONWARNINGS = 'ignore'

foreach ($case in $Cases) {
    foreach ($offset in $StartOffset..($StartOffset + $StateCount - 1)) {
        $summary = Join-Path $repo "outputs\pcc_v2_dc_scopf_gate\dc_scopf_gate_all_${case}_offset${offset}_1states_summary.json"
        if ((-not $Force) -and (Test-Path -LiteralPath $summary)) {
            $prior = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
            if (
                $prior.loader_revision -eq 'pglib-pypsa-transformer-explicit-v2' -and
                $prior.result_schema -eq 'pcc-v2-dc-scopf-result-v2' -and
                $prior.failed_states -eq 0 -and
                $prior.rows -gt 0
            ) {
                Write-Host "SKIP complete case=$case offset=$offset rows=$($prior.rows)"
                continue
            }
        }
        Write-Host "RUN case=$case offset=$offset"
        & $python $experiment `
            --cases $case `
            --states 1 `
            --state-offset $offset `
            --candidate-mode all
        if ($LASTEXITCODE -ne 0) {
            throw "DC-SCOPF batch failed: case=$case offset=$offset exit=$LASTEXITCODE"
        }
        $current = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
        if ($current.failed_states -ne 0 -or $current.rows -le 0) {
            Write-Error "DC-SCOPF state retained as failed: case=$case offset=$offset"
        }
    }
}
