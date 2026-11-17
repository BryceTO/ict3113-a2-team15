# ICT3113 Assignment 2 — Fast Triage Within an Accuracy Floor (Team 15)

The Assignment 1 complaint triage service, extended with a **cascade**: a smaller model classifies every ticket, a rule decides whether to accept its answer, and otherwise the ticket is escalated to a larger model. Assignment 2 measures every Assignment 1 model alone and the cascade at two settings, and recommends the fastest configuration that stays within the client's accuracy limits.

Assignment 1 is the starting point and is tagged **`a1-baseline`** in this repository (`git checkout a1-baseline` shows it exactly as submitted).

## Team
| Name | Student ID | A2 role |
|---|---|---|
| BRYCE TEOH YI | 2401073 | Service, cascade implementation, residency check |
| BRYAN KOH KAI XUN | 2400960 | Workload, trade-off analysis, limitations |
| AROKKIASAMY LIANDOMAXIN | 2400643 | Escalation rule, predictions, accuracy |
| TOH ZHENGDA | 2302113 | JMeter, speed tests |
| LIN YUHAO | 2400703 | Golden-set split, ML evaluation tests, evidence and deck |

## What is fixed and what changed from Assignment 1
**Unchanged:** the three candidate models (same tags and digests), the classification prompt and seven categories, the golden set and its labels, the endpoints and their responses, CPU-only Ollama 0.35.0 with the same settings, the test machines and their CPU/RAM allocation, and the open-loop JMeter method.

**Changed:** `POST /tickets` can run as a cascade (`MODE=cascade`). The log records which model gave the final answer and whether the ticket was escalated. A `GET /health` endpoint was added. No classification results are cached.

## System overview
```
JMeter (separate machine) -> Triage service (FastAPI, :8000) -> Ollama (CPU, :11434)
                                   |                              small model  -> rule -> accept
                                SQLite                            large model  (escalated tickets)
```
`POST /tickets` is still synchronous: it returns only after the final model has answered.

### Endpoints
| Endpoint | Description |
|---|---|
| `POST /tickets` | Body `{"narrative": "...", "row_id": 15123}` (`row_id` optional, logged only). Classifies, stores one result, returns `{"id", "category"}`. The caller cannot tell which model answered. |
| `GET /search?q=<text>` | Stored tickets whose narrative contains the text (max 100) |
| `GET /stats` | Counts of stored tickets by category |
| `GET /health` | Service status, configured models, and which models Ollama currently has loaded (`all_configured_loaded`) |

Categories: Credit reporting, Debt collection, Mortgage, Credit card, Bank account or service, Consumer loan, Money transfer or service.

## Run it
Requirements: Docker Desktop (with Compose). From the repo root:
```
docker compose up -d --build
docker compose exec ollama ollama list
```
The models are stored in the Docker volume `ict3113-a1-team15_ollama_models`, shared with the Assignment 1 setup, so A2 uses the exact models pulled in A1 (same digests). On a machine without them, pull the three candidates with `docker compose exec ollama ollama pull <tag>` and check the digests match `docs/candidate_models.md`.

Only one of the A1 and A2 setups can run at a time (they use the same ports). Stop the other with `docker compose down` in its folder.

### Configuration (environment variables, set per run)
| Variable | Default | Purpose |
|---|---|---|
| `MODE` | `single` | `single`: `MODEL` classifies every ticket (A1 behaviour). `cascade`: small model first, rule, large model if escalated |
| `MODEL` | `llama3.2:1b` | Model used when `MODE=single` |
| `SMALL_MODEL`, `LARGE_MODEL` | — | Cascade pair (`MODE=cascade`). Both must stay loaded together; see Residency check |
| `RULE` | — | `category`, `length` or `confidence` |
| `RULE_SETTING` | — | `category`: small-model categories to **accept**, separated by `;`. `length`: maximum narrative length in characters to accept. `confidence`: not used |
| `RUN_ID` | `dev` | Name of the run. Each run gets its own log `results/logs/<RUN_ID>.log` and its own empty database |
| `NUM_CTX` | `4096` | Context window, identical for every model and configuration |
| `KEEP_ALIVE` | `30m` | Keeps models loaded between requests |
| `OLLAMA_VERSION` | `0.35.0` | Ollama image version (pinned) |

Ollama runs with `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_QUEUE=512`, unchanged from A1. The brief does not allow changing Ollama inference settings between configurations.

The service refuses to start with an incomplete or invalid cascade configuration (for example an unknown category in `RULE_SETTING`).

The full escalation rule, the chosen pair and the two settings are documented in `docs/escalation_rule.md`.

**PowerShell examples.** `$env:` values stay set in that terminal window, so always set `MODE` explicitly:
```
# single model
$env:MODE="single"; $env:MODEL="gemma3:4b"; $env:RUN_ID="a2_gemma3-4b_speed_r1"; docker compose up -d

# cascade
$env:MODE="cascade"; $env:SMALL_MODEL="llama3.2:1b"; $env:LARGE_MODEL="gemma3:4b"; $env:RULE="category"; $env:RULE_SETTING="Bank account or service"; $env:RUN_ID="a2_cascade_s1_speed_r1"; docker compose up -d
```
Check the active configuration with `Invoke-RestMethod http://localhost:8000/health`.

**Run IDs** start with `a2_` and use one configuration ID everywhere: `a2_<config>_<test>_r<N>`, for example `a2_cascade_s1_speed_r1` or `a2_gemma3-4b_accuracy`. Write a model tag's `:` as `-`, because the run ID becomes a file name.

### Stop
```
docker compose down
```

## Logging
Every request (including errors) is one JSON line in `results/logs/<RUN_ID>.log`.

| Field | Meaning |
|---|---|
| `ts`, `run_id`, `request_id` | When, which run, and the ID returned in the `X-Request-ID` header |
| `endpoint`, `status`, `latency_ms` | e.g. `POST /tickets`, `200` / `422` / `502`, total time inside the service |
| `row_id`, `narrative_chars`, `category` | `POST /tickets`: dataset row, ticket length, final category returned |
| `mode`, `model`, `final_model` | Configuration, and the model that gave the final answer |
| `escalated`, `escalation_reason` | Cascade decision: `category_accepted`, `category_not_accepted`, `short_enough`, `too_long`, `confidence_high`, `confidence_low`, `unclassified` |
| `routing` | Cascade only: `decided` once the escalation decision was made, `not_reached` if the small model failed first. Use `decided` tickets as the escalation-fraction denominator |
| `small_model`, `large_model`, `rule`, `rule_setting` | Cascade configuration |
| `small_category`, `small_ms`, `small_load_ns` | Small model's answer, time, and load time (ns) |
| `large_category`, `large_ms`, `large_load_ns` | Large model's answer and timings, only when escalated |
| `confidence_answer`, `confidence_ms` | `RULE=confidence` only: the extra HIGH/LOW call |
| `ollama_ms`, `ollama_load_ns`, `prompt_eval_count`, `eval_count` | Time spent in Ollama, and single-mode load time and token counts. A large load time means a model was (re)loaded |
| `error`, `error_stage` | Failures: `model` (single), `small`, `rule` or `large` (cascade) |
| `results` | `GET /search` only: number of matches |

`Unclassified` means the model's output named no valid category. It counts as wrong, and in the cascade it is always escalated. Logs are committed to Git as evidence. Do not delete or edit them.

## Tests and checks
**Service tests** (fake Ollama, no models needed), run inside the service image:
```
docker compose build triage
docker compose run --rm --no-deps -v "${PWD}/tests:/app/tests" triage python -m unittest discover -s tests/service -v
```
They cover the single mode, cascade accept/escalate/unclassified, small and large backend errors, the same prompt and options for both models, no result caching, the length and confidence rules, `/search`, `/stats` and `/health`.

**Residency check** (on the service host, with `docker compose up -d` running):
```
powershell -ExecutionPolicy Bypass -File scripts\check_residency.ps1 -Small <small tag> -Large <large tag>
```
It records the environment, digests and Ollama settings, loads both models, alternates tickets between them, captures `ollama ps` each time, and reports **RESIDENT** or **NOT RESIDENT**. Evidence is saved in `results/a2/residency/<timestamp>_<pair>/`. A cascade is only tested with a pair that is resident on the A1 test machine.

## Repository layout
Assignment 2 work lives in new files and the `results/a2/` folder. Everything else is the Assignment 1 baseline, kept for reuse and reference.

```
docker-compose.yml        Service + Ollama (CPU only)                          [A1, updated for A2]
service/                  Triage service: single mode and cascade                [A1, updated for A2]
tests/service/            Service behaviour tests                                [A2]
tests/ml/                 ML evaluation tests and synthetic fixtures             [A2]
golden_set/               Frozen golden set; a2_split.csv = tuning/test split    [A1 + A2]
docs/escalation_rule.md   Cascade rule, pair and two settings (attachment)       [A2]
docs/                     A1 candidate models, playbook, environment; A2 docs    [A1 + A2]
predictions/              A1 prediction record; a2_prediction_record.md          [A1 + A2]
jmeter/                   JMeter plan, run script; a2_workload_rows.csv          [A1 + A2]
scripts/                  A1 scripts; A2 residency, split, tuning, summaries     [A1 + A2]
results/logs/             Service request logs, one per run (A2 run IDs start a2_) [A1 + A2]
results/a2/residency/     Residency (ollama ps) evidence                         [A2]
results/a2/accuracy/      Test-set predictions, floors, confusion matrices       [A2]
results/a2/jtl/           Raw A2 JMeter results and run metadata                 [A2]
results/a2/summary/       A2 speed tables and chart inputs                       [A2]
results/accuracy/, results/jtl/, results/summary/, analysis/    A1 evidence      [A1]
```
The Team 15 dataset rows are not in the repository. Each tester places the extract at `context/team15_rows.csv`, which is git-ignored.

## Evidence rules
- The golden-set tuning/test split is committed **first**, before any tuning or measurement.
- The escalation rule (`docs/escalation_rule.md`), the A2 prediction record and the speed-test workload row list are committed **before** the first A2 benchmark run. Do not edit them afterwards.
- The rule is designed on the **tuning set** (odd rows) only. Every reported accuracy figure uses the **test set** (even rows).
- Do not rewrite Git history (no force push or reset).
- Keep the raw `.jtl` files and service logs for every reported run. Every figure on slides 4–7 must trace back to them.

## Assignment 1 baseline
The A1 service, results and procedures are unchanged in this repository and tagged `a1-baseline`. A1 load runs followed `docs/test_playbook.md`, with run IDs such as `llama3.2-1b_stretch_run1`; A1 results are in `results/accuracy/`, `results/jtl/`, `results/summary/` and `results/logs/`.
