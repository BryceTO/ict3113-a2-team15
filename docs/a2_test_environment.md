# A2 Test Environment

Owner: Performance Testing Lead (load generator, run checks), with the Model & Accuracy Lead (service host).

The brief requires the A2 tests to run on the same machine, CPU and RAM as A1, with software versions, model digests and Ollama settings recorded before the first run and re-checked before each configuration (Step 4). This file is that record. The A1 description is `docs/test_environment.md`.

Placeholders are marked **`TODO`**. Fill them in before the first official A2 run, then do not edit the recorded values. Add any later change as a new row in section 6, with its reason.

## 1. Machines

The same two machines as A1. The load generator stays a separate physical machine from the service.

| | Service host (triage service + Ollama) | Load generator (JMeter) |
|---|---|---|
| Machine | The A1 service host laptop | The A1 load-generator laptop |
| CPU | Intel Core Ultra 7 155H, 16 cores / 22 threads | Intel Core i5-1235U, 10 cores / 12 threads |
| Memory | 16 GB (15.61 GB usable) | 16 GB (15.7 GB usable) |
| Operating system | Windows 11 Home, 64-bit | Windows 11 Home, 64-bit |
| Software | Docker Desktop 4.48.0 (WSL 2 backend), Docker Engine 28.5.1, Docker Compose 2.40.0, Ollama image `ollama/ollama:0.35.0`, CPU only | Apache JMeter 5.6.3, Java 8 (1.8.0_441), Windows PowerShell 5.1, Python 3.12.10 |
| Docker CPU / memory available | 22 logical CPUs / 9.713 GiB. Same as A1 | not applicable |
| Power | Mixed, as in A1: on battery for some runs and plugged in for others. Power mode: Best Power Efficiency | Mixed, as in A1: on battery for some runs and plugged in for others. Power mode: Best Power Efficiency |

Sources: the A1 record (`docs/test_environment.md`) for the machines, operating systems, Docker Desktop and Compose versions, and power. The residency check (`results/a2/residency/20261117-180010_llama3.2-1b__gemma3-4b/environment.json`) for the service host's Docker Engine version, Docker CPU and memory, and Ollama version and settings; these match A1. Load-generator software versions were read on that laptop.

**Service host kept idle.** To keep conditions steady across runs, **nothing else runs on the service host during calibration or a speed run**: no other programs, tests or downloads.

## 2. Container resources

| Item | Value | Same as A1? |
|---|---|---|
| CPUs available to Docker | 22 | yes |
| Memory available to Docker | 9.713 GiB | yes |
| Ollama container CPU limit | none (`NanoCpus` = 0): it can use all 22 | yes |
| Ollama container memory limit | none (0): it can use the 9.713 GiB | yes |
| GPU | none. No GPU settings in `docker-compose.yml`, and `ollama ps` shows `100% CPU` | yes |
| Memory with both cascade models loaded | Ollama container 5.14 GiB of 9.713 GiB (`docker_stats_end.txt`, residency check) | new in A2 |

## 3. Models

These tags and digests are the ones the A1 candidates used (`docs/candidate_models.md`). The service-host digests were read by the residency checks.

A digest is the SHA-256 fingerprint of a model's files, as shown by `ollama list`. It is the same on every machine that pulls the same model version from the public Ollama library, so it shows the models have not changed since A1. It contains nothing about the machine or the team.

| Model | Tag | Digest (service host) | Matches A1? |
|---|---|---|---|
| Llama 3.2 1B | `llama3.2:1b` | `baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878` | yes |
| Gemma 3 4B (top model) | `gemma3:4b` | `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a` | yes |
| Mistral 7B Instruct | `mistral:7b-instruct` | `6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf` | yes |

The models come from the Docker volume `ict3113-a1-team15_ollama_models` used in A1. Nothing has been pulled again.

**Ollama version note.** `docs/candidate_models.md` says the candidates were first pulled and checked with Ollama 0.40.0. The A1 benchmarks and all A2 tests use the pinned container image 0.35.0. The digests are identical, so the model files are the same.

## 4. Inference and service settings

These are held constant across all five configurations. The brief does not allow changing Ollama's inference settings between configurations.

| Setting | Value | Where it is set |
|---|---|---|
| Ollama version | 0.35.0 | `docker-compose.yml` (`OLLAMA_VERSION`) |
| Parallel requests | `OLLAMA_NUM_PARALLEL=1`: one inference at a time | `docker-compose.yml` |
| Queue limit | `OLLAMA_MAX_QUEUE=512` | `docker-compose.yml` |
| Thread count | Ollama default: not set | unchanged from A1 |
| Context length | `num_ctx` 4096, every model and every call | service `NUM_CTX` |
| Generation options | `temperature` 0, `num_predict` 16, `think` false for models that support it | `service/main.py`, `call_ollama` |
| Keep-alive | 30m: loaded models stay in memory between requests | service `KEEP_ALIVE` |
| Service timeout on Ollama | 300 s, then the service returns 502 | service `OLLAMA_TIMEOUT` |
| Classification prompt | unchanged from A1, the same for every model and both cascade stages | `service/main.py` |
| Result caching | none | `service/main.py` (covered by `tests/service`) |

The cascade adds `MODE`, `SMALL_MODEL`, `LARGE_MODEL`, `RULE` and `RULE_SETTING`. These are routing settings, not inference settings. Their values for each configuration are in `jmeter/a2_configs.json` and `docs/escalation_rule.md`.

## 5. Network

| Item | Value |
|---|---|
| Link | Tailscale, as in A1 |
| Path | Direct, not relayed: `tailscale ping <service-host-ip>` answered through the service host's own address and port, not "via DERP" (10 ms) |
| Protocol | Plain HTTP to the service host on port 8000 |
| Round-trip time | `ping -n 10 <service-host-ip>` at the practice run: 50 ms mean, 11–106 ms, 0% loss. Repeated pings sometimes lose 1 of 10. A1: 25 ms mean, 10–94 ms. This is about 1% of a 5 s request, and the per-run overhead below shows its effect directly. Re-checked before calibration |
| Network overhead per request | Reported per run as `median_outside_service_ms` in `results/a2/summary/a2_speed_runs.csv`: JMeter's elapsed time minus the service's logged latency |
| Load generator Tailscale version | 1.104.1 |

Calibration and every speed run must use the same network path. If it changes, record the change in section 6.

## 6. Changes from A1

| Change | Reason | Effect on comparability |
|---|---|---|
| `POST /tickets` can run a cascade; `GET /health` added | Required by the A2 brief | The single-model path and its responses are unchanged (`tests/service`) |
| Two models may be loaded at once | Cascade residency | Checked: both pairs stay resident (`results/a2/residency/`) |
| JMeter plan is `a2_triage_load.jmx`: `POST /tickets` only, the feeder never wraps, timeout and drain from S | A2 test method (brief, Step 4) | A2 speed figures are not comparable with A1 load figures, which were measured at different rates and also included `GET /search` |
| Ollama is restarted before every run, and 3 fixed warm-ups are sent | A2 test method | Clears Ollama's prompt cache. A1 used one warm-up and no restart |
| Service host kept idle during calibration and runs | Keeps conditions steady across runs | Reduces spread across runs. Power stays mixed, as in A1 |

## 7. Pre-run checks

Do this check before calibration and again before the first run of each configuration. Every speed run's `.meta.json` also keeps `/health` before and after the run, `/stats` before and after, and the SHA-256 hashes of the workload files.

**Service host:**
```
docker version --format "{{.Server.Version}}"
docker compose version
docker info --format "CPUs={{.NCPU}} Mem={{.MemTotal}}"
docker compose exec ollama ollama --version
docker compose exec ollama ollama list
docker compose exec ollama env | findstr OLLAMA_
```
**Load generator:**
```
& "$env:JMETER_HOME\bin\jmeter.bat" --version
ping -n 10 <service-host-ip>
Invoke-RestMethod http://<service-host-ip>:8000/health
```

| Before | Digests same | Versions and settings same | Nothing else running on the service host | Notes |
|---|---|---|---|---|
| practice run (not a benchmark) | yes: `baf6a787fdff`, `a2af6cc3eb7f`, `6577803aa9a0` | yes: Engine 28.5.1, Compose 2.40.0, 22 CPUs, 10429063168 bytes (9.713 GiB), Ollama 0.35.0, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_QUEUE=512`. JMeter 5.6.3 | yes | Cascade with a placeholder rule setting, 2 arrivals: 2 sent, 2 completed, 2 stored by the service. Its log was deleted |
| calibration | **`TODO`** | | | |
| `gemma3-4b` | | | | |
| `cascade_s1` | | | | |
| `cascade_s2` | | | | |
| other qualifying singles | | | | |

Freeze before the first benchmark run:
- Escalation rule and prediction record: frozen in `docs/escalation_rule.md` and `predictions/a2_prediction_record.md`. Cascade settings: `RULE=length`, S1 `RULE_SETTING=241`, S2 `RULE_SETTING=289`, also in `jmeter/a2_configs.json`.
- Workload list: the workload files are private; their SHA-256 hashes are checked by the runner and kept in every run's `.meta.json`.
