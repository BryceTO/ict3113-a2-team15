<#
Runs ONE A2 speed-test run (open-loop JMeter, POST /tickets only) and keeps its evidence.
Run it on the load-generator machine, never on the service host.

Service host first (prints exactly this if the service does not match):
  <env for the config>; $env:RUN_ID="a2_<config>_speed_r<N>"; docker compose up -d; docker compose restart ollama

Then here:
  powershell -ExecutionPolicy Bypass -File jmeter\a2_run_load.ps1 -TargetHost <ip> -Config gemma3-4b -Run 1
  Add -ShowRunId to print the run ID only, -ShowSettings to print the settings only.

Per run (brief, Step 4 "Each run"):
  1. GET /health matches the config, Ollama was just restarted (no model loaded) and GET /stats is empty
     (fresh RUN_ID database).
  2. Sends the 3 fixed warm-up tickets one at a time; timings are discarded (kept in .meta.json).
  3. Requires every configured model to be loaded (/health all_configured_loaded, i.e. Ollama /api/ps).
     For a cascade whose warm-ups did not escalate, it waits and prints the command that loads the large
     model on the service host with the service's own num_ctx and keep_alive (so it is not reloaded later).
  4. Records the GET /stats total, runs JMeter with the rate/window/timeout/drain derived from S,
     then records GET /stats and /health again.
S comes from results/a2/calibration/a2_calibration.json, so every configuration uses the same settings.

Files written to results/a2/jtl/ (or -OutDir): <RUN_ID>.jtl .properties .meta.json .jmeter.log
#>
param(
    [Parameter(Mandatory = $true)][string]$TargetHost,
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][ValidateRange(1, 99)][int]$Run,
    [string]$CalibrationFile = "",          # default <repo>\results\a2\calibration\a2_calibration.json
    [double]$S = 0,                         # plumbing tests only: override S (seconds); recorded in the meta
    [string]$WorkloadDir = "",              # default <repo>\context\a2_workload
    [int]$Port = 8000,
    [ValidateSet("http", "https")][string]$Scheme = "http",
    [string]$JMeterHome = $env:JMETER_HOME,
    [string]$OutDir = "",                   # default results\a2\jtl; use a scratch folder for plumbing tests
    [double]$ResidencyWaitMin = 10,         # how long to wait for the large model to be loaded
    [string]$Schedule = "",                 # plumbing tests only: replaces the derived schedule
    [switch]$SkipRestartCheck,              # plumbing tests only
    [switch]$ShowRunId,
    [switch]$ShowSettings
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "a2_common.ps1")

$cfg = Get-A2Config (Read-A2Configs $repo) $Config
$runId = "a2_{0}_speed_r{1}" -f $Config, $Run
if ($ShowRunId) { $runId; return }

# --- settings from S -----------------------------------------------------------
$calPath = if ($CalibrationFile) { $CalibrationFile } else { Join-Path $repo "results\a2\calibration\a2_calibration.json" }
if ($S -gt 0) {
    $sSource = "manual -S (plumbing test, not an official run)"
} else {
    if (-not (Test-Path $calPath)) { throw "No calibration file at $calPath. Run scripts\a2_calibrate.ps1 first." }
    $S = (Get-Content $calPath -Raw | ConvertFrom-Json).settings.s_seconds
    # never record a local absolute path (it contains the Windows user name)
    $sSource = if ($calPath.StartsWith($repo + "\")) { $calPath.Substring($repo.Length + 1) } else { Split-Path -Leaf $calPath }
}
$st = Get-A2Settings $S
if ($Schedule) {
    $st.schedule = $Schedule
    $sSource += "; schedule overridden (plumbing test)"
    $st.planned_arrivals = $null
    $st.arrival_window_s = 0
    if ($Schedule -match 'rate\(([\d.]+)/(sec|min)\) random_arrivals\(([\d.]+) sec\)') {
        $perSec = [double]::Parse($Matches[1], $A2Inv) / $(if ($Matches[2] -eq "min") { 60 } else { 1 })
        $st.arrival_window_s = [double]::Parse($Matches[3], $A2Inv)
        $st.planned_arrivals = [int][math]::Floor($perSec * $st.arrival_window_s + 1e-9)
    }
}

$workload = if ($WorkloadDir) { $WorkloadDir } else { Join-Path $repo "context\a2_workload" }
$hashes = Test-A2Workload $workload
$feederPath = Join-Path $workload "measured_feeder.tsv"
$feeder = Read-A2Tsv $feederPath
$warmups = Read-A2Tsv (Join-Path $workload "warmup_requests.tsv")
if ($warmups.Count -ne 3) { throw "Expected 3 warm-up tickets." }
$overlap = @($feeder.row_id | Where-Object { $warmups.row_id -contains $_ })
if ($overlap.Count) { throw "Warm-up rows also appear in the measured feeder: $($overlap -join ', ')" }

if ($ShowSettings) {
    $st | Format-Table -HideTableHeaders | Out-String | Write-Host
    Write-Host "feeder rows: $($feeder.Count)"
    return
}
if (-not $Schedule -and $st.planned_arrivals -gt $feeder.Count) {
    throw "The schedule sends $($st.planned_arrivals) tickets but the feeder has $($feeder.Count) rows (S = $($st.s_seconds) s). Ask the Workload & Requirements Lead to extend the ordered feeder; do not wrap or shorten the window."
}

$outDir = if ($OutDir) { $OutDir } else { Join-Path $repo "results\a2\jtl" }
$jtl = Join-Path $outDir "$runId.jtl"
$propsFile = Join-Path $outDir "$runId.properties"
$metaFile = Join-Path $outDir "$runId.meta.json"
$plan = Join-Path $PSScriptRoot "a2_triage_load.jmx"
$baseUrl = "${Scheme}://${TargetHost}:$Port"
if (-not $JMeterHome) { throw "Set JMETER_HOME or pass -JMeterHome (the folder that contains bin\jmeter.bat)." }
$jmeterBat = Join-Path $JMeterHome "bin\jmeter.bat"
if (-not (Test-Path $jmeterBat)) { throw "jmeter.bat not found at $jmeterBat" }
if (Test-Path $jtl) { throw "$jtl already exists. Evidence is never overwritten: use the next -Run number and note why." }
New-Item -ItemType Directory -Force $outDir | Out-Null

# --- 1. service state ------------------------------------------------------------
$hostCmd = Get-A2HostCommand $cfg $runId
$health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 30
$problems = Test-A2Health $health $cfg
if (@($health.loaded_models).Count -gt 0 -and -not $SkipRestartCheck) {
    $problems += "Ollama already has $(@($health.loaded_models) -join ', ') loaded: it was not restarted for this run"
}
$stats0 = Invoke-RestMethod -Uri "$baseUrl/stats" -TimeoutSec 30
if ((Get-A2StatsTotal $stats0) -gt 0) { $problems += "GET /stats is not empty: the service is not on a fresh RUN_ID ($runId)" }
if ($problems.Count) {
    Write-Host "Service host command for this run:`n  $hostCmd"
    throw ("Service is not ready:`n - " + ($problems -join "`n - "))
}
if ($cfg.mode -eq "cascade" -and ($null -eq $cfg.rule_setting)) {
    Write-Warning "jmeter\a2_configs.json has no frozen rule_setting for $Config. Recording what the service reports: rule=$($health.rule) setting=$($health.rule_setting)"
}

# --- 2. warm-up ------------------------------------------------------------------
$warm = @()
foreach ($r in $warmups) {
    $res = Send-A2Ticket $baseUrl $r
    Write-Host ("warm-up row {0}: {1} ms  status {2}" -f $res.row_id, $res.elapsed_ms, $res.status)
    if ($res.status -ne 200) { throw "Warm-up row $($r.row_id) failed: $($res.error)" }
    $warm += $res
}

# --- 3. every configured model must be resident ----------------------------------
$deadline = (Get-Date).AddMinutes($ResidencyWaitMin)
$told = $false
while ($true) {
    $healthReady = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 30
    if ($healthReady.all_configured_loaded) { break }
    $missing = @($cfg.models | Where-Object { @($healthReady.loaded_models) -notcontains $_ })
    if (-not $told) {
        Write-Host "Not loaded yet: $($missing -join ', '). On the service host run (loads without classifying, same num_ctx/keep_alive as the service):"
        foreach ($m in $missing) {
            Write-Host "  Invoke-RestMethod -Method Post http://127.0.0.1:11434/api/generate -Body '{`"model`":`"$m`",`"keep_alive`":`"30m`",`"options`":{`"num_ctx`":4096}}'"
        }
        Write-Host "  docker compose exec ollama ollama ps      # both models must be listed; save the output"
        Write-Host "Waiting up to $ResidencyWaitMin min..."
        $told = $true
    }
    if ((Get-Date) -gt $deadline) { throw "Configured models are not all loaded ($($missing -join ', ') missing). Do not start the run." }
    Start-Sleep -Seconds 10
}
Write-Host "Resident: $(@($healthReady.loaded_models) -join ', ')"

# --- 4. stats before, JMeter, stats after ----------------------------------------
$statsBefore = Invoke-RestMethod -Uri "$baseUrl/stats" -TimeoutSec 30
$fwd = { param($p) $p.Replace("\", "/") }   # Java .properties treats \ as an escape
# JMeter resolves a relative CSV path against the plan's folder (jmeter\). Inside the repo, write it
# relative so the committed .properties holds no local path (it would contain the Windows user name).
$feederProp = if ((Resolve-Path $feederPath).Path.StartsWith($repo + "\")) {
    "../" + (Resolve-Path $feederPath).Path.Substring($repo.Length + 1)
} else { $feederPath }
@"
protocol=$Scheme
host=$TargetHost
port=$Port
connect_timeout_ms=10000
response_timeout_ms=$($st.response_timeout_s * 1000)
feeder=$(& $fwd $feederProp)
schedule=$($st.schedule)
seed=$Run
sample_variables=row_id,request_id
jmeter.save.saveservice.output_format=csv
jmeter.save.saveservice.print_field_names=true
jmeter.save.saveservice.timestamp_format=ms
"@ | Set-Content -Path $propsFile -Encoding ascii

$meta = [ordered]@{
    run_id               = $runId
    config               = $Config
    run                  = $Run
    mode                 = $cfg.mode
    models               = $cfg.models
    target               = $baseUrl
    jmeter_version       = (Split-Path -Leaf $JMeterHome)   # folder name only, e.g. apache-jmeter-5.6.3 (no local path)
    s_source             = $sSource
    settings             = $st
    seed                 = $Run
    feeder_rows          = $feeder.Count
    feeder_rows_used     = @($feeder | Select-Object -First $st.planned_arrivals | ForEach-Object { $_.row_id })
    workload_sha256      = $hashes
    restart_check        = -not $SkipRestartCheck
    health_before_warmup = $health
    warmup               = $warm
    health_before_run    = $healthReady
    stats_before         = $statsBefore
    stats_before_total   = Get-A2StatsTotal $statsBefore
    jmeter_started_ms    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
}
$meta | ConvertTo-Json -Depth 6 | Set-Content -Path $metaFile -Encoding utf8

Write-Host "RUN_ID    $runId"
Write-Host "Schedule  $($st.schedule)   (planned $($st.planned_arrivals) arrivals, seed $Run)"
Write-Host "Expected end in about $([math]::Ceiling(($st.arrival_window_s + $st.drain_pause_s) / 60)) min. Do not use either machine until JMeter finishes."
& $jmeterBat -n -t $plan -q $propsFile -l $jtl -j (Join-Path $outDir "$runId.jmeter.log")
$jmeterExit = $LASTEXITCODE
$meta["jmeter_finished_ms"] = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$meta["jmeter_exit_code"] = $jmeterExit
# the schedule starts when the test starts, a few seconds after the JVM launch above: take that time from JMeter's log
$startLine = Select-String -Path (Join-Path $outDir "$runId.jmeter.log") -Pattern "Starting OpenModelThreadGroup" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($startLine) {
    $meta["jmeter_log_schedule_line"] = $startLine.Line
    if ($startLine.Line -match '^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3})') {
        $local = [datetime]::ParseExact($Matches[1], "yyyy-MM-dd HH:mm:ss,fff", $A2Inv, [System.Globalization.DateTimeStyles]::AssumeLocal)
        $meta["schedule_started_ms"] = ([DateTimeOffset]$local).ToUnixTimeMilliseconds()
    }
}

$statsAfter = Invoke-RestMethod -Uri "$baseUrl/stats" -TimeoutSec 30
$meta["stats_after"] = $statsAfter
$meta["stats_after_total"] = Get-A2StatsTotal $statsAfter
$meta["stored_during_run"] = $meta["stats_after_total"] - $meta["stats_before_total"]
$meta["health_after_run"] = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 30
$meta | ConvertTo-Json -Depth 6 | Set-Content -Path $metaFile -Encoding utf8
if ($jmeterExit -ne 0) { throw "JMeter exited with code $jmeterExit (meta saved)." }

$samples = if (Test-Path $jtl) { (Get-Content $jtl | Measure-Object -Line).Lines - 1 } else { 0 }
Write-Host "Finished: planned $($st.planned_arrivals), JMeter recorded $samples, service stored $($meta['stored_during_run']) during the run."
if (-not $meta["health_after_run"].all_configured_loaded) { Write-Warning "A configured model was no longer loaded after the run: check the log for reloads." }
Write-Host "Next: commit results/logs/$runId.log from the service host, pull, then: py scripts\summarize_a2_load.py"
