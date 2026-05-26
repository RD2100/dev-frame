<#
.SYNOPSIS
PowerShell Acceptance Smoke Test
Exit: 0=PASS, 1=BLOCKED, 2=FAILED
#>
param(
    [string]$ProjectPath = (Resolve-Path "$PSScriptRoot\..\..").Path,
    [string]$ReportDir = $env:TEMP + '\acceptance-smoke-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
)

$ErrorActionPreference = 'Continue'
$results = [System.Collections.ArrayList]::new()
$startTime = Get-Date

function Record($flow, $status, $detail) {
    $r = @{ flow = $flow; status = $status; detail = $detail; timestamp = (Get-Date -Format 'o') }
    [void]$results.Add($r)
    $icon = @{ PASS = 'PASS'; BLOCKED = 'BLOCK'; FAILED = 'FAIL' }[$status]
    Write-Host "  [$icon] $flow $detail"
}

# 1. Path check
if (-not (Test-Path $ProjectPath)) {
    Record 'project-exists' 'BLOCKED' "not found: $ProjectPath"
    Write-Host "FATAL: project path missing"
    exit 1
}
Record 'project-exists' 'PASS' $ProjectPath

# 2. Python
try {
    $py = python --version 2>&1
    Record 'python' 'PASS' $py.Trim()
} catch {
    Record 'python' 'BLOCKED' 'not on PATH'
}

# 3. Git
try {
    $gv = git --version 2>&1
    Record 'git' 'PASS' $gv.Trim()
} catch {
    Record 'git' 'BLOCKED' 'not on PATH'
}

# 4. Source dir
$src = Join-Path $ProjectPath 'src'
if (Test-Path $src) {
    Record 'src-exists' 'PASS' 'found'
    $pySrc = $src -replace '\\', '/'
    $env:PYTHONPATH = $pySrc
    try {
        python -m compileall -q $pySrc 2>&1
        if ($LASTEXITCODE -eq 0) {
            Record 'compileall' 'PASS' 'OK'
        } else {
            Record 'compileall' 'FAILED' "exit=$LASTEXITCODE"
        }
    } catch {
        Record 'compileall' 'BLOCKED' $_.Exception.Message
    }
} else {
    Record 'src-exists' 'BLOCKED' 'not found'
}

# 5. Config files
'package.json', '.gitignore' | ForEach-Object {
    $p = Join-Path $ProjectPath $_
    if (Test-Path $p) { Record "config-$_" 'PASS' 'found' }
    else { Record "config-$_" 'BLOCKED' 'not found' }
}

# 6. tasks.yaml
$ty = Join-Path $ProjectPath 'tasks.yaml'
if (Test-Path $ty) {
    try {
        $tySafe = $ty -replace '\\', '/'
        python -c "import yaml; yaml.safe_load(open('$tySafe',encoding='utf-8')); print('OK')" 2>&1
        if ($LASTEXITCODE -eq 0) { Record 'tasks-yaml' 'PASS' 'parse OK' }
        else { Record 'tasks-yaml' 'FAILED' 'parse error' }
    } catch {
        Record 'tasks-yaml' 'BLOCKED' $_.Exception.Message
    }
} else {
    Record 'tasks-yaml' 'BLOCKED' 'not found'
}

# Summary
$elapsed = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
$passed = ($results | Where-Object { $_.status -eq 'PASS' }).Count
$blocked = ($results | Where-Object { $_.status -eq 'BLOCKED' }).Count
$failed = ($results | Where-Object { $_.status -eq 'FAILED' }).Count
$total = $results.Count

New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$lines = @()
$lines += "# PowerShell Acceptance Smoke Report"; $lines += ""
$lines += "**Time**: $(Get-Date -Format 'o')"
$lines += "**Duration**: ${elapsed}s"; $lines += ""
$lines += "## Summary"; $lines += "PASS=$passed BLOCKED=$blocked FAILED=$failed TOTAL=$total"; $lines += ""
$lines += "## Results"; $lines += ""
$lines += "| # | Flow | Status | Detail |"
$lines += "|---|------|--------|--------|"
for ($i = 0; $i -lt $total; $i++) {
    $r = $results[$i]
    $lines += "| $($i+1) | $($r.flow) | $($r.status) | $($r.detail) |"
}
$lines += ""
$lines += "## Verdict"
if ($failed -gt 0) { $lines += 'FAILED' }
elseif ($blocked -gt 0) { $lines += 'BLOCKED' }
else { $lines += 'PASS' }
$lines += ""; $lines += "## Explorer"; $lines += "Explorer: not run, browser automation deferred"

$reportPath = Join-Path $ReportDir 'acceptance-report.md'
($lines -join "`n") | Out-File -FilePath $reportPath -Encoding utf8
Write-Host "`nReport: $reportPath"

if ($failed -gt 0) { exit 2 }
if ($blocked -gt 0) { exit 1 }
exit 0
