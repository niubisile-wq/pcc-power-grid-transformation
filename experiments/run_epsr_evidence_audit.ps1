param(
    [switch]$RequireSubmissionReady
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = 'C:\Windows\py.exe'
$pythonArgs = @('-3.12')
$output = Join-Path $repo 'outputs\epsr_clean_room_audit'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$started = Get-Date
$env:PYTHONPATH = (Resolve-Path (Join-Path $repo 'cgmes')).Path

$steps = @()
function Invoke-AuditStep {
    param([string]$Name, [scriptblock]$Command)
    $stepStarted = Get-Date
    try {
        & $Command
        if ($LASTEXITCODE -ne 0) {
            throw "exit code $LASTEXITCODE"
        }
        $script:steps += [pscustomobject]@{
            name = $Name
            status = 'pass'
            elapsed_seconds = ((Get-Date) - $stepStarted).TotalSeconds
            error = $null
        }
    }
    catch {
        $script:steps += [pscustomobject]@{
            name = $Name
            status = 'fail'
            elapsed_seconds = ((Get-Date) - $stepStarted).TotalSeconds
            error = $_.Exception.Message
        }
        throw
    }
}

try {
    Invoke-AuditStep 'semantic_confirmatory_lock_v2' {
        & $python @pythonArgs (Join-Path $repo 'experiments\verify_semantic_confirmatory_lock_v2.py')
    }
    Invoke-AuditStep 'regression_suite' {
        & $python @pythonArgs -m unittest discover -s (Join-Path $repo 'cgmes\tests')
    }
    Invoke-AuditStep 'dc_scopf_statistics_rebuild' {
        & $python @pythonArgs (Join-Path $repo 'experiments\run_dc_scopf_confirmatory_statistics.py')
    }
    Invoke-AuditStep 'dc_scopf_mechanism_atlas_rebuild' {
        & $python @pythonArgs (Join-Path $repo 'experiments\build_dc_scopf_mechanism_atlas.py')
    }
    Invoke-AuditStep 'pcc_decision_reason_taxonomy_rebuild' {
        & $python @pythonArgs (Join-Path $repo 'experiments\build_pcc_decision_reason_taxonomy.py')
    }
    Invoke-AuditStep 'external_tool_consequence_adjudication_rebuild' {
        & $python @pythonArgs (Join-Path $repo 'experiments\run_external_tool_consequence_adjudication.py')
    }
    Invoke-AuditStep 'evidence_dashboard_rebuild' {
        & $python @pythonArgs (Join-Path $repo 'experiments\build_epsr_evidence_dashboard.py')
    }
    Invoke-AuditStep 'manuscript_tables_rebuild' {
        & $python @pythonArgs (Join-Path $repo 'experiments\build_epsr_manuscript_tables.py')
    }
    Invoke-AuditStep 'dc_scopf_confirmatory_lock_v2' {
        & $python @pythonArgs (Join-Path $repo 'experiments\manage_dc_scopf_confirmatory_lock_v2.py')
    }
    $dashboard = Get-Content -LiteralPath (Join-Path $repo 'outputs\epsr_evidence_dashboard\epsr_evidence_dashboard.json') -Raw | ConvertFrom-Json
    if ($RequireSubmissionReady -and -not $dashboard.submission_ready) {
        throw "submission gate is open: $($dashboard.ready_gates)/$($dashboard.total_gates) ready"
    }
    $status = 'pass'
    $errorMessage = $null
}
catch {
    $status = 'fail'
    $errorMessage = $_.Exception.Message
}

$summary = [ordered]@{
    protocol = 'epsr_evidence_audit_v1'
    started_at = $started.ToString('o')
    completed_at = (Get-Date).ToString('o')
    elapsed_seconds = ((Get-Date) - $started).TotalSeconds
    python = $python
    python_args = $pythonArgs
    require_submission_ready = [bool]$RequireSubmissionReady
    status = $status
    error = $errorMessage
    steps = $steps
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'audit_summary.json') -Encoding UTF8
$summary | ConvertTo-Json -Depth 8
if ($status -ne 'pass') {
    exit 1
}
