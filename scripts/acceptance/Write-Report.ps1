<#
.SYNOPSIS
Write acceptance report from results + artifacts.
Used by Run-Smoke.ps1 and Run-Flow.ps1 as a post-process step.
#>
param(
    [Parameter(Mandatory)]
    [string]$ReportDir,

    [Parameter(Mandatory)]
    [array]$Results,

    [string]$SuiteName = 'acceptance',

    [string[]]$ArtifactPaths = @(),

    [string]$ExplorerNote = "Explorer: not run, browser automation deferred"
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$passed = ($Results | Where-Object status -eq 'PASS').Count
$blocked = ($Results | Where-Object status -eq 'BLOCKED').Count
$failed = ($Results | Where-Object status -eq 'FAILED').Count
$total = $Results.Count

# ---- Markdown report ----
$now = Get-Date -Format 'o'
$md = @"
# Acceptance Report: $SuiteName

**Time**: $now

## Summary
PASS=$passed BLOCKED=$blocked FAILED=$failed TOTAL=$total

## Results

| # | Flow | Status | Detail |
|---|------|--------|--------|
$(
    for ($i = 0; $i -lt $Results.Count; $i++) {
        $r = $Results[$i]
        "| $($i+1) | $($r.flow) | $($r.status) | $($r.detail) |"
    }
)

## Implementation
All checks that ran without runtime/backend dependency.

## Runtime
Checks that require running code, tests, or commands.

## Explorer
$ExplorerNote

## Artifacts
$(
    if ($ArtifactPaths.Count -eq 0) {
        '(none)'
    } else {
        ($ArtifactPaths | ForEach-Object { "- ``$_``" }) -join "`n"
    }
)

## Verdict
$(
    if ($failed -gt 0) { 'FAILED' }
    elseif ($blocked -gt 0) { 'BLOCKED' }
    else { 'PASS' }
)
"@

$reportPath = Join-Path $ReportDir 'acceptance-report.md'
$md | Out-File -FilePath $reportPath -Encoding utf8

# ---- JSON results ----
$json = @{
    suite = $SuiteName
    timestamp = $now
    passed = $passed
    blocked = $blocked
    failed = $failed
    total = $total
    results = @($Results)
    report_path = $reportPath
    artifact_paths = @($ArtifactPaths)
} | ConvertTo-Json -Depth 3

$jsonPath = Join-Path $ReportDir 'acceptance-result.json'
$json | Out-File -FilePath $jsonPath -Encoding utf8

Write-Host "Report: $reportPath"
Write-Host "JSON:   $jsonPath"

return @{
    ReportPath = $reportPath
    JsonPath = $jsonPath
}
