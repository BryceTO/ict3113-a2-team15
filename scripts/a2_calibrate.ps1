<#
A2 calibration: measures S on the top model and derives the speed-test settings for EVERY configuration.
Run it on the load-generator machine, after the accuracy tests, once.

Service host first (fresh run ID and a freshly restarted Ollama, so no model is loaded):
  $env:MODE="single"; $env:MODEL="gemma3:4b"; $env:RUN_ID="a2_gemma3-4b_calibration"; docker compose up -d; docker compose restart ollama

Then here:
  powershell -ExecutionPolicy Bypass -File scripts\a2_calibrate.ps1 -TargetHost <service-host-ip>

What it does (brief, Step 4 Set-up):
  1. Checks GET /health: single mode on the top model, Ollama up, no model loaded yet.
  2. Sends the 3 fixed warm-up tickets one at a time (timings kept but not used).
  3. Sends the 3 calibration tickets (different rows, typical length) one at a time to the top model.
  4. S = the middle of the 3 calibration times, in seconds (client-side, the same clock as JMeter's elapsed).
  5. Writes results/a2/calibration/a2_calibration.json with the timings, row IDs, request IDs and the
     derived rate, window, timeout and drain. a2_run_load.ps1 reads S from this file.
#>
param(
    [Parameter(Mandatory = $true)][string]$TargetHost,
    [string]$Config = "gemma3-4b",          # the confirmed A1 top model
    [int]$Port = 8000,
    [ValidateSet("http", "https")][string]$Scheme = "http",
    [string]$WorkloadDir = "",              # default <repo>\context\a2_workload
    [string]$OutFile = "",                  # default <repo>\results\a2\calibration\a2_calibration.json
    [switch]$SkipRestartCheck               # plumbing tests only: allow models already loaded
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $repo "jmeter\a2_common.ps1")

$workload = if ($WorkloadDir) { $WorkloadDir } else { Join-Path $repo "context\a2_workload" }
$out = if ($OutFile) { $OutFile } else { Join-Path $repo "results\a2\calibration\a2_calibration.json" }
if (Test-Path $out) { throw "$out already exists. Calibration is done once; evidence is never overwritten (pass -OutFile for a new attempt and explain why)." }
$baseUrl = "${Scheme}://${TargetHost}:$Port"

$cfg = Get-A2Config (Read-A2Configs $repo) $Config
if ($cfg.mode -ne "single") { throw "Calibrate on the top model alone (a single-mode config)." }
$hashes = Test-A2Workload $workload
$warmups = Read-A2Tsv (Join-Path $workload "warmup_requests.tsv")
$calib = Read-A2Tsv (Join-Path $workload "calibration_requests.tsv")
if ($warmups.Count -ne 3 -or $calib.Count -ne 3) { throw "Expected 3 warm-up and 3 calibration tickets." }
if (@($calib.row_id | Sort-Object -Unique).Count -ne 3) { throw "The 3 calibration tickets must be different rows (Ollama caches repeated prompts)." }

# --- 1. service state --------------------------------------------------------
$health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 30
$problems = Test-A2Health $health $cfg
if (@($health.loaded_models).Count -gt 0 -and -not $SkipRestartCheck) {
    $problems += "Ollama already has $(@($health.loaded_models) -join ', ') loaded: restart it first (docker compose restart ollama)"
}
if ($problems.Count) {
    Write-Host "Service host command:`n  $(Get-A2HostCommand $cfg 'a2_gemma3-4b_calibration')"
    throw ("Service is not ready for calibration:`n - " + ($problems -join "`n - "))
}
$statsBefore = Invoke-RestMethod -Uri "$baseUrl/stats" -TimeoutSec 30

# --- 2. warm-up, 3. calibration ----------------------------------------------
$warm = @()
foreach ($r in $warmups) {
    $res = Send-A2Ticket $baseUrl $r
    Write-Host ("warm-up     row {0}: {1} ms  status {2}" -f $res.row_id, $res.elapsed_ms, $res.status)
    if ($res.status -ne 200) { throw "Warm-up row $($r.row_id) failed: $($res.error)" }
    $warm += $res
}
$cal = @()
foreach ($r in $calib) {
    $res = Send-A2Ticket $baseUrl $r
    Write-Host ("calibration row {0}: {1} ms  status {2}" -f $res.row_id, $res.elapsed_ms, $res.status)
    if ($res.status -ne 200) { throw "Calibration row $($r.row_id) failed: $($res.error). Fix the cause and calibrate again from a restart." }
    $cal += $res
}
$healthAfter = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 30

# --- 4. S and the derived settings -------------------------------------------
$middleMs = (@($cal.elapsed_ms) | Sort-Object)[1]
$settings = Get-A2Settings ($middleMs / 1000.0)
$feederRows = (Read-A2Tsv (Join-Path $workload "measured_feeder.tsv")).Count

$record = [ordered]@{
    purpose            = "A2 speed-test calibration (brief Step 4, Set-up)"
    config             = $Config
    model              = $cfg.models[0]
    target             = $baseUrl
    measured_at_utc    = [DateTime]::UtcNow.ToString("o")
    load_generator     = $env:COMPUTERNAME
    timing_method      = "client-side wall time of each sequential POST /tickets (System.Diagnostics.Stopwatch), the same clock JMeter's elapsed uses"
    health_before      = $health
    health_after       = $healthAfter
    stats_before       = $statsBefore
    warmups            = $warm
    calibration        = $cal
    calibration_ms     = @($cal.elapsed_ms)
    middle_ms          = $middleMs
    settings           = $settings
    feeder_rows        = $feederRows
    workload_sha256    = $hashes
    restart_check      = -not $SkipRestartCheck
}
New-Item -ItemType Directory -Force (Split-Path -Parent $out) | Out-Null
$record | ConvertTo-Json -Depth 6 | Set-Content -Path $out -Encoding utf8

# --- report ------------------------------------------------------------------
$s = $settings
Write-Host ""
Write-Host "Calibration rows      $(@($cal.row_id) -join ', ')"
Write-Host "Calibration times     $(@($cal.elapsed_ms) -join ' ms, ') ms"
Write-Host "S (middle)            $($s.s_seconds) s"
Write-Host "Arrival interval      $($s.arrival_interval_s) s  (one ticket every 2 x S)"
Write-Host "Rate                  $($s.rate_per_min) /min  ($($s.rate_per_hour) /h)"
Write-Host "Arrival window        $($s.arrival_window_min) min ($($s.arrival_window_s) s)"
Write-Host "Response timeout      $($s.response_timeout_s) s"
Write-Host "Drain pause           $($s.drain_pause_s) s"
Write-Host "Planned arrivals/run  $($s.planned_arrivals)   (feeder has $feederRows rows)"
Write-Host "Schedule              $($s.schedule)"
if ($s.s_seconds -lt 5) { Write-Warning "S < 5 s: the 5-minute minimum gives $($s.planned_arrivals) arrivals per run. Tell Bryan now." }
if ($s.planned_arrivals -gt $feederRows) { Write-Warning "The feeder is too short ($feederRows rows). Official runs are blocked until Bryan extends it." }
Write-Host "`nSaved $out. Commit it with results/logs/a2_gemma3-4b_calibration.log from the service host."
