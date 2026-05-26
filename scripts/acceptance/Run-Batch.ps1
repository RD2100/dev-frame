<#
.SYNOPSIS
PowerShell Batch Acceptance Runner
Runs tasks from a JSON manifest. Each task gets its own result dir.
Exit: 0=PASS, 1=BLOCKED, 2=FAILED
#>
param(
    [Parameter(Mandatory)]
    [string]$TaskFile,

    [string]$RunsBase = 'runs/powershell-acceptance',

    [int]$DefaultTimeout = 120
)

$ErrorActionPreference = 'Continue'
$script:batchStart = Get-Date

# ---- Forbidden command patterns ----
$script:forbidden = @(
    'git push', 'git reset --hard', 'git clean',
    'Remove-Item -Recurse', 'rm -rf',
    'cleanup --apply', 'review-recovered --apply',
    'AIHUB_PLANNER_TIMEOUT_SECONDS', 'AIHUB_SYSTEM_TIMEOUT_SECONDS'
)

function IsForbidden($cmd) {
    foreach ($pat in $script:forbidden) {
        if ($cmd -match $pat) { return $true }
    }
    return $false
}

# ---- Load manifest ----
if (-not (Test-Path $TaskFile)) {
    Write-Host "FATAL: task file not found: $TaskFile"
    exit 2
}
$manifest = Get-Content $TaskFile -Raw | ConvertFrom-Json
$batchId = $manifest.batch_id
$tasks = $manifest.tasks
$batchDir = Join-Path $RunsBase $batchId
New-Item -ItemType Directory -Force -Path $batchDir | Out-Null

Write-Host "=== Batch: $batchId ==="
Write-Host "Tasks: $($tasks.Count) | Mode: $($manifest.mode)"
Write-Host "Output: $batchDir"
Write-Host ""

# ---- Execute tasks ----
$taskResults = [System.Collections.ArrayList]::new()
foreach ($task in $tasks) {
    $tid = $task.id
    $tdir = Join-Path $batchDir $tid
    New-Item -ItemType Directory -Force -Path $tdir | Out-Null

    Write-Host "[$tid] $($task.title) ..." -NoNewline
    $t0 = Get-Date

    # Forbidden check
    $cmd = $task.command
    if (IsForbidden $cmd) {
        $ts = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
        Write-Host " [BLOCKED] forbidden command"
        [void]$taskResults.Add(@{
            id = $tid; title = $task.title; tier = $task.tier
            exit_code = -1; verdict = 'BLOCKED'
            duration = $ts; reason = 'forbidden command pattern detected'
            report_path = ''
        })
        "BLOCKED: forbidden command" | Out-File (Join-Path $tdir 'stderr.log')
        continue
    }

    # Timeout
    $timeout = if ($task.timeout_seconds) { $task.timeout_seconds } else { $DefaultTimeout }

    # Execute
    try {
        $job = Start-Job -ScriptBlock {
            param($c, $d, $p)
            Set-Location $p
            Invoke-Expression $c 2>&1 | Out-File (Join-Path $d 'stdout.log')
        } -ArgumentList $cmd, $tdir, (Get-Location).Path

        $done = Wait-Job $job -Timeout $timeout
        if (-not $done) {
            Stop-Job $job -PassThru | Remove-Job -Force
            $ts = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
            Write-Host " [FAILED] timeout after ${timeout}s"
            [void]$taskResults.Add(@{
                id = $tid; title = $task.title; tier = $task.tier
                exit_code = -1; verdict = 'FAILED'
                duration = $ts; reason = "timeout after ${timeout}s"
                report_path = ''
            })
            "FAILED: timeout after ${timeout}s" | Out-File (Join-Path $tdir 'stderr.log')
            continue
        }

        Receive-Job $job 2>&1 | Out-Null
        $ec = $job.ChildJobs[0].JobStateInfo.State
        Remove-Job $job -Force

        $ts = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)

        # Determine verdict
        $actualExit = if ($LASTEXITCODE) { $LASTEXITCODE } else { 0 }
        $expected = $task.expected_exit_codes
        if ($actualExit -in $expected) {
            $verdict = if ($actualExit -eq 0) { 'PASS' } else { 'BLOCKED' }
        } else {
            $verdict = 'FAILED'
        }

        # Check required artifacts
        foreach ($art in $task.required_artifacts) {
            $ap = Join-Path $tdir $art
            if (-not (Test-Path $ap)) {
                $verdict = 'FAILED'
            }
        }

        Write-Host " [$verdict] exit=$actualExit ${ts}s"
        [void]$taskResults.Add(@{
            id = $tid; title = $task.title; tier = $task.tier
            exit_code = $actualExit; verdict = $verdict
            duration = $ts; reason = ''
            report_path = Join-Path $tdir 'stdout.log'
        })
    } catch {
        $ts = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
        Write-Host " [FAILED] exception: $($_.Exception.Message)"
        [void]$taskResults.Add(@{
            id = $tid; title = $task.title; tier = $task.tier
            exit_code = -1; verdict = 'FAILED'
            duration = $ts; reason = $_.Exception.Message
            report_path = ''
        })
        $_.Exception.Message | Out-File (Join-Path $tdir 'stderr.log')
    }

    $LASTEXITCODE = 0  # reset after each task
}

# ---- Batch report ----
$elapsed = [math]::Round(((Get-Date) - $script:batchStart).TotalSeconds, 1)
$passed = ($taskResults | Where-Object { $_.verdict -eq 'PASS' }).Count
$blocked = ($taskResults | Where-Object { $_.verdict -eq 'BLOCKED' }).Count
$failed = ($taskResults | Where-Object { $_.verdict -eq 'FAILED' }).Count
$total = $taskResults.Count

$lines = @()
$lines += "# Batch Report: $batchId"; $lines += ""
$lines += "**Time**: $(Get-Date -Format 'o')"
$lines += "**Duration**: ${elapsed}s"
$lines += "**Mode**: $($manifest.mode)"; $lines += ""
$lines += "## Executive Decision"; $lines += ""
if ($failed -gt 0) { $lines += 'FAILED — one or more tasks failed. See Task Matrix below.' }
elseif ($blocked -gt 0) { $lines += 'BLOCKED — some pre-flight tasks blocked. Review blocked items.' }
else { $lines += 'PASS — all tasks passed.' }
$lines += ""
$lines += "## Summary"; $lines += "PASS=$passed BLOCKED=$blocked FAILED=$failed TOTAL=$total"
$lines += ""
$lines += "## Task Matrix"; $lines += ""
$lines += "| # | Task ID | Tier | Exit | Verdict | Duration | Notes |"
$lines += "|---|---------|------|------|---------|----------|-------|"
for ($i = 0; $i -lt $total; $i++) {
    $r = $taskResults[$i]
    $notes = if ($r.reason) { $r.reason } else { '-' }
    $lines += "| $($i+1) | $($r.id) | $($r.tier) | $($r.exit_code) | $($r.verdict) | $($r.duration)s | $notes |"
}
$lines += ""
$lines += "## Failed/Blocked Summary"
$blockedFailed = $taskResults | Where-Object { $_.verdict -in @('FAILED', 'BLOCKED') }
if ($blockedFailed) {
    foreach ($r in $blockedFailed) {
        $lines += "- **$($r.id)**: $($r.verdict) — $($r.reason)"
    }
} else {
    $lines += "(none)"
}
$lines += ""
$lines += "## Artifacts"; $lines += "- Batch dir: $batchDir"
$lines += "## Next Action"
if ($failed -gt 0) { $lines += 'Review failed tasks. Escalate to GPT-5.5 for diagnosis.' }
elseif ($blocked -gt 0) { $lines += 'Review blocked tasks. May indicate pre-flight issues or expected blockers.' }
else { $lines += 'All clear. Proceed to Tier 1 tasks or release gate.' }

$reportPath = Join-Path $batchDir 'batch-report.md'
($lines -join "`n") | Out-File -FilePath $reportPath -Encoding utf8

# JSON result
$batchResult = @{
    batch_id = $batchId
    timestamp = (Get-Date -Format 'o')
    mode = $manifest.mode
    passed = $passed; blocked = $blocked; failed = $failed; total = $total
    duration = $elapsed
    tasks = @($taskResults)
    report_path = $reportPath
} | ConvertTo-Json -Depth 3
$batchResult | Out-File (Join-Path $batchDir 'batch-result.json') -Encoding utf8

Write-Host "`nBatch Report: $reportPath"
Write-Host "PASS=$passed BLOCKED=$blocked FAILED=$failed"

if ($failed -gt 0) { exit 2 }
if ($blocked -gt 0) { exit 1 }
exit 0
