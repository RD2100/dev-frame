<#
.SYNOPSIS
Queue Group Runner with optional parallel execution.
Default: serial. -Parallel enables concurrent execution with MaxParallel limit.
Exit: 0=PASS, 1=BLOCKED/ESCALATED, 2=FAILED
#>
param(
    [Parameter(Mandatory)][string[]]$QueueFiles,
    [switch]$Parallel,
    [int]$MaxParallel = 2,
    [string]$OutputRoot = 'runs/powershell-acceptance/workqueue-groups'
)

$ErrorActionPreference = 'Continue'
$script:groupStart = Get-Date
$groupDir = Join-Path $OutputRoot ('group-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path $groupDir | Out-Null

# ---- Conflict guard ----
$outputDirs = @{}
$conflicts = [System.Collections.ArrayList]::new()
foreach ($qf in $QueueFiles) {
    if (-not (Test-Path $qf)) {
        Write-Host "BLOCKED: queue file not found: $qf"
        [void]$conflicts.Add("missing: $qf")
        continue
    }
    $q = Get-Content $qf -Raw | ConvertFrom-Json
    $qid = $q.queue_id
    if ($outputDirs.ContainsKey($qid)) {
        [void]$conflicts.Add("duplicate queue_id: $qid")
    }
    $outputDirs[$qid] = $true
}
if ($conflicts.Count -gt 0) {
    Write-Host "BLOCKED: queue conflicts detected"
    foreach ($c in $conflicts) { Write-Host "  $c" }
    exit 1
}

$runner = Join-Path $PSScriptRoot 'Run-WorkQueue.ps1'
$queueResults = [System.Collections.ArrayList]::new()

# ---- Serial mode (default) ----
if (-not $Parallel) {
    Write-Host "=== QueueGroup: Serial Mode ==="
    foreach ($qf in $QueueFiles) {
        if (-not (Test-Path $qf)) { continue }
        $q = Get-Content $qf -Raw | ConvertFrom-Json
        Write-Host "`n--- Queue: $($q.queue_id) ---"
        $t0 = Get-Date
        powershell -ExecutionPolicy Bypass -File $runner -QueueFile $qf 2>&1 | Out-Null
        $ec = $LASTEXITCODE
        $ts = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
        $verdict = if ($ec -eq 0) { 'PASS' } elseif ($ec -eq 1) { 'BLOCKED' } else { 'FAILED' }
        [void]$queueResults.Add(@{ queue = $q.queue_id; exit_code = $ec; verdict = $verdict; duration = $ts })
        Write-Host "  Exit: $ec ($verdict) ${ts}s"
    }
}
else {
    # ---- Parallel mode ----
    Write-Host "=== QueueGroup: Parallel Mode (max=$MaxParallel) ==="
    $validQueues = $QueueFiles | Where-Object { Test-Path $_ }
    $queueCount = $validQueues.Count
    $running = @{}
    $completed = @{}

    while ($completed.Count -lt $queueCount) {
        # Start new jobs up to MaxParallel
        for ($i = 0; $i -lt $queueCount; $i++) {
            $qf = $validQueues[$i]
            if ($completed.ContainsKey($i)) { continue }
            if ($running.Count -ge $MaxParallel) { break }
            if ($running.ContainsKey($i)) { continue }

            $q = Get-Content $qf -Raw | ConvertFrom-Json
            $jid = "job-$i"
            Write-Host "[$jid] Starting: $($q.queue_id)"
            $job = Start-Job -Name $jid -ScriptBlock {
                param($r, $q, $d)
                Set-Location $d
                powershell -ExecutionPolicy Bypass -File $r -QueueFile $q
                $LASTEXITCODE
            } -ArgumentList $runner, $qf, (Get-Location).Path
            $running[$i] = @{ job = $job; queue = $qf; qid = $q.queue_id; t0 = Get-Date }
        }

        # Check for completed jobs
        $toRemove = @()
        foreach ($kv in $running.GetEnumerator()) {
            $idx = $kv.Key
            $j = $kv.Value.job
            if ($j.State -eq 'Completed' -or $j.State -eq 'Failed') {
                $ec = Receive-Job $j -ErrorAction SilentlyContinue
                Remove-Job $j -Force
                $ts = [math]::Round(((Get-Date) - $kv.Value.t0).TotalSeconds, 1)
                $verdict = if ($ec -eq 0) { 'PASS' } elseif ($ec -eq 1) { 'BLOCKED' } else { 'FAILED' }
                [void]$queueResults.Add(@{ queue = $kv.Value.qid; exit_code = $ec; verdict = $verdict; duration = $ts })
                Write-Host "[job-$idx] Done: $($verdict) ${ts}s"
                $completed[$idx] = $true
                $toRemove += $idx
            }
        }
        foreach ($r in $toRemove) { $running.Remove($r) }

        if ($running.Count -ge $MaxParallel -and $completed.Count -lt $queueCount) {
            Start-Sleep -Seconds 2
        }
    }
}

# ---- Group report ----
$elapsed = [math]::Round(((Get-Date) - $script:groupStart).TotalSeconds, 1)
$passed = ($queueResults | Where-Object { $_.verdict -eq 'PASS' }).Count
$blocked = ($queueResults | Where-Object { $_.verdict -eq 'BLOCKED' }).Count
$failed = ($queueResults | Where-Object { $_.verdict -eq 'FAILED' }).Count
$total = $queueResults.Count

$lines = @()
$lines += "# QueueGroup Report"; $lines += ""
$lines += "**Time**: $(Get-Date -Format 'o')"
$lines += "**Duration**: ${elapsed}s"
$lines += "**Mode**: $(if ($Parallel) { 'parallel' } else { 'serial' })"
$lines += "**MaxParallel**: $(if ($Parallel) { $MaxParallel } else { 'N/A' })"; $lines += ""
$lines += "## Executive Decision"; $lines += ""
if ($failed -gt 0) { $lines += 'FAILED. Escalate to reviewer.' }
elseif ($blocked -gt 0) { $lines += 'BLOCKED. Reviewer should check blocked queues.' }
else { $lines += 'PASS. All queues passed.' }
$lines += ""
$lines += "## Summary"; $lines += "PASS=$passed BLOCKED=$blocked FAILED=$failed TOTAL=$total"
$lines += ""
$lines += "## Queue Results"; $lines += ""
$lines += "| # | Queue | Exit | Verdict | Duration |"
$lines += "|---|-------|------|---------|----------|"
for ($i = 0; $i -lt $total; $i++) {
    $r = $queueResults[$i]
    $lines += "| $($i+1) | $($r.queue) | $($r.exit_code) | $($r.verdict) | $($r.duration)s |"
}
$lines += ""

$rptPath = Join-Path $groupDir 'group-report.md'
($lines -join "`n") | Out-File -FilePath $rptPath -Encoding utf8

Write-Host "`nGroup Report: $rptPath"
Write-Host "PASS=$passed BLOCKED=$blocked FAILED=$failed"

if ($failed -gt 0) { exit 2 }
if ($blocked -gt 0) { exit 1 }
exit 0
