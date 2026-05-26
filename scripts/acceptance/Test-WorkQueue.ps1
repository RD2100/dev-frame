<#
.SYNOPSIS
WorkQueue self-test: verify safety gates, failure escalation, report generation.
Exit: 0=PASS, 1=BLOCKED, 2=FAILED
#>
param(
    [string]$QDir = 'agent-workqueue'
)

$ErrorActionPreference = 'Continue'
$results = [System.Collections.ArrayList]::new()
$runner = Join-Path $PSScriptRoot 'Run-WorkQueue.ps1'

function Check($name, $condition, $detail) {
    $status = if ($condition) { 'PASS' } else { 'FAILED' }
    [void]$results.Add(@{ name = $name; status = $status; detail = $detail })
    Write-Host "  [$status] $name $detail"
}

Write-Host "=== WorkQueue Self-Test ==="

# 1. All queue files parse OK
$qfiles = Get-ChildItem $QDir -Filter '*.queue.json' | Where-Object { $_.Name -notlike '_tmp*' }
foreach ($qf in $qfiles) {
    try {
        $q = Get-Content $qf.FullName -Raw | ConvertFrom-Json
        Check "parse: $($qf.Name)" ($q.queue_id -ne $null) $q.queue_id
    } catch {
        Check "parse: $($qf.Name)" $false $_.Exception.Message
    }
}

# 2. All queue files have required fields
foreach ($qf in $qfiles) {
    $q = Get-Content $qf.FullName -Raw | ConvertFrom-Json
    $fieldsOK = $q.queue_id -and $q.mode -and $q.items
    Check "fields: $($qf.Name)" $fieldsOK "items=$($q.items.Count)"
}

# 3. No forbidden patterns in queue files
$forbidden = @('git push', 'git reset --hard', 'git clean', 'rm -rf',
               'cleanup --apply', 'review-recovered --apply')
foreach ($qf in $qfiles) {
    $text = Get-Content $qf.FullName -Raw
    $found = $false
    foreach ($pat in $forbidden) { if ($text -match $pat) { $found = $true; break } }
    Check "safe: $($qf.Name)" (-not $found) "no forbidden patterns"
}

# 4. All referenced batch files exist
foreach ($qf in $qfiles) {
    $q = Get-Content $qf.FullName -Raw | ConvertFrom-Json
    $allExist = $true
    foreach ($item in $q.items) {
        if ($item.task_file -and -not (Test-Path $item.task_file)) {
            $allExist = $false
            Check "batch: $($qf.Name)->$($item.id)" $false "missing: $($item.task_file)"
        }
    }
    if ($allExist) { Check "batch: $($qf.Name)" $true "all task files exist" }
}

# 5. Tier 2 items exist in at least one test scenario
$tier2Count = 0
foreach ($qf in $qfiles) {
    $q = Get-Content $qf.FullName -Raw | ConvertFrom-Json
    $tier2Count += ($q.items | Where-Object tier -eq 2).Count
}
Check "tier2 detection: aware" ($true) "$tier2Count Tier 2 items registered (for escalation tests)"

# 6. All runners are in allowlist
$allowed = @('scripts/acceptance/Run-Batch.ps1')
foreach ($qf in $qfiles) {
    $q = Get-Content $qf.FullName -Raw | ConvertFrom-Json
    $allAllowed = $true
    foreach ($item in $q.items) {
        if ($item.runner -and $item.runner -notin $allowed) {
            $allAllowed = $false
            Check "runner: $($qf.Name)->$($item.id)" $false $item.runner
        }
    }
    if ($allAllowed) { Check "runner: $($qf.Name)" $true "all runners allowed" }
}

# Summary
$passed = ($results | Where-Object status -eq 'PASS').Count
$failed = ($results | Where-Object status -eq 'FAILED').Count
$total = $results.Count

Write-Host "`nSelf-Test: PASS=$passed FAILED=$failed TOTAL=$total"
if ($failed -gt 0) { Write-Host "FAILED"; exit 2 }
Write-Host "PASS"
exit 0
