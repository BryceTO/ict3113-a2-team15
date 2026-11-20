"""Summarise the A2 speed-test runs and reconcile each one with its service log.

For every results/a2/jtl/<RUN_ID>.jtl it reads <RUN_ID>.meta.json (written by jmeter/a2_run_load.ps1)
and results/logs/<RUN_ID>.log (written by the service), then writes to results/a2/summary/:

    a2_speed_runs.csv          one row per run: request accounting, latency, throughput, errors,
                               backlog, reconciliation, and (cascade) escalation from the log
    a2_speed_configs.csv       one row per configuration: p50 per run with mean and spread,
                               pooled p95 with its sample count, throughput/error, escalation
    timeline/<RUN_ID>.csv      per-minute arrivals, completions, backlog and latency

Definitions (brief, Step 4 "Report, per run"); quote them wherever the numbers are used:
- Latency is JMeter's `elapsed` (ms) of SUCCESSFUL POST /tickets samples only.
- Percentiles are nearest-rank (value at position ceil(p/100 * n) in the sorted list), so every
  percentile is a latency a real request had. p50 is per run; p95 is only reported pooled over all
  runs of a configuration, with its sample count. No p99 (sample too small).
- planned     = arrivals the schedule sends: floor(rate x window), from the .meta.json.
- recorded    = POST /tickets samples in the .jtl.
- cut_off     = recorded samples JMeter killed when the schedule ended (no HTTP code,
                "Socket closed"): from the client's view the request never finished.
- completed   = success=true.  errored = recorded - completed - cut_off (HTTP errors, client timeouts).
- unfinished  = (planned - recorded) + cut_off: arrivals with no finished outcome. Runs with
                unfinished requests are kept and flagged, never dropped. Cut-off samples carry no
                request ID, so they are matched to the service log by row_id.
- stored      = increase in the GET /stats total across the run (from the .meta.json); the
                service's own count of completed, stored tickets, shown next to the client counts.
- Throughput  = completed / test time, test time = arrival window or JMeter start to last
                response, whichever is longer. Reported per second (brief) and per minute.
- Error rate  = errored / recorded. Cut-off requests count as unfinished, not as errors.
- Backlog     = requests that had arrived but not finished at an instant (from .jtl start/end).
- Escalation fraction (cascade) = escalated / tickets with routing == "decided", from the service
  log lines of this run's measured requests (warm-ups excluded).
"""
import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

LABEL = "POST /tickets"
RELOAD_NS = 1e9  # a load_duration above 1 s means the model was (re)loaded during the request


def nearest_rank(values, pct):
    ordered = sorted(values)
    if not ordered:
        return ""
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def read_jtl(path):
    samples = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["label"] != LABEL:
                continue
            start, elapsed = int(row["timeStamp"]), int(row["elapsed"])
            samples.append(
                {
                    "start": start,
                    "end": start + elapsed,
                    "elapsed": elapsed,
                    "code": row["responseCode"],
                    "ok": row["success"].strip().lower() == "true",
                    "row_id": row.get("row_id", ""),
                    "request_id": row.get("request_id", "NA"),
                    "failure": (row.get("failureMessage") or "") + " " + (row.get("responseMessage") or ""),
                }
            )
    return samples


def is_cut_off(s):
    """JMeter interrupts requests still running when the schedule ends: no HTTP code, 'Socket closed'."""
    return not s["ok"] and not s["code"].isdigit() and "socket closed" in (s["code"] + " " + s["failure"]).lower()


def read_log(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def timeline(samples, start_ms):
    rows = []
    if not samples:
        return rows
    last = max(s["end"] for s in samples)
    for minute in range(math.ceil((last - start_ms) / 60000)):
        lo, hi = start_ms + minute * 60000, start_ms + (minute + 1) * 60000
        arrived = [s for s in samples if lo <= s["start"] < hi]
        done = [s for s in samples if lo <= s["end"] < hi]
        rows.append(
            {
                "minute": minute + 1,
                "arrivals": len(arrived),
                "completions": len(done),
                "errors": sum(not s["ok"] for s in done),
                "backlog_at_end": sum(s["start"] < hi <= s["end"] for s in samples),
                "p50_ms_of_arrivals": nearest_rank([s["elapsed"] for s in arrived], 50),
                "max_ms_of_arrivals": max((s["elapsed"] for s in arrived), default=""),
            }
        )
    return rows


def backlog_at(samples, t):
    return sum(s["start"] <= t < s["end"] for s in samples)


def summarise_run(jtl_path, log_dir, out_dir):
    run_id = jtl_path.stem
    meta_path = jtl_path.with_name(run_id + ".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig")) if meta_path.exists() else {}
    settings = meta.get("settings", {})
    samples = read_jtl(jtl_path)
    # schedule start (from JMeter's own log, recorded by the runner); the JVM launch time is a fallback only
    start_ms = meta.get("schedule_started_ms") or meta.get("jmeter_started_ms") or (min(s["start"] for s in samples) if samples else 0)
    window_s = settings.get("arrival_window_s", 0)
    planned = settings.get("planned_arrivals")

    ok = [s for s in samples if s["ok"]]
    cut = [s for s in samples if is_cut_off(s)]
    elapsed_ok = [s["elapsed"] for s in ok]
    last_end = max((s["end"] for s in samples), default=start_ms)
    test_time_s = max(window_s, (last_end - start_ms) / 1000) or 1
    flags = []
    if not meta:
        flags.append("no meta.json")
    if meta and (not meta.get("restart_check", True) or "manual" in str(meta.get("s_source", "")) or "overridden" in str(meta.get("s_source", ""))):
        flags.append("plumbing test (not official)")

    row = {
        "run_id": run_id,
        "config": meta.get("config", run_id.rsplit("_speed_", 1)[0].removeprefix("a2_")),
        "run": meta.get("run", ""),
        "mode": meta.get("mode", ""),
        "s_seconds": settings.get("s_seconds", ""),
        "rate_per_min": settings.get("rate_per_min", ""),
        "window_s": window_s,
        "seed": meta.get("seed", ""),
        "planned": planned if planned is not None else "",
        "recorded": len(samples),
        "completed": len(ok),
        "errored": len(samples) - len(ok) - len(cut),
        "client_side_errors": sum(not s["code"].isdigit() and not is_cut_off(s) for s in samples),
        "cut_off": len(cut),
        "not_sent": max(0, planned - len(samples)) if planned is not None else "",
        "unfinished": (max(0, planned - len(samples)) if planned is not None else 0) + len(cut),
        "stored_during_run": meta.get("stored_during_run", ""),
        "error_rate_pct": round(100 * (len(samples) - len(ok) - len(cut)) / len(samples), 2) if samples else "",
        "n_success": len(elapsed_ok),
        "p50_ms": nearest_rank(elapsed_ok, 50),
        "mean_ms": round(statistics.fmean(elapsed_ok), 1) if elapsed_ok else "",
        "min_ms": min(elapsed_ok, default=""),
        "max_ms": max(elapsed_ok, default=""),
        "test_time_s": round(test_time_s, 1),
        "throughput_per_s": round(len(ok) / test_time_s, 4),
        "throughput_per_min": round(60 * len(ok) / test_time_s, 3),
    }
    if row["unfinished"]:
        flags.append(f"{row['unfinished']} unfinished")

    # backlog: does the queue grow during the run?
    arrivals = sorted(samples, key=lambda s: s["start"])
    half = len(arrivals) // 2
    first = [s["elapsed"] for s in arrivals[:half] if s["ok"]]
    second = [s["elapsed"] for s in arrivals[half:] if s["ok"]]
    tl = timeline(samples, start_ms)
    row.update(
        {
            "max_backlog": max((backlog_at(samples, s["start"]) for s in samples), default=0),
            "backlog_at_window_end": backlog_at(samples, start_ms + window_s * 1000) if window_s else "",
            "p50_first_half_ms": nearest_rank(first, 50),
            "p50_second_half_ms": nearest_rank(second, 50),
        }
    )
    if first and second and row["p50_second_half_ms"] > 1.5 * row["p50_first_half_ms"] and row["max_backlog"] > 2:
        flags.append("possible queue growth (2nd-half p50 > 1.5x 1st-half)")

    # reconcile with the service log
    log_path = log_dir / f"{run_id}.log"
    warm_ids = {w.get("request_id") for w in meta.get("warmup", []) if w.get("request_id")}
    if not log_path.exists():
        row["reconciled"] = "NO LOG"
        flags.append(f"{log_path.as_posix()} not found")
    else:
        entries = [e for e in read_log(log_path) if e.get("endpoint") == LABEL and e.get("request_id") not in warm_ids]
        by_id = {e["request_id"]: e for e in entries}
        notes = []
        if len(entries) != len(samples):
            notes.append(f"log has {len(entries)} measured requests, jtl has {len(samples)}")
        # match by request ID; samples without one (cut off, no response headers) by row_id
        matched, by_row_matches, used = [], [], set()
        for s in samples:
            if s["request_id"] in by_id:
                matched.append((s, by_id[s["request_id"]]))
                used.add(s["request_id"])
        for s in samples:
            if s["request_id"] in by_id:
                continue
            cand = [e for e in entries if e["request_id"] not in used and str(e.get("row_id")) == s["row_id"]]
            if cand:
                by_row_matches.append((s, cand[0]))
                used.add(cand[0]["request_id"])
        missing = len(samples) - len(matched) - len(by_row_matches)
        if missing:
            notes.append(f"{missing} jtl samples not in the log")
        service_only = [e for e in entries if e["request_id"] not in used]
        if service_only:
            notes.append(f"{len(service_only)} log requests not in the jtl")
        wrong_run = sum(e.get("run_id") != run_id for e in entries)
        if wrong_run:
            notes.append(f"{wrong_run} log lines carry another run_id")
        if sum(s["code"] != str(e.get("status")) for s, e in matched):
            notes.append("status codes differ")
        row["matched_by_row_id"] = len(by_row_matches)
        row["cut_off_but_stored_by_service"] = sum(is_cut_off(s) and e.get("status") == 200 for s, e in by_row_matches)
        log_ok = sum(e.get("status") == 200 for e in entries)
        if row["stored_during_run"] != "" and row["stored_during_run"] != log_ok:
            notes.append(f"/stats grew by {row['stored_during_run']} but the log has {log_ok} successful requests")
        if not warm_ids and meta:
            notes.append("no warm-up request IDs in meta")
        row["reconciled"] = "no" if notes else "yes"
        row["reconcile_notes"] = "; ".join(notes)
        row["log_requests"] = len(entries)
        row["log_ok"] = log_ok
        row["service_only_requests"] = len(service_only)
        if matched:
            row["median_outside_service_ms"] = round(statistics.median(s["elapsed"] - e.get("latency_ms", 0) for s, e in matched), 1)
        row["mean_service_latency_ms"] = round(statistics.fmean(e["latency_ms"] for e in entries), 1) if entries else ""
        ollama = [e["ollama_ms"] for e in entries if e.get("ollama_ms") is not None]
        row["mean_ollama_ms"] = round(statistics.fmean(ollama), 1) if ollama else ""
        row["model_reloads"] = sum(
            any((e.get(k) or 0) > RELOAD_NS for k in ("ollama_load_ns", "small_load_ns", "large_load_ns")) for e in entries
        )
        if row["model_reloads"]:
            flags.append(f"{row['model_reloads']} requests paid a model load")
        row["unclassified"] = sum(e.get("category") == "Unclassified" for e in entries)
        row["final_models"] = "|".join(f"{m}={n}" for m, n in sorted(_count(e.get("final_model") for e in entries).items()))

        if meta.get("mode") == "cascade" or any(e.get("mode") == "cascade" for e in entries):
            decided = [e for e in entries if e.get("routing") == "decided"]
            escalated = [e for e in decided if e.get("escalated")]
            accepted = [e for e in decided if not e.get("escalated")]
            row["routing_decided"] = len(decided)
            row["routing_not_reached"] = sum(e.get("routing") == "not_reached" for e in entries)
            row["escalated"] = len(escalated)
            row["escalation_fraction"] = round(len(escalated) / len(decided), 4) if decided else ""
            small = [e["small_ms"] for e in entries if e.get("small_ms") is not None]
            large = [e["large_ms"] for e in escalated if e.get("large_ms") is not None]
            row["mean_small_ms"] = round(statistics.fmean(small), 1) if small else ""
            row["mean_large_ms"] = round(statistics.fmean(large), 1) if large else ""
            el = {s["request_id"]: s["elapsed"] for s in ok}
            row["p50_accepted_ms"] = nearest_rank([el[e["request_id"]] for e in accepted if e["request_id"] in el], 50)
            row["p50_escalated_ms"] = nearest_rank([el[e["request_id"]] for e in escalated if e["request_id"] in el], 50)
    row["flags"] = "; ".join(flags)

    write_csv(out_dir / "timeline" / f"{run_id}.csv", tl)
    return row, elapsed_ok


def _count(values):
    out = defaultdict(int)
    for v in values:
        out[v or "none"] += 1
    return out


def summarise_configs(runs, pooled):
    out = []
    by_config = defaultdict(list)
    for r in runs:
        by_config[r["config"]].append(r)
    for config, rows in sorted(by_config.items()):
        rows.sort(key=lambda r: (str(r["run"]), r["run_id"]))
        p50s = [r["p50_ms"] for r in rows if r["p50_ms"] != ""]
        all_ok = [v for r in rows for v in pooled[r["run_id"]]]
        c = {
            "config": config,
            "runs": len(rows),
            "run_ids": "|".join(r["run_id"] for r in rows),
            "all_reconciled": all(r.get("reconciled") == "yes" for r in rows),
            "flags": " / ".join(f"{r['run_id']}: {r['flags']}" for r in rows if r["flags"]),
            "p50_per_run_ms": "|".join(str(v) for v in p50s),
            "p50_mean_ms": round(statistics.fmean(p50s), 1) if p50s else "",
            "p50_sd_ms": round(statistics.stdev(p50s), 1) if len(p50s) > 1 else "",
            "p50_min_ms": min(p50s, default=""),
            "p50_max_ms": max(p50s, default=""),
            "p50_spread_ms": (max(p50s) - min(p50s)) if p50s else "",
            "pooled_p95_ms": nearest_rank(all_ok, 95),
            "pooled_n": len(all_ok),
            "planned_total": sum(r["planned"] or 0 for r in rows),
            "completed_total": sum(r["completed"] for r in rows),
            "errored_total": sum(r["errored"] for r in rows),
            "unfinished_total": sum(r["unfinished"] or 0 for r in rows),
            "throughput_per_s_per_run": "|".join(str(r["throughput_per_s"]) for r in rows),
            "throughput_per_s_mean": round(statistics.fmean(r["throughput_per_s"] for r in rows), 4),
            "error_rate_pct_per_run": "|".join(str(r["error_rate_pct"]) for r in rows),
        }
        if any("escalated" in r for r in rows):
            decided = sum(r.get("routing_decided", 0) for r in rows)
            esc = sum(r.get("escalated", 0) for r in rows)
            c["escalation_fraction_per_run"] = "|".join(str(r.get("escalation_fraction", "")) for r in rows)
            c["escalated_total"] = esc
            c["routing_decided_total"] = decided
            c["escalation_fraction_pooled"] = round(esc / decided, 4) if decided else ""
        out.append(c)
    return out


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r)) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Summarise A2 speed-test runs and reconcile them with service logs.")
    parser.add_argument("--jtl-dir", default="results/a2/jtl")
    parser.add_argument("--log-dir", default="results/logs")
    parser.add_argument("--out-dir", default="results/a2/summary")
    args = parser.parse_args()
    jtl_dir, log_dir, out_dir = Path(args.jtl_dir), Path(args.log_dir), Path(args.out_dir)

    runs, pooled = [], {}
    for jtl in sorted(jtl_dir.glob("*.jtl")):
        row, ok_elapsed = summarise_run(jtl, log_dir, out_dir)
        runs.append(row)
        pooled[row["run_id"]] = ok_elapsed
    if not runs:
        raise SystemExit(f"no .jtl files in {jtl_dir}")
    configs = summarise_configs(runs, pooled)
    write_csv(out_dir / "a2_speed_runs.csv", runs)
    write_csv(out_dir / "a2_speed_configs.csv", configs)

    print("| run | planned | recorded | ok | err | cut off | unfinished | stored | p50 ms | ok/s | max backlog | esc | reconciled |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in runs:
        rec = r.get("reconciled", "") + (f" ({r['reconcile_notes']})" if r.get("reconcile_notes") else "")
        print(f"| {r['run_id']} | {r['planned']} | {r['recorded']} | {r['completed']} | {r['errored']} | {r['cut_off']} | {r['unfinished']} | "
              f"{r['stored_during_run']} | {r['p50_ms']} | {r['throughput_per_s']} | {r['max_backlog']} | "
              f"{r.get('escalation_fraction', '')} | {rec} |")
        if r["flags"]:
            print(f"    flags: {r['flags']}")
    print()
    print("| config | runs | p50 per run | p50 mean | p50 sd | pooled p95 (n) | esc pooled |")
    print("|---|---:|---|---:|---:|---|---:|")
    for c in configs:
        print(f"| {c['config']} | {c['runs']} | {c['p50_per_run_ms']} | {c['p50_mean_ms']} | {c['p50_sd_ms']} | "
              f"{c['pooled_p95_ms']} ({c['pooled_n']}) | {c.get('escalation_fraction_pooled', '')} |")
        if c["runs"] != 3:
            print(f"    WARNING: {c['config']} has {c['runs']} run(s); the brief requires 3.")
    print(f"\nwrote {out_dir.as_posix()}")


if __name__ == "__main__":
    main()
