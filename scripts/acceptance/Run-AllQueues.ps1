<#
.SYNOPSIS
Run all default Tier 0 WorkQueues sequentially. Direct calls (no nested Jobs).
Exit: 0=PASS, 1=BLOCKED/ESCALATED, 2=FAILED
#>
param(
    [string[]]$QueueFiles = @(
        'agent-workqueue/local-quality.queue.json',
        'agent-workqueue/docs-quality.queue.json',
        'agent-workqueue/recovery-regression.queue.json',
        'agent-workqueue/release-readiness.queue.json',
        'agent-workqueue/cleanup-dryrun.queue.json'
    ),
    [string]$RunsBase = 'runs/powershell-acceptance/workqueue/all-queues'
)

$ErrorActionPreference = 'Continue'
$script:allStart = Get-Date
$allDir = $RunsBase
New-Item -ItemType Directory -Force -Path $allDir | Out-Null

$runner = Join-Path $PSScriptRoot 'Run-WorkQueue.ps1'
$queueResults = [System.Collections.ArrayList]::new()

foreach ($qf in $QueueFiles) {
    if (-not (Test-Path $qf)) {
        Write-Host "SKIP: $qf not found"
        [void]$queueResults.Add(@{ queue = $qf; exit_code = -1; verdict = 'SKIPPED'; reason = 'file not found' })
        continue
    }
    Write-Host "`n=== Queue: $qf ==="
    $t0 = Get-Date
    try {
        $prevEC = $global:LASTEXITCODE
        powershell -ExecutionPolicy Bypass -File $runner -QueueFile $qf 2>&1
        $ec = if ($global:LASTEXITCODE) { $global:LASTEXITCODE } else { 0 }
        $global:LASTEXITCODE = 0
    } catch {
        $ec = 2
        Write-Host "ERROR: $($_.Exception.Message)"
    }
    $ts = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    $verdict = if ($ec -eq 0) { 'PASS' } elseif ($ec -eq 1) { 'BLOCKED' } elseif ($ec -lt 0) { 'SKIPPED' } else { 'FAILED' }
    [void]$queueResults.Add(@{ queue = $qf; exit_code = $ec; verdict = $verdict; duration = $ts; reason = '' })
    Write-Host "  Exit: $ec ($verdict) ${ts}s"
}

# ---- Combined report ----
$elapsed = [math]::Round(((Get-Date) - $script:allStart).TotalSeconds, 1)
$passed = ($queueResults | Where-Object { $_.verdict -eq 'PASS' }).Count
$blocked = ($queueResults | Where-Object { $_.verdict -eq 'BLOCKED' }).Count
$failed = ($queueResults | Where-Object { $_.verdict -eq 'FAILED' }).Count
$skipped = ($queueResults | Where-Object { $_.verdict -eq 'SKIPPED' }).Count
$total = $queueResults.Count

$lines = @()
$lines += "# All Queues Report"; $lines += ""
$lines += "**Time**: $(Get-Date -Format 'o')"
$lines += "**Duration**: ${elapsed}s"; $lines += ""
$lines += "## Executive Decision"; $lines += ""
if ($failed -gt 0) { $lines += 'FAILED. Escalate to reviewer.' }
elseif ($blocked -gt 0) { $lines += 'BLOCKED. Reviewer should check blocked queues.' }
else { $lines += 'PASS. All queues passed. Ready for release gate.' }
$lines += ""
$lines += "## Summary"; $lines += "PASS=$passed BLOCKED=$blocked FAILED=$failed SKIPPED=$skipped TOTAL=$total"
$lines += ""
$lines += "## Queue Results"; $lines += ""
$lines += "| # | Queue | Exit | Verdict | Duration |"
$lines += "|---|-------|------|---------|----------|"
for ($i = 0; $i -lt $total; $i++) {
    $r = $queueResults[$i]
    $lines += "| $($i+1) | $($r.queue) | $($r.exit_code) | $($r.verdict) | $($r.duration)s |"
}
$lines += ""
$lines += "## Next Action"
if ($failed -gt 0) { $lines += 'Stop. Escalate failed queues to reviewer.' }
elseif ($blocked -gt 0) { $lines += 'Review blocked queues.' }
else { $lines += 'All clear. Ready for next stage.' }

$rptPath = Join-Path $allDir 'all-queues-report.md'
($lines -join "`n") | Out-File -FilePath $rptPath -Encoding utf8

$allResult = @{
    timestamp = (Get-Date -Format 'o')
    passed = $passed; blocked = $blocked; failed = $failed; skipped = $skipped; total = $total
    duration = $elapsed
    queues = @($queueResults)
    report_path = $rptPath
} | ConvertTo-Json -Depth 3
$allResult | Out-File (Join-Path $allDir 'all-queues-result.json') -Encoding utf8

Write-Host "`nAll Queues Report: $rptPath"
Write-Host "PASS=$passed BLOCKED=$blocked FAILED=$failed"

if ($failed -gt 0) { exit 2 }
if ($blocked -gt 0) { exit 1 }
exit 0
