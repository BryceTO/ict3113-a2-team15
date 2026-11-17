<#
.SYNOPSIS
  A2 memory/residency check: can the cascade's small and large model stay loaded in Ollama together
  on THIS machine, with the A1 CPU/RAM allocation and Ollama settings?

.DESCRIPTION
  Run on the service host (the A1 test machine), from the repo root, with `docker compose up -d` running.
  1. Records environment: Docker CPUs/RAM, Ollama container limits and OLLAMA_* settings, Ollama version,
     model digests.
  2. Unloads all models, then loads SMALL, then LARGE (one ticket each) and captures `ollama ps`.
  3. Alternates SMALL/LARGE for -Rounds rounds with different tickets, capturing `ollama ps` and each call's
     load_duration. A load_duration above 1 s after a model's first call means it was evicted and reloaded.
  4. Writes a verdict: RESIDENT (both listed at the end and no reloads) or NOT RESIDENT.
  Calls use the same options as the service (temperature 0, num_predict 16, num_ctx, keep_alive).

.EXAMPLE
  .\scripts\check_residency.ps1 -Small llama3.2:1b -Large gemma3:4b
  .\scripts\check_residency.ps1 -Small gemma3:4b -Large mistral:7b-instruct
#>
param(
    [Parameter(Mandatory = $true)][string]$Small,
    [Parameter(Mandatory = $true)][string]$Large,
    [int]$Rounds = 3,
    [int]$NumCtx = 4096,
    [string]$KeepAlive = "30m",
    [string]$OllamaUrl = "http://localhost:11434"
)
$ErrorActionPreference = "Stop"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$pair = ("{0}__{1}" -f $Small, $Large) -replace '[:/\\]', '-'
$out = Join-Path "results/a2/residency" "${stamp}_${pair}"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Write-Host "Saving evidence to $out"

function Save-Json($obj, $name) { $obj | ConvertTo-Json -Depth 10 | Out-File -Encoding utf8 (Join-Path $out $name) }

function Save-OllamaPs($label) {
    $api = Invoke-RestMethod "$OllamaUrl/api/ps" -TimeoutSec 30
    Save-Json $api "ps_${label}.json"
    $text = (docker compose exec -T ollama ollama ps) -join "`n"
    $text | Out-File -Encoding utf8 (Join-Path $out "ps_${label}.txt")
    Write-Host "--- ollama ps ($label) ---`n$text"
    return @($api.models | ForEach-Object { $_.name })
}

# Prompt text mirrors the service's classification prompt (service/main.py PROMPT).
$cats = "Credit reporting", "Debt collection", "Mortgage", "Credit card", "Bank account or service", "Consumer loan", "Money transfer or service"
function Build-Prompt($narrative) {
    "You are a complaint ticket classifier for a financial services company.`n" +
    "Classify the customer complaint into exactly ONE of these categories:`n" +
    (($cats | ForEach-Object { "- $_" }) -join "`n") +
    "`n`nReply with only the category name, exactly as written above, and nothing else.`n`n" +
    "Complaint:`n$narrative`n`nCategory:"
}
# Different tickets each call, so Ollama's prompt cache cannot hide a reload.
$tickets = @(
    "A debt collector keeps calling me about a loan I already paid off two years ago.",
    "My credit report shows a late payment on an account that I never opened.",
    "The bank closed my checking account without notice and kept my last deposit.",
    "I was charged twice on my credit card for one purchase and the dispute was denied.",
    "My mortgage servicer misapplied my escrow payment and now says I am behind.",
    "A wire transfer I sent to my family never arrived and the company will not refund the fee.",
    "My car loan lender added fees that were not in my contract.",
    "The collection agency reported a medical debt that my insurance already covered."
)
$ticketIdx = 0

function Invoke-Model($model, $label) {
    $script:ticketIdx++
    $t = $tickets[($script:ticketIdx - 1) % $tickets.Count]
    $body = @{ model = $model; prompt = (Build-Prompt $t); stream = $false; keep_alive = $KeepAlive
               options = @{ temperature = 0; num_predict = 16; num_ctx = $NumCtx } } | ConvertTo-Json -Depth 5
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-RestMethod -Method Post "$OllamaUrl/api/generate" -ContentType "application/json" -Body $body -TimeoutSec 900
    $sw.Stop()
    $row = [pscustomobject]@{
        step = $label; model = $model; ticket = $script:ticketIdx
        wall_ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 1)
        load_ms = [math]::Round($r.load_duration / 1e6, 1)
        total_ms = [math]::Round($r.total_duration / 1e6, 1)
        answer = ($r.response -replace '\s+', ' ').Trim()
    }
    Write-Host ("{0,-12} {1,-22} wall {2,8} ms  load {3,8} ms  -> {4}" -f $label, $model, $row.wall_ms, $row.load_ms, $row.answer)
    return $row
}

# ---- 1. environment
Write-Host "Recording environment..."
$info = docker info --format "{{json .}}" | ConvertFrom-Json
$cid = (docker compose ps -q ollama).Trim()
$inspect = docker inspect $cid | ConvertFrom-Json
$ollamaEnv = @(docker compose exec -T ollama env | Where-Object { $_ -like "OLLAMA_*" })
$tags = (Invoke-RestMethod "$OllamaUrl/api/tags").models | Where-Object { $_.name -in @($Small, $Large) } |
    Select-Object name, digest, size
$envInfo = [ordered]@{
    timestamp = (Get-Date).ToString("o"); host = $env:COMPUTERNAME
    host_cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
    host_ram_gb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)
    docker_server_version = $info.ServerVersion; docker_ncpu = $info.NCPU
    docker_mem_gib = [math]::Round($info.MemTotal / 1GB, 3)
    ollama_container_memory_limit = $inspect[0].HostConfig.Memory
    ollama_container_nano_cpus = $inspect[0].HostConfig.NanoCpus
    ollama_image = $inspect[0].Config.Image
    ollama_version = (Invoke-RestMethod "$OllamaUrl/api/version").version
    ollama_env = $ollamaEnv
    num_ctx = $NumCtx; keep_alive = $KeepAlive
    small = $Small; large = $Large; models = $tags
}
Save-Json $envInfo "environment.json"
if (@($tags).Count -lt 2) { throw "Both models must be pulled first (found: $(@($tags).name -join ', '))" }

# ---- 2. clean start: unload everything
foreach ($m in (Invoke-RestMethod "$OllamaUrl/api/ps").models) {
    $b = @{ model = $m.name; keep_alive = 0 } | ConvertTo-Json
    Invoke-RestMethod -Method Post "$OllamaUrl/api/generate" -ContentType "application/json" -Body $b | Out-Null
}
Start-Sleep -Seconds 3
Save-OllamaPs "0_start" | Out-Null

$calls = @()
$calls += Invoke-Model $Small "load_small"
Save-OllamaPs "1_after_small" | Out-Null
$calls += Invoke-Model $Large "load_large"
$afterBoth = Save-OllamaPs "2_after_both"

# ---- 3. alternate
for ($i = 1; $i -le $Rounds; $i++) {
    $calls += Invoke-Model $Small "alt${i}_small"
    $calls += Invoke-Model $Large "alt${i}_large"
}
$final = Save-OllamaPs "3_after_alternating"
docker stats --no-stream --format "{{.Name}}`t{{.MemUsage}}`t{{.MemPerc}}`t{{.CPUPerc}}" |
    Out-File -Encoding utf8 (Join-Path $out "docker_stats_end.txt")
$calls | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out "calls.csv")

# ---- 4. verdict
$reloads = @($calls | Where-Object { $_.step -like "alt*" -and $_.load_ms -gt 1000 })
$bothAtEnd = ($final -contains $Small) -and ($final -contains $Large)
$resident = $bothAtEnd -and ($reloads.Count -eq 0)
$verdict = if ($resident) { "RESIDENT" } else { "NOT RESIDENT" }
$summary = @"
# Residency check: $Small + $Large

- Verdict: **$verdict**
- Both listed by ``ollama ps`` after loading both: $(($afterBoth -contains $Small) -and ($afterBoth -contains $Large))
- Both listed after $Rounds alternating rounds: $bothAtEnd
- Reloads during alternation (load_duration > 1 s): $($reloads.Count)
- Host: $($envInfo.host_cpu), $($envInfo.host_ram_gb) GB RAM; Docker: $($envInfo.docker_ncpu) CPUs, $($envInfo.docker_mem_gib) GiB
- Ollama $($envInfo.ollama_version); settings: $($ollamaEnv -join ', '); num_ctx $NumCtx; keep_alive $KeepAlive

| Step | Model | Wall ms | Load ms | Answer |
|---|---|---:|---:|---|
$(($calls | ForEach-Object { "| $($_.step) | $($_.model) | $($_.wall_ms) | $($_.load_ms) | $($_.answer) |" }) -join "`n")

Files: environment.json (versions, digests, limits), ps_*.json/txt (``ollama ps`` snapshots), calls.csv, docker_stats_end.txt.
"@
$summary | Out-File -Encoding utf8 (Join-Path $out "summary.md")
Write-Host "`n==> $verdict  ($Small + $Large). Evidence: $out"
