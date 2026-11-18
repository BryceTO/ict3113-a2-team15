# A2 Speed-Test Playbook

Owner: Performance Testing Lead. This covers calibration and the speed runs (brief, Step 4). The accuracy test is the Model & Accuracy Lead's procedure and runs **first**.

## 1. Gate: do not start official runs until all are true

- `docs/escalation_rule.md`, `predictions/a2_prediction_record.md` and `jmeter/a2_workload_rows.csv` are committed. Record the commit hash here: `________`.
- The Model & Accuracy Lead has published the accuracy results and the speed-eligibility list (which singles pass both floors).
- The cascade `rule` and `rule_setting` for `cascade_s1` and `cascade_s2` are filled in `jmeter/a2_configs.json` from the frozen rule.
- `docs/a2_test_environment.md` records versions, digests, CPU/RAM limits and Ollama settings. Re-check them before each configuration.
- Nothing else runs on the service host during a run.

## 2. Machines

| Role | Machine | Runs |
|---|---|---|
| Service host | The A1 service host laptop | Docker: triage service + Ollama 0.35.0, CPU only |
| Load generator | The A1 JMeter laptop | JMeter 5.6.3, these scripts |

Same machines, CPU and RAM allocation as A1 (`docs/test_environment.md`).

## 3. One-time setup on the load generator

1. Put the private workload files from the Workload & Requirements Lead in `context/a2_workload/`. This folder is git-ignored, so never commit them. The files are `measured_feeder.tsv`, `warmup_requests.tsv`, `calibration_requests.tsv` and `SHA256SUMS.txt`. The scripts check the hashes on every run.
2. Set JMeter: `$env:JMETER_HOME = "<folder>\apache-jmeter-5.6.3"`
3. Check that the service is reachable: `Invoke-RestMethod http://<service-host-ip>:8000/health`

## 4. Calibration: once, after the accuracy tests

**Service host:**
```
$env:MODE="single"; $env:MODEL="gemma3:4b"; $env:RUN_ID="a2_gemma3-4b_calibration"; docker compose up -d; docker compose restart ollama
```
**Load generator:**
```
powershell -ExecutionPolicy Bypass -File scripts\a2_calibrate.ps1 -TargetHost <service-host-ip>
```
The script:
1. Checks that the service is in single mode on `gemma3:4b` with no model loaded yet (Ollama was just restarted).
2. Sends warm-ups 15520, 15675 and 15859 one at a time.
3. Times calibration rows 15363, 15464 and 15871 one at a time, using the client-side clock (the same clock as JMeter's `elapsed`).
4. Takes **S** as the middle of the three times, rounded to 0.1 s.
5. Saves `results/a2/calibration/a2_calibration.json`.

Commit that file together with `results/logs/a2_gemma3-4b_calibration.log`. Then send the Workload & Requirements Lead the three row IDs, the three timings, S, the interval, the rate and the window.

| Setting | Rule | Source |
|---|---|---|
| Arrival interval | 2 × S s | brief |
| Rate | 30 / S per min | brief |
| Arrival window | max(S, 5) min | brief |
| Response timeout | max(10 × S, 300) s | brief |
| Drain pause | timeout + 60 s | brief: longer than the timeout by at least 1 min |
| Seed | run number | run r1 has the same arrival times in every configuration |

**Arrival count.** JMeter's Open Model Thread Group sends exactly floor(rate × window) tickets at random times. This was checked on all 19 A1 runs and in a separate JMeter test. With S ≥ 5 that is 30 tickets per run. With S < 5 it is more (S = 4 gives 37), and the runner refuses to start if the feeder is shorter than that. The rate is rounded up at the 6th decimal, because 4.8387/min would give 29 instead of 30. The feeder never wraps: `recycle=false`, `stopThread=true`.

## 5. One run

Run IDs follow the pattern `a2_<config>_speed_r<N>`, with configs `gemma3-4b`, `llama3.2-1b`, `mistral-7b-instruct`, `cascade_s1` and `cascade_s2`. Use `-ShowRunId` to print one.

1. **Service host:** start the service for this run and restart Ollama. The runner prints the exact line if the service does not match, for example:
   ```
   $env:MODE="single"; $env:MODEL="gemma3:4b"; $env:RUN_ID="a2_gemma3-4b_speed_r1"; docker compose up -d; docker compose restart ollama
   ```
2. **Load generator:**
   ```
   powershell -ExecutionPolicy Bypass -File jmeter\a2_run_load.ps1 -TargetHost <service-host-ip> -Config gemma3-4b -Run 1
   ```
   The runner stops before sending any load unless:
   - `/health` matches the config (mode, models, cascade rule and setting) and no model is loaded yet;
   - `/stats` is empty, which shows the service is on a fresh run ID.

   It then sends the 3 warm-ups and discards their timings. Next it requires **every configured model to be loaded**. For a cascade whose warm-ups did not escalate, it prints a command for the service host. That command loads the large model without classifying anything, using the service's `num_ctx` and `keep_alive`, so the model is not reloaded mid-run. After that the runner records `/stats`, runs JMeter, and records `/stats` and `/health` again.
3. **Cascade only, service host:** save the output of `docker compose exec ollama ollama ps` once the runner says "Resident". Store it in `results/a2/residency/` under the run ID.
4. Do not touch either machine until the runner prints `Finished`.
5. **Service host:** commit and push `results/logs/<RUN_ID>.log`.
6. **Load generator:** pull, then run `py scripts\summarize_a2_load.py`. Commit the `results/a2/jtl/<RUN_ID>.jtl`, `.properties` and `.meta.json` files together with `results/a2/summary/`.

A run that fails a check, or ends with `reconciled = no`, is kept on file. Note the reason and repeat it under the next run number. A run with unfinished requests is **reported, not discarded**.

### Run matrix

Three repeats of each:
- `gemma3-4b` (the reference);
- every other single that passes both floors;
- `cascade_s1` and `cascade_s2`, even if they fail accuracy.

That is 9–15 runs. Each takes about the arrival window + drain + 3–5 min for the restart and warm-up. Run r1 of every configuration, then r2, then r3, so that drift over the day is spread evenly.

## 6. What the summary reports

`results/a2/summary/a2_speed_runs.csv` (one row per run) and `a2_speed_configs.csv` (one row per configuration). The definitions are in the header of `scripts/summarize_a2_load.py`. In short:

- **Counts:** planned, recorded, completed, errored, cut off, unfinished, and the requests the service stored (`/stats` delta). The `/stats` delta is shown separately from the client counts so that any mismatch is visible.
- **Latency:** nearest-rank p50 over **successful** requests for each run, with mean, sd and spread across the three runs. p95 is reported only pooled over the three runs, with its sample count. There is no p99.
- **Throughput and errors:** completed per second and error rate, for each run.
- **Backlog:** maximum backlog, backlog at the end of the arrival window, and first-half versus second-half p50. A per-minute timeline is in `timeline/<RUN_ID>.csv`.
- **Cascade:** escalated / `routing == "decided"` from the service log, plus mean small-model and large-model time, and p50 for accepted versus escalated tickets.
- **Reconciliation:** every JTL sample is matched to a service-log line by request ID, or by `row_id` for requests JMeter cut off. Status codes and run ID must agree.

## 7. Plumbing tests

To test the scripts without a real run, use `-S <seconds>`, `-Schedule "<schedule>"` and `-OutDir <scratch folder>`. Runs made this way are flagged `plumbing test (not official)`. Never put them in `results/a2/jtl/`.
