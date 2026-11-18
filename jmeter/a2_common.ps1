<#
Shared helpers for the A2 speed test. Dot-sourced by a2_calibrate.ps1 and a2_run_load.ps1.

Get-A2Settings turns the calibration time S (seconds) into the brief's run settings:
  arrival interval  = 2 x S seconds                 -> rate = 30 / S per minute
  arrival window    = max(S, 5) minutes
  response timeout  = max(10 x S, 300) seconds      (HTTP sampler)
  drain pause       = timeout + 60 seconds          (end of the Open Model schedule; must outlast the timeout)

JMeter's Open Model Thread Group sends floor(rate x window) arrivals (checked on JMeter 5.6.3:
rate 4.8387/s for 6.2 s gave 29, not 30). The rate is therefore written rounded UP at the
6th decimal, so that S >= 5 gives exactly 30 arrivals instead of 29.
#>

$script:A2Inv = [System.Globalization.CultureInfo]::InvariantCulture

function Format-A2Num([double]$x, [string]$fmt = "0.######") { return $x.ToString($fmt, $script:A2Inv) }

function Get-A2Settings([double]$S) {
    if ($S -le 0) { throw "S must be positive (seconds)." }
    $S = [math]::Round($S, 1)                                   # S is used to 0.1 s everywhere
    $ratePerMin = [math]::Ceiling((30.0 / $S) * 1e6) / 1e6      # rounded up: see header
    $windowSec = [int][math]::Round([math]::Max($S, 5) * 60)
    $timeoutSec = [int][math]::Ceiling([math]::Max(10 * $S, 300))
    $drainSec = $timeoutSec + 60
    $planned = [int][math]::Floor($ratePerMin * $windowSec / 60 + 1e-9)
    [ordered]@{
        s_seconds            = $S
        arrival_interval_s   = [math]::Round(2 * $S, 1)
        rate_per_min         = $ratePerMin
        rate_per_hour        = [math]::Round($ratePerMin * 60, 2)
        arrival_window_s     = $windowSec
        arrival_window_min   = [math]::Round($windowSec / 60, 2)
        response_timeout_s   = $timeoutSec
        drain_pause_s        = $drainSec
        planned_arrivals     = $planned
        schedule             = "rate($(Format-A2Num $ratePerMin)/min) random_arrivals($windowSec sec) rate($(Format-A2Num $ratePerMin)/min) pause($drainSec sec)"
    }
}

function Read-A2Configs([string]$repo) {
    $path = Join-Path $repo "jmeter\a2_configs.json"
    return Get-Content $path -Raw | ConvertFrom-Json
}

function Get-A2Config($configs, [string]$id) {
    $c = $configs.PSObject.Properties[$id]
    if (-not $c -or $id.StartsWith("_")) {
        $ids = ($configs.PSObject.Properties.Name | Where-Object { -not $_.StartsWith("_") }) -join ", "
        throw "Unknown config '$id'. Use one of: $ids"
    }
    return $c.Value
}

# The PowerShell line Li runs on the service host to start the service for a run.
function Get-A2HostCommand($cfg, [string]$runId) {
    if ($cfg.mode -eq "single") {
        $env = "`$env:MODE=`"single`"; `$env:MODEL=`"$($cfg.models[0])`""
    } else {
        $rule = if ($cfg.rule) { $cfg.rule } else { "<rule>" }
        $setting = if ($null -ne $cfg.rule_setting) { $cfg.rule_setting } else { "<setting>" }
        $env = "`$env:MODE=`"cascade`"; `$env:SMALL_MODEL=`"$($cfg.models[0])`"; `$env:LARGE_MODEL=`"$($cfg.models[1])`"; `$env:RULE=`"$rule`"; `$env:RULE_SETTING=`"$setting`""
    }
    return "$env; `$env:RUN_ID=`"$runId`"; docker compose up -d; docker compose restart ollama"
}

# Checks GET /health against the config. Returns a list of problems (empty = OK).
function Test-A2Health($health, $cfg) {
    $problems = @()
    if ($health.mode -ne $cfg.mode) { $problems += "service mode is '$($health.mode)', expected '$($cfg.mode)'" }
    $got = @($health.configured_models) -join ","
    $want = @($cfg.models) -join ","
    if ($got -ne $want) { $problems += "service models are '$got', expected '$want'" }
    if ($cfg.mode -eq "cascade") {
        if ($cfg.rule -and $health.rule -ne $cfg.rule) { $problems += "rule is '$($health.rule)', expected '$($cfg.rule)'" }
        if ($null -ne $cfg.rule_setting -and $health.rule_setting -ne $cfg.rule_setting) { $problems += "rule_setting is '$($health.rule_setting)', expected '$($cfg.rule_setting)'" }
    }
    if ($health.ollama -ne "up") { $problems += "Ollama is not up: $($health.ollama)" }
    return ,$problems
}

function Get-A2StatsTotal($stats) {
    $total = 0
    foreach ($p in $stats.PSObject.Properties) { $total += [int]$p.Value }
    return $total
}

# Reads a workload TSV (row_id<TAB>json body) into objects.
function Read-A2Tsv([string]$path) {
    if (-not (Test-Path $path)) { throw "Missing $path. Put Bryan's workload files in context\a2_workload\ (git-ignored)." }
    $rows = @()
    foreach ($line in [System.IO.File]::ReadAllLines($path, [System.Text.Encoding]::UTF8)) {
        if (-not $line.Trim()) { continue }
        $tab = $line.IndexOf("`t")
        if ($tab -lt 1) { throw "Bad line in ${path}: expected row_id<TAB>json" }
        $rows += [pscustomobject]@{ row_id = [int]$line.Substring(0, $tab); body = $line.Substring($tab + 1) }
    }
    return ,$rows
}

# Checks the workload files against SHA256SUMS.txt when it is present. Returns the hashes.
function Test-A2Workload([string]$dir) {
    $sumsFile = Join-Path $dir "SHA256SUMS.txt"
    $hashes = [ordered]@{}
    if (Test-Path $sumsFile) {
        foreach ($line in Get-Content $sumsFile) {
            if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+)$') {
                $file = Join-Path $dir $Matches[2].Trim()
                if (-not (Test-Path $file)) { continue }
                $actual = (Get-FileHash -Algorithm SHA256 $file).Hash.ToLower()
                if ($actual -ne $Matches[1].ToLower()) { throw "SHA-256 mismatch for $($Matches[2]). The workload files changed: get a fresh package from Bryan." }
                $hashes[$Matches[2].Trim()] = $actual
            }
        }
    }
    return $hashes
}

# One sequential POST /tickets. Returns row, request ID, status and client-side time.
function Send-A2Ticket([string]$baseUrl, $row, [int]$timeoutSec = 900) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $status = $null; $rid = $null; $category = $null; $err = $null
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($row.body)
        $resp = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$baseUrl/tickets" -ContentType "application/json; charset=utf-8" -Body $bytes -TimeoutSec $timeoutSec
        $status = [int]$resp.StatusCode
        $rid = [string]$resp.Headers["X-Request-ID"]
        $category = ($resp.Content | ConvertFrom-Json).category
    } catch {
        $err = $_.Exception.Message
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
    }
    $sw.Stop()
    return [ordered]@{ row_id = $row.row_id; request_id = $rid; status = $status; category = $category; elapsed_ms = $sw.ElapsedMilliseconds; error = $err }
}
