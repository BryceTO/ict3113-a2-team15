# A2 accuracy workflow and regression-test contract

Status: implementation for review; no official accuracy requests or performance benchmarks have been executed by this workflow review. Nothing here changes the rule or prediction freeze at `fafe5bfbf5b389e8e8f07cbda18a4a34cb6fe2f4`.

## Scope and preconditions

The new scripts use Python 3.10+ and only the standard library. Run them from the repository root. A1 scripts and evidence are unchanged. Official inputs are the frozen 88 even-row tickets in `golden_set/a2/test (even).csv`; the scripts do not tune thresholds or inspect odd-row outcomes. `load_test()` validates count, positive even IDs, uniqueness, nonblank narratives, seven-category labels and a pinned SHA-256 of canonical row/narrative/label records. CSV newline differences do not change that fingerprint. Changing a ticket or label does. The sorted row order is the submission order.

The canonical configuration IDs are `llama3.2-1b`, `gemma3-4b`, `mistral-7b-instruct`, `cascade_s1`, and `cascade_s2`. The runner cross-checks `jmeter/a2_configs.json`. Its currently null cascade rule/settings are resolved in memory to the frozen `length` rule and 241/289 thresholds. A conflicting non-null value is an error. This does not edit the benchmark configuration; its owner must still fill those fields before speed testing.

Before official collection:

1. Review this implementation with Yuhao, then commit the reviewed workflow. Keep the existing rule and predictions unchanged.
2. Verify the service host, full model digests, Ollama version, fixed inference settings and resource allocation using `docs/a2_test_environment.md`. `/health` cannot prove these facts.
3. Configure the service for the selected configuration and set its `RUN_ID` to the exact CLI run ID. `/health` does not expose `RUN_ID`; the scorer verifies it against service logs for all five configurations. Use a new suffix for every attempt and archive abandoned runs. Never resume an interrupted official run or silently combine attempts.
4. Warm the configured models with synthetic non-test tickets, explicitly using reserved `row_id` values `-1`, `-2`, and `-3` (one per warm-up). Never use golden test row IDs for warm-ups. For cascades, confirm both are resident. The runner checks both names in `/health.loaded_models` and `all_configured_loaded` before sending any test ticket; it does not warm models itself.
5. Keep the configuration fixed for the whole run, retain `results/logs/<RUN_ID>.log`, and avoid simultaneous clients. The runner does not start/reconfigure Docker or select models.

## A1 reuse audit

| A1 model | Record integrity (full historical set, not A2 accuracy) | Reuse verdict now |
|---|---|---|
| Llama 3.2 1B | 175 unique rows, all golden IDs/labels and model tags match; 0 failed records; 175 request IDs reconcile to their service-log row IDs | Blocked pending historical execution provenance |
| Gemma 3 4B | 175 unique matching rows; 1 failed record (HTTP 502) without a request ID; the other 174 request IDs reconcile | Blocked pending historical execution provenance |
| Mistral 7B Instruct | 175 unique matching rows; 24 failed records (HTTP 502) without request IDs; the other 151 request IDs reconcile | Blocked pending historical execution provenance |

The failed A1 records are not grounds to drop tickets or automatically reject an otherwise verified run. They remain incorrect, including those without request IDs. The old runner loses the request ID when `raise_for_status()` fails; the new runner preserves the response header even on HTTP errors. No official even-row accuracy scores were calculated for this audit, and no outcomes were used to select new settings.

All historical correctness flags agree with the recorded labels/status/errors, and all recorded latencies are finite and nonnegative. Successful predictions match their logged categories and statuses. Each failed record without an ID has one matching historical log row with the same status; this audit does not invent missing request IDs in the source CSV.

Evidence checked:

- `docs/candidate_models.md` records the full digests below and candidate verification with Ollama 0.40.0.
- The A2 residency `environment.json` files record the same full digests, but their November checks do not establish the runtime used by the historical October accuracy requests.
- AST comparison of `CATEGORIES`, `PROMPT` and `match_category` in `service/main.py` against `a1-baseline:service/main.py` found them unchanged. This establishes source compatibility, not which source was deployed during an old run.
- `docs/test_environment.md`, `docs/a2_test_environment.md` and Docker configuration describe Ollama 0.35.0, the same Intel Core Ultra 7 155H host, 22 Docker logical CPUs and 9.713 GiB available memory. The documents support compatibility but do not conclusively bind the historical accuracy runs to those conditions.
- `results/logs/llama3.2-1b_accuracy.log`, `gemma3-4b_accuracy.log` and `mistral-7b_accuracy.log` contain request-level model tags and timings, but no full digest, Ollama version, source revision or machine/resource snapshot. They cannot resolve the 0.40.0 versus 0.35.0 discrepancy by themselves.

| Model | Required full digest |
|---|---|
| Llama | `baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878` |
| Gemma | `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a` |
| Mistral | `6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf` |

To unblock reuse, the responsible reviewer must supply evidence linking the historical accuracy runs and the intended A2 environment to the same digest, prompt, category matching, Ollama version, machine/resources and inference settings. Do not infer historical version from the current container. If that evidence cannot be recovered, collect fresh single-model accuracy after approval instead. There is deliberately no pre-approved reuse file in this change.

## Runner CLI and official commands

The following are commands for future authorized collection, not commands executed in this review. Substitute the actual host and a new unique suffix. For each invocation, the service must already have the matching environment below; use the team's existing Docker start/recreate procedure. Set `RUN_ID` to the command's `--run-id` before starting the service. Merely changing the shell variable does not change an already running container.

| ID | Required service environment besides RUN_ID |
|---|---|
| llama3.2-1b | `MODE=single`, `MODEL=llama3.2:1b` |
| gemma3-4b | `MODE=single`, `MODEL=gemma3:4b` |
| mistral-7b-instruct | `MODE=single`, `MODEL=mistral:7b-instruct` |
| cascade_s1 | `MODE=cascade`, `SMALL_MODEL=llama3.2:1b`, `LARGE_MODEL=gemma3:4b`, `RULE=length`, `RULE_SETTING=241` |
| cascade_s2 | `MODE=cascade`, `SMALL_MODEL=llama3.2:1b`, `LARGE_MODEL=gemma3:4b`, `RULE=length`, `RULE_SETTING=289` |

```powershell
python scripts/run_a2_accuracy.py --config llama3.2-1b --run-id a2_llama3.2-1b_accuracy_r1 --url http://SERVICE_HOST:8000
python scripts/run_a2_accuracy.py --config gemma3-4b --run-id a2_gemma3-4b_accuracy_r1 --url http://SERVICE_HOST:8000
python scripts/run_a2_accuracy.py --config mistral-7b-instruct --run-id a2_mistral-7b-instruct_accuracy_r1 --url http://SERVICE_HOST:8000
python scripts/run_a2_accuracy.py --config cascade_s1 --run-id a2_cascade_s1_accuracy_r1 --url http://SERVICE_HOST:8000
python scripts/run_a2_accuracy.py --config cascade_s2 --run-id a2_cascade_s2_accuracy_r1 --url http://SERVICE_HOST:8000
```

`--timeout` defaults to 630 seconds per HTTP request for all five configurations (two consecutive 300-second backend inference calls plus 30 seconds of service overhead). `service/main.py` reads `OLLAMA_TIMEOUT` with default `300` and passes it to each `/api/generate` call; the frozen length cascade can make two such calls. Verify the deployed value before collection; if it differs, explicitly use `--timeout` at least twice that value plus overhead. Warm-up should populate model metadata before collection. This changes neither the backend timeout nor the benchmark timeout. Requests are sequential, once per row. HTTP redirects and retries are disabled. A complete run sends exactly 88 POST requests; a crash can leave fewer, and that partial run cannot be scored. Reusing its ID is refused. A fresh rerun is a separate experiment, never an overwrite or an implicit retry.

Every HTTP failure, timeout, transport error, malformed success body, or missing/mismatched response ID is recorded as `Failure` and incorrect. Unknown category text in an otherwise valid response is `Unclassified` and incorrect. Correctness is recalculated against golden labels. `X-Request-ID` is the authoritative response ID; a successful JSON body's `id` must match it. The runner does not substitute the body ID when the header is missing.

### Verified import, after provenance is resolved

```powershell
python scripts/run_a2_accuracy.py --config gemma3-4b --run-id a2_gemma3-4b_accuracy_import1 --import-a1 results/accuracy/gemma3_4b_predictions.csv --reuse-evidence PATH_TO_REVIEWED_APPROVAL.json
```

Use `results/accuracy/llama3.2_1b_predictions.csv` for `llama3.2-1b` and `results/accuracy/mistral_7b_predictions.csv` for `mistral-7b-instruct`. Import filters to the frozen even IDs before validating outcomes, requires all 88 once, and preserves failures. It sends no HTTP requests. It rejects label, model, correctness and source hash mismatches. Cascade import is forbidden.

The reviewer-authored approval JSON must contain:

```json
{
  "config": "gemma3-4b",
  "eligible": true,
  "reviewer": "responsible reviewer name",
  "reviewed_at": "ISO-8601 date/time",
  "service_run_id": "exact historical RUN_ID from approved logs",
  "source_sha256": "SHA-256 of the exact historical prediction CSV",
  "model_digest": "full 64-character expected model digest",
  "evidence": [
    {"id": "historical-runtime", "path": "relative/path/to/evidence", "sha256": "SHA-256 of that file"}
  ],
  "checks": {
    "model_digest": {"verified": true, "explanation": "How historical and A2 digests match", "evidence_ids": ["historical-runtime"]},
    "classification_prompt": {"verified": true, "explanation": "How deployed prompts match", "evidence_ids": ["historical-runtime"]},
    "category_matching": {"verified": true, "explanation": "How deployed matching behaviour matches", "evidence_ids": ["historical-runtime"]},
    "ollama_version": {"verified": true, "explanation": "Actual historical version and resolution of discrepancy", "evidence_ids": ["historical-runtime"]},
    "machine_resources": {"verified": true, "explanation": "Same host, CPU and RAM allocations", "evidence_ids": ["historical-runtime"]},
    "inference_settings": {"verified": true, "explanation": "Same effective inference settings", "evidence_ids": ["historical-runtime"]}
  }
}
```

This is a schema illustration, not approval. Paths resolve relative to the approval file. Each check must cite existing hashed evidence. The software validates structure, source identity and checks marked verified; it cannot judge whether a reviewer's prose actually proves historical compatibility. That judgment remains with the team. The approval, original A1 CSV and cited files are archived in the run folder. A1 sources are not edited.

## Scorer CLI

Supply exactly one complete run for each of the five configurations. Choose the attempts explicitly; the scorer never selects the best run. Supply all five logs collected from the service host. All output is offline; no model requests occur.

```powershell
python scripts/summarize_a2_accuracy.py `
  --run results/a2/accuracy/a2_llama3.2-1b_accuracy_r1 `
  --run results/a2/accuracy/a2_gemma3-4b_accuracy_r1 `
  --run results/a2/accuracy/a2_mistral-7b-instruct_accuracy_r1 `
  --run results/a2/accuracy/a2_cascade_s1_accuracy_r1 `
  --run results/a2/accuracy/a2_cascade_s2_accuracy_r1 `
  --log llama3.2-1b=results/logs/a2_llama3.2-1b_accuracy_r1.log `
  --log gemma3-4b=results/logs/a2_gemma3-4b_accuracy_r1.log `
  --log mistral-7b-instruct=results/logs/a2_mistral-7b-instruct_accuracy_r1.log `
  --log cascade_s1=results/logs/a2_cascade_s1_accuracy_r1.log `
  --log cascade_s2=results/logs/a2_cascade_s2_accuracy_r1.log `
  --summary-id reviewed_r1
```

Substitute an approved import directory for a single model if appropriate. A missing/partial configuration prevents publishing an eligibility table. Outputs go to `results/a2/accuracy/summary_reviewed_r1/`; this directory must not already exist.

Gemma's test results define the floors. For each comparison use exact rational arithmetic: `100 * correct / total - tolerance`, with tolerance 10 for overall and 15 for each true category. No floor clipping or rounding is applied before pass/fail. A model qualifies only if it passes the overall and all seven category floors. All failures count in the overall denominator of 88 and their true-category denominator. Percentages are serialized as full float representations for display; the pass/fail decisions use fractions.

The printed eligibility table and `eligibility.csv` are the handoff to Zhengda: every qualifying single must be speed-tested. Both cascades must be speed-tested even when `accuracy_eligible=false`. Until real or approved imported runs exist, there is no official eligibility verdict for any candidate.

## Input/output contract for Yuhao

A repeatable implementation smoke suite is supplied at `tests/test_a2_accuracy_workflow.py`; it does not replace independent regression testing. Yuhao should test the public functions and CLI independently, using synthetic fixtures. Functions `load_run(folder, tickets)`, `reconcile(rows, log_path, tickets, service_run_id=None)` and `score_runs(runs, logs, tickets, service_run_ids=None)` are import-safe and do not call models. `run_a2_accuracy` also exposes `load_test`, `validate_health`, `validate_reuse` and `import_a1`. The runner/scorer use the frozen dataset by default; synthetic fixtures should patch module dependencies and output roots in a temporary directory, never change the production frozen hash.

### Per-run directory

| File | Schema/purpose |
|---|---|
| `manifest.json` | `schema_version=1`, `run_id`, `config`, `source` (`live` or `a1_import`), `started_at`, `test_sha256` (canonical frozen-set hash), `expected_config`, `timeout`, `runner_sha256`, `frozen_commit` |
| `predictions.csv` | Columns in order: `row,config,run_id,source,golden_label,prediction,correct,http_status,request_id,latency_seconds,error` |
| `health_before.json` (live) | Raw preflight `http_status`, `headers`, `body`; body must parse as the existing service `/health` JSON |
| `health_after.json` (live) | Raw post-collection `http_status,headers,body,error` and `validation_issues` list; empty means configuration/health/residency passed. Transport failures use status 0. |
| `requests.jsonl` (live) | Exactly one `attempt` then one `response` per prediction, in row order. Attempt: `event,row,payload` where payload has `narrative,row_id`. Response: `event,row,http_status,headers,body,error`. Flushed after each event; raw text retained |
| `complete.json` | Written only after all 88 records: `rows`, `predictions_sha256`, `completed_at`, `failures`, `health_after_sha256` (null for import). Written even when post-run validation fails. Its absence means partial/unscorable |
| `a1_source.csv`, `reuse_approval.json`, `reuse_evidence/0`, `1`, ... (import) | Unmodified original source and cited files; approval evidence paths rewritten to archive-relative paths in approval list order; hashes rechecked by the scorer |

`row` is a positive even integer. Labels use exact service category spelling. `prediction` is one of seven categories, `Unclassified`, or `Failure`. CSV booleans are `True`/`False` (reader is case-insensitive). HTTP status 0 means no response; otherwise it is the received HTTP status. Latency is a finite nonnegative client elapsed time in seconds. `error` is nonempty for a failure; successful or unclassified records have an empty error. Empty request IDs are allowed only on failures. Nonempty request IDs must be unique within the run. A1 import can retain blank IDs on failed historical rows.

The scorer requires all 88 IDs exactly once, matching gold labels, metadata, manifest and completion hash. It recomputes correctness, verifies live records against their raw journal and preflight, and verifies imported records against their archived A1 source and reuse approval. Unknown extra CSV columns are tolerated; required columns may not be omitted.

### All-configuration log input and reconciliation

Only integer `row_id` values `-1`, `-2`, and `-3` explicitly identify accuracy warm-ups. These entries are excluded from reconciliation and reload flags only when their request IDs are absent from predictions. They remain in the archived raw logs. Missing/null row IDs, arbitrary other non-test IDs, timestamps, and free-text warm-up claims do not authorize exclusion: those entries remain unmatched evidence. Official request IDs always take precedence; duplicate test-row detection remains active. Historical or existing unmarked warm-ups need review rather than automatic exclusion.

Input is the existing service's JSON Lines log, not a new service schema. Select entries where `run_id` matches the prediction run and `endpoint` is `POST /tickets`. Join exclusively on `request_id`; require matching `row_id` and HTTP status. Duplicate request IDs, duplicate service attempts for a test row, or contradictory IDs are errors. Missing logs and blank prediction IDs are explicitly reported as unmatched evidence, without changing predictions. Other runs and endpoints are ignored.

Single-model entries require `mode=single`, the configured `model`, and matching `final_model` when present (required on live successes). Successful entries require a matching category. Failed single requests can omit `final_model`; they remain in the denominator.

Cascade matched entries require `mode`, `small_model`, `large_model`, `rule`, `rule_setting` to match the frozen configuration. `routing` must be `decided` or `not_reached`. Decided entries require boolean `escalated`, valid `small_category`, and `escalation_reason` consistent with the original narrative length and frozen rule. Successful requests also require the expected `final_model` and matching `category`.

`not_reached` failures count as unknown routing. A failed request without an ID remains unknown; no row-only fallback invents a routing decision. Large-stage failures with a logged decision still count as escalated and incorrect. Escalation fraction is `escalated / (accepted + escalated)`; it excludes unknown routing, not failed decided requests. All three groups remain in overall accuracy. Empty groups have blank/null accuracy, not zero; a zero known-decision denominator produces blank/null escalation fraction. Unclassified completed requests remain incorrect even when routing and final model are known.

### Summary files

| File | Columns |
|---|---|
| `overall.csv` | `config,category` (`overall`), `correct,wrong,total,accuracy_percent,floor_percent,passes` |
| `per_category.csv` | Same columns, seven rows per configuration using true category |
| `floors.csv` | `category,reference_correct,total,reference_accuracy_percent,tolerance_pp,floor_percent` (overall plus seven categories) |
| `eligibility.csv` | `config,overall_pass,all_categories_pass,accuracy_eligible,must_speed_test,reason` |
| `confusion_matrices.csv` | Long-form matrix: `config,golden_label,prediction,count`; all 7 x 9 cells per configuration, including zero cells, failures and unclassified |
| `cascade_escalation.csv` | `config,total,known_decisions,escalation_fraction`, then `accepted_count,accepted_correct,accepted_accuracy_percent`, equivalent `escalated_*` and `unknown_*` columns |
| `cascade_routing.csv` | `config,row,request_id,routing_group` (`accepted`, `escalated`, `unknown`), `reason,correct` |
| `<config>.service.jsonl` (all five) | Copies of supplied raw logs |
| `service_reconciliation.csv` | `config,row,request_id,routing_group,reason,correct,evidence_status,load_durations_ns,possible_reload`. Status is `matched`, `unmatched_prediction`, or `unmatched_service_log`; single routing is `not_applicable` when matched. No ID is synthesized. |
| `validation.json` | `health` (config/issues pairs), `unmatched_evidence`, `possible_reload_requests`, `review_required` |
| `provenance.json` | Schema version, test/scorer hashes, input run paths and hashes, input log paths and hashes |
| `complete.json` | Map of generated filenames to SHA-256 hashes; absence means output is incomplete |

Per-ticket predictions remain in their input run directories. The summary does not rewrite them. Preserve run and summary directories together.

### Error behaviour and independent test targets

- CLI input, preflight, provenance, incomplete evidence, reconciliation and overwrite errors exit 2 with an `ERROR:` message. Argument-parser errors also exit 2. Contradictory evidence prevents summary creation; unmatched evidence and post-run health problems produce a preserved summary marked for review; a later disk error can leave an incomplete output directory without `complete.json`.
- A completed runner exits 2 if post-run health validation fails, after preserving predictions and `complete.json`. The scorer revalidates post-run evidence and its completion hash, and exits 2 after writing all summary files when health, unmatched evidence or possible reloads require review. Summary completion denotes file integrity, not validation approval. A completed runner otherwise exits 0 even if individual requests failed. Those are data, not a reason to drop tickets or automatically rerun. A summary exits 0 even if configurations fail floors. Eligibility is in the output, not the process status.
- Both CLIs refuse existing destination directories. Partial outputs are retained. Exceptions do not delete evidence. An interrupted live run may contain an attempt without a response and cannot be scored.
- Test exact threshold boundaries, unclassified escalation, small-stage versus large-stage failures, missing response IDs, body/header ID mismatch, wrong health/missing residency, no retries, incomplete runs, duplicate/missing IDs, incorrect labels, raw-evidence mismatch, and rejected unverified imports.
- Test the overall and all seven category boundaries using exact fractions (including equality), unsuccessful/unclassified denominator inclusion, all-unknown routing, empty accepted/escalated groups, missing or conflicting log IDs, and mandatory speed testing for failed cascades. Do not use official outcomes to design a new rule.

## Implementation smoke validation

An ad hoc temporary local HTTP fixture exercised five synthetic 88-ticket runs: 440 distinct POSTs with no retries, including HTTP 502 failures, an unclassified answer, small-stage unknown routing and a decided large-stage failure. The scorer reconciled logs, kept all 88 tickets in each denominator, represented failures/unclassified explicitly, and produced the eligibility table and all CSV outputs. Guards rejected overwritten run/summary directories, wrong threshold/residency, a log row mismatch, changed predictions and an unapproved A1 import. Fixtures and generated evidence were kept in the OS temporary directory, not in `results/`. These are smoke checks only; Yuhao's independent regression testing remains pending.

Additional offline synthetic checks passed for exact per-category floor equality, eight versus nine losses against an 88/88 reference overall floor, exclusion of an ineligible single from speed testing, mandatory speed testing of ineligible cascades, all-unknown routing and null empty-group metrics. A synthetic approved import preserved a failed record, ignored an unrelated odd row, archived its evidence and passed scorer revalidation. A changed frozen input was rejected. Both new scripts passed Python syntax compilation. None of these fixtures is official A2 evidence.


## Post-run review and portable evidence

Inspect `health_after.json` for unchanged mode/models/rule/threshold and, for cascades, both model names in `loaded_models` with `all_configured_loaded=true`. The scorer independently validates the response and its hash. A failure never deletes completed predictions. Resolve the validation issue before treating the eligibility table as official.

Review `service_reconciliation.csv` alongside the raw logs. Load durations are retained in nanoseconds; any available `ollama_load_ns`, `small_load_ns` or `large_load_ns` above 1,000,000,000 flags `possible_reload=true`, following the existing residency check's one-second criterion. This is a review signal, not proof of eviction. A healthy final snapshot cannot rule out intermediate eviction; missing timing fields cannot prove its absence. Unmatched service entries do not add to the 88-ticket accuracy/routing denominators. No row-only match replaces a missing request ID.

Approved historical imports must identify `service_run_id` in their approval; this is recorded in summary provenance and used only for the log join. Historical logs may omit `mode` and `final_model`; only for verified imports, the logged configured `model` and approved runtime evidence establish those facts. Existing fields must still match. Historical entries outside the selected even-row set remain explicitly unmatched for review, rather than being silently discarded. Historical blank IDs remain blank. Reuse remains blocked until provenance is verified.

Published provenance uses repository-relative paths, or only a basename plus content hash for external inputs. The runner omits the service URL from the manifest. Archived approval paths refer to `reuse_evidence/<index>`. Preserve run and summary directories together; external source basenames are labels, not resolvable absolute locations. Review free-text approval explanations and copied evidence before publication for credentials, usernames, laptop names and local paths; generated path sanitization does not sanitize arbitrary source contents.

## Environment capture (PowerShell, service host)

Execute these read-only commands immediately before each future authorized run, after configuring/warming the service. They do not send accuracy requests. Substitute the chosen configuration and exact RUN_ID. Store environment evidence separately first because the runner refuses a pre-existing run directory; copy it into the completed run afterward. Do not publish unrestricted `docker inspect`, `docker info`, or environment dumps.

```powershell
$config = 'cascade_s1'
$runId = 'a2_cascade_s1_accuracy_r1'
$evidence = "results/a2/environment/$runId"
New-Item -ItemType Directory -Path $evidence -ErrorAction Stop | Out-Null

docker version --format '{{json .}}' | ConvertFrom-Json | ForEach-Object {
  [ordered]@{ ClientVersion=$_.Client.Version; ServerVersion=$_.Server.Version; ServerApiVersion=$_.Server.ApiVersion }
} | ConvertTo-Json | Set-Content "$evidence/docker_version.json" -Encoding UTF8
docker compose version --short | Set-Content "$evidence/compose_version.txt" -Encoding UTF8
docker info --format '{{json .}}' | ConvertFrom-Json | ForEach-Object {
  [ordered]@{ NCPU=$_.NCPU; MemTotal=$_.MemTotal }
} | ConvertTo-Json | Set-Content "$evidence/docker_resources.json" -Encoding UTF8

$containers = foreach ($name in @('triage', 'ollama')) {
  $cid = docker compose ps -q $name
  if (-not $cid) { throw "Missing running container: $name" }
  $info = (docker inspect $cid | ConvertFrom-Json)[0]
  $allowed = '^(MODEL|MODE|SMALL_MODEL|LARGE_MODEL|RULE|RULE_SETTING|RUN_ID|NUM_CTX|KEEP_ALIVE|OLLAMA_TIMEOUT|OLLAMA_NUM_PARALLEL|OLLAMA_MAX_QUEUE)='
  [ordered]@{ Service=$name; Image=$info.Config.Image; ImageId=$info.Image;
    NanoCpus=$info.HostConfig.NanoCpus; Memory=$info.HostConfig.Memory;
    CpuQuota=$info.HostConfig.CpuQuota; CpuPeriod=$info.HostConfig.CpuPeriod;
    CpusetCpus=$info.HostConfig.CpusetCpus; Environment=@($info.Config.Env | Where-Object { $_ -match $allowed }) }
}
$containers | ConvertTo-Json -Depth 6 | Set-Content "$evidence/containers.json" -Encoding UTF8
Invoke-RestMethod http://localhost:11434/api/version | ConvertTo-Json | Set-Content "$evidence/ollama_version.json" -Encoding UTF8
$tags = Invoke-RestMethod http://localhost:11434/api/tags
$tags.models | Select-Object name,digest | ConvertTo-Json | Set-Content "$evidence/model_digests.json" -Encoding UTF8
Invoke-RestMethod http://localhost:8000/health | ConvertTo-Json -Depth 6 | Set-Content "$evidence/health.json" -Encoding UTF8
Invoke-RestMethod http://localhost:11434/api/ps | ConvertTo-Json -Depth 8 | Set-Content "$evidence/residency.json" -Encoding UTF8
# Read deployed source without importing it or invoking inference.
docker compose exec -T triage cat /app/main.py | Set-Content "$evidence/deployed_main.py" -Encoding UTF8
Select-String -Path "$evidence/deployed_main.py" -Pattern 'OLLAMA_TIMEOUT|NUM_CTX|KEEP_ALIVE|temperature|num_predict|think|options' |
  ForEach-Object { $_.Line } | Set-Content "$evidence/inference_settings.txt" -Encoding UTF8

$active = @($containers | Where-Object { $_.Service -eq 'triage' })[0].Environment
if ($active -notcontains "RUN_ID=$runId") { throw 'RUN_ID mismatch' }
$expected = @{
  'llama3.2-1b' = @('MODE=single','MODEL=llama3.2:1b')
  'gemma3-4b' = @('MODE=single','MODEL=gemma3:4b')
  'mistral-7b-instruct' = @('MODE=single','MODEL=mistral:7b-instruct')
  'cascade_s1' = @('MODE=cascade','SMALL_MODEL=llama3.2:1b','LARGE_MODEL=gemma3:4b','RULE=length','RULE_SETTING=241')
  'cascade_s2' = @('MODE=cascade','SMALL_MODEL=llama3.2:1b','LARGE_MODEL=gemma3:4b','RULE=length','RULE_SETTING=289')
}
foreach ($setting in $expected[$config]) {
  if ($active -notcontains $setting) { throw "Active configuration mismatch: $setting" }
}
foreach ($setting in @('NUM_CTX=4096','KEEP_ALIVE=30m')) {
  if ($active -notcontains $setting) { throw "Inference setting mismatch: $setting" }
}
$backendTimeout = @($active | Where-Object { $_ -like 'OLLAMA_TIMEOUT=*' })
if ($backendTimeout.Count -and $backendTimeout[0] -ne 'OLLAMA_TIMEOUT=300') { throw 'Review accuracy timeout budget' }
$expectedDigests = @{
  'llama3.2:1b' = 'baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878'
  'gemma3:4b' = 'a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a'
  'mistral:7b-instruct' = '6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf'
}
foreach ($model in $expectedDigests.Keys) {
  $match = @($tags.models | Where-Object { $_.name -eq $model })
  if ($match.Count -ne 1 -or $match[0].digest -ne $expectedDigests[$model]) { throw "Digest mismatch: $model" }
}
$resources = Get-Content "$evidence/docker_resources.json" -Raw | ConvertFrom-Json
if ($resources.NCPU -ne 22 -or [math]::Abs($resources.MemTotal / 1GB - 9.713) -gt 0.01) { throw 'Docker allocation differs from recorded A1 environment' }
$containers | ForEach-Object {
  if ($_.NanoCpus -ne 0 -or $_.Memory -ne 0 -or $_.CpuQuota -gt 0 -or $_.CpusetCpus) { throw 'Unexpected container resource limit' }
}
$versions = Get-Content "$evidence/docker_version.json" -Raw | ConvertFrom-Json
$composeVersion = (Get-Content "$evidence/compose_version.txt" -Raw).Trim()
$composeVersionMatches = $composeVersion -cmatch '^v?2\.40\.0(?:-desktop\.1)?$'
$ollamaVersion = (Get-Content "$evidence/ollama_version.json" -Raw | ConvertFrom-Json).version
if ($versions.ServerVersion -ne '28.5.1' -or -not $composeVersionMatches -or $ollamaVersion -ne '0.35.0') {
  throw 'Version differs from recorded environment; review before collection'
}
$ollamaEnv = @($containers | Where-Object { $_.Service -eq 'ollama' })[0].Environment
foreach ($setting in @('OLLAMA_NUM_PARALLEL=1','OLLAMA_MAX_QUEUE=512')) {
  if ($ollamaEnv -notcontains $setting) { throw "Ollama setting mismatch: $setting" }
}
$deployedSource = (Get-Content "$evidence/deployed_main.py" -Raw).Replace("`r`n", "`n").TrimEnd()
$reviewedSource = (Get-Content service/main.py -Raw).Replace("`r`n", "`n").TrimEnd()
if ($deployedSource -cne $reviewedSource) { throw 'Deployed source differs from reviewed inference implementation' }
Get-Content "$evidence/docker_version.json", "$evidence/compose_version.txt", "$evidence/ollama_version.json", "$evidence/inference_settings.txt"
# Compare versions to the reviewed environment and the deployed PROMPT/category matching
# to service/main.py. Confirm temperature=0, num_predict=16, conditional think=False,
# and the 300-second default when OLLAMA_TIMEOUT is absent. Record any discrepancy;
# do not assume the historical 0.40.0/0.35.0 discrepancy is resolved by current output.
Get-ChildItem $evidence -File | ForEach-Object {
  [ordered]@{ File=$_.Name; SHA256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower() }
} | ConvertTo-Json | Set-Content "$evidence/hashes.json" -Encoding UTF8
# ONLY after a future authorized run has completed, preserve evidence with it:
# Copy-Item -LiteralPath $evidence -Destination "results/a2/accuracy/$runId/environment" -Recurse
```

Check `$LASTEXITCODE` after Docker commands and stop if any command fails. Compare captured versions with `docs/a2_test_environment.md` (Engine 28.5.1, Compose 2.40.0, Ollama 0.35.0 currently recorded); the evidence must establish actual versions, not merely desired image tags. Document reviewed differences before official testing. Preserve environment files and their hashes with the official run, including runs with a post-run validation issue.

## Repeatable synthetic validation after targeted improvements

```powershell
python -m unittest discover -s tests -p test_a2_accuracy_workflow.py -v
```

Five implementation smoke test methods passed, including subcases: all five 88-row collections and offline CLI scoring (440 simulated POSTs); identical 630-second defaults; retained 502s; single-model mode/model/final-model/category/status/row mismatches; wrong RUN_ID and unmatched evidence without ID fabrication; client timeout preservation; approved historical log identity mapping; possible reload detection; repository-independent provenance; and post-run transport, HTTP, malformed JSON, configuration and residency failures. Completed predictions and completion markers survived all post-run failures. Changed post-run health evidence produced a complete summary with validation issues and exit 2. These fixtures mock the HTTP transport, send no network requests, and use temporary output directories. The earlier smoke results above describe prior validation; Yuhao's independent regression remains pending.

Final pre-commit checks: the Compose comparison accepts `v2.40.0-desktop.1` as the recorded host build, as well as plain `2.40.0` with an optional `v`. It preserves the exact captured version and rejects other core versions or unreviewed suffixes. Synthetic warm-up coverage verifies reserved-ID exclusion, retention of ambiguous/unmatched official evidence, duplicate test-row rejection, and precedence of official request IDs. These remain implementation smoke tests; Yuhao's independent regression suite is still required.
