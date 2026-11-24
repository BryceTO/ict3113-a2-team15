"""Audit the saved Team 15 A2 evidence without calling the service."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import re
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def require(condition, message):
    if not condition:
        raise ValueError(message)


def evidence_path(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root), f"Evidence path is outside the repository: {relative}")
    require(path.is_file(), f"Missing evidence: {relative}")
    return path


def check_hash(runner, path, expected):
    require(runner.sha(path) == expected.lower(), f"SHA-256 differs: {path.name}")


def compare_rows(runner, path, derived):
    expected = [{key: "" if value is None else str(value) for key, value in row.items()}
                for row in derived]
    saved = runner.read_csv(path)
    require(len(saved) == len(expected), f"{path.name}: row count differs")
    for number, (actual, row) in enumerate(zip(saved, expected), 2):
        for key in actual.keys() | row.keys():
            # Some speed fields only apply to cascades, leaving blank cells for singles.
            require(actual.get(key, "") == row.get(key, ""),
                    f"{path.name}:{number}: {key} differs from derived evidence")


def check_split(root, runner):
    def indexed(path):
        rows = runner.read_csv(path)
        indexed_rows = {int(row["ROW"]): row for row in rows}
        require(len(rows) == len(indexed_rows), f"{path.name}: duplicate row IDs")
        return indexed_rows

    golden = indexed(root / "golden_set/golden_set.csv")
    odd = indexed(root / "golden_set/a2/tuning (odd).csv")
    even = indexed(root / "golden_set/a2/test (even).csv")
    require((len(golden), len(odd), len(even)) == (175, 87, 88), "Unexpected split sizes")
    require(set(odd) == {row for row in golden if row % 2}, "Odd split membership differs")
    require(set(even) == {row for row in golden if not row % 2}, "Even split membership differs")
    require(list(odd) == sorted(odd) and list(even) == sorted(even), "Split IDs are not sorted")
    for row_id, split_row in (odd | even).items():
        original = golden[row_id]
        require(split_row["GOLDEN_LABEL"] == original["GOLDEN_LABEL"],
                f"Golden label differs for row {row_id}")
        require(split_row["NARRATIVE"].replace("\r\n", "\n") ==
                original["NARRATIVE"].replace("\r\n", "\n"),
                f"Narrative differs for row {row_id}")
    return set(golden), runner.load_test(root / "golden_set/a2/test (even).csv")


def check_accuracy(root, runner, scorer, tickets, warnings):
    accuracy_dir = root / "results/a2/accuracy"
    summary = accuracy_dir / "summary_reviewed_r1"
    provenance = runner.read_json(summary / "provenance.json")
    require(provenance["test_sha256"] == runner.FROZEN_HASH, "Accuracy split fingerprint differs")
    check_hash(runner, Path(scorer.__file__), provenance["scorer_sha256"])
    for name, digest in runner.read_json(summary / "complete.json")["files"].items():
        check_hash(runner, evidence_path(root, summary.relative_to(root) / name), digest)

    runs, logs, ids, finishes = {}, {}, set(), {}
    for entry in provenance["runs"]:
        folder = evidence_path(root, Path(entry["path"]) / "manifest.json").parent
        check_hash(runner, folder / "manifest.json", entry["manifest_sha256"])
        check_hash(runner, folder / "predictions.csv", entry["predictions_sha256"])
        manifest, predictions = scorer.load_run(folder, tickets)
        config, run_id = manifest["config"], manifest["run_id"]
        require(config not in runs, f"Multiple primary runs for {config}")
        require(folder.name == run_id and run_id not in ids, f"Invalid accuracy run ID: {run_id}")
        log = evidence_path(root, provenance["logs"][config]["path"])
        require(log.stem == run_id, f"Accuracy log filename differs for {config}")
        check_hash(runner, log, provenance["logs"][config]["sha256"])
        check_hash(runner, summary / f"{config}.service.jsonl", runner.sha(log))
        runs[config], logs[config] = predictions, log
        ids.add(run_id)

    tables = scorer.score_runs(runs, logs, tickets, provenance["service_run_ids"])
    for name, derived in tables.items():
        compare_rows(runner, summary / name, derived)
    reconciliation = tables["service_reconciliation.csv"]
    require(len(reconciliation) == sum(map(len, runs.values()))
            and all(row["evidence_status"] == "matched" for row in reconciliation),
            "Primary accuracy requests do not all reconcile")

    for folder in sorted(accuracy_dir.glob("a2_*_accuracy_*")):
        manifest, predictions = scorer.load_run(folder, tickets)
        run_id = manifest["run_id"]
        require(folder.name == run_id, f"Accuracy run ID and directory differ: {folder.name}")
        check_hash(runner, Path(runner.__file__), manifest["runner_sha256"])
        completion = runner.read_json(folder / "complete.json")
        finishes[run_id] = datetime.fromisoformat(completion["completed_at"])
        check_hash(runner, folder / "health_after.json", completion["health_after_sha256"])
        health = runner.read_json(folder / "health_after.json")
        for issue in runner.health_issues(health, manifest["expected_config"]):
            warnings.append(f"{run_id}: {issue} after run ({completion['failures']} failed requests).")
        if run_id not in ids:
            log = evidence_path(root, f"results/logs/{run_id}.log")
            decisions = scorer.reconcile(predictions, log, tickets)
            require(len(decisions) == len(tickets) and
                    all(row["evidence_status"] == "matched" for row in decisions),
                    f"Diagnostic accuracy requests do not reconcile: {run_id}")
            print(f"Diagnostic accuracy (excluded from primary): {run_id}, "
                  f"{sum(row['correct'] for row in predictions)}/{len(tickets)} correct")

    require(ids <= finishes.keys(), "Primary accuracy run inventory is incomplete")
    print(f"Accuracy: {len(runs)} primary configurations, {len(reconciliation)} matched requests, "
          f"{len(finishes) - len(ids)} diagnostic run(s)")
    primary_finish = max(finishes[run_id] for run_id in ids)
    return tables, primary_finish


def check_speed(root, runner, speed, rates, golden_ids, required_configs, accuracy_finish, warnings):
    calibration_path = root / "results/a2/calibration/a2_calibration.json"
    jtl_dir = root / "results/a2/jtl"
    log_dir = root / "results/logs"
    summary = root / "results/a2/summary"
    workload_path = root / "jmeter/a2_workload_rows.csv"
    workload = runner.read_csv(workload_path)
    workload_ids = [int(row["row_id"]) for row in workload]
    require(len(workload_ids) == len(set(workload_ids)), "Workload row IDs are duplicated")
    require(not golden_ids.intersection(workload_ids), "Workload overlaps the golden set")
    by_purpose = {}
    for purpose, count in (("warmup", 3), ("calibration", 3), ("measured", 60)):
        rows = sorted((row for row in workload if row["purpose"] == purpose),
                      key=lambda row: int(row["order"]))
        require([int(row["order"]) for row in rows] == list(range(1, count + 1)),
                f"Workload {purpose} order or count differs")
        by_purpose[purpose] = [int(row["row_id"]) for row in rows]
    require(len(workload) == 66, "Unexpected workload rows")

    calibration = runner.read_json(calibration_path)
    expected_settings = calibration["settings"]
    require(calibration["calibration_ms"] == [row["elapsed_ms"] for row in calibration["calibration"]],
            "Calibration timing list differs from the recorded requests")
    s = expected_settings["s_seconds"]
    require(s == round(calibration["middle_ms"] / 1000, 1)
            and expected_settings["arrival_window_s"] == 60 * max(s, 5)
            and expected_settings["response_timeout_s"] == max(10 * s, 300)
            and expected_settings["drain_pause_s"] >= expected_settings["response_timeout_s"] + 60,
            "Calibration window, timeout or drain differs from the assignment method")
    cal_id = "a2_gemma3-4b_calibration"
    cal_log = evidence_path(root, f"results/logs/{cal_id}.log")
    cal_requests = {row["request_id"]: row for row in speed.read_log(cal_log)
                    if row.get("endpoint") == speed.LABEL and row.get("run_id") == cal_id}
    for purpose, key in (("warmup", "warmups"), ("calibration", "calibration")):
        require([row["row_id"] for row in calibration[key]] == by_purpose[purpose],
                f"Calibration {purpose} rows differ from frozen workload")
        for row in calibration[key]:
            logged = cal_requests[row["request_id"]]
            require((logged["row_id"], logged["status"], logged["model"]) ==
                    (row["row_id"], row["status"], "gemma3:4b"),
                    f"Calibration request differs: {row['row_id']}")
    # PowerShell emits seven fractional digits. Python 3.10 accepts up to six here.
    timestamp = re.sub(r"(\.\d{6})\d+(?=Z$)", r"\1", calibration["measured_at_utc"])
    calibrated_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if calibrated_at < accuracy_finish:
        warnings.append(
            f"Gemma calibration ({calibrated_at.isoformat()}) predates completion of "
            f"the last primary accuracy run ({accuracy_finish.isoformat()})."
        )

    paths = sorted(jtl_dir.glob("*.jtl"))
    runs, pooled = [], {}
    prefix = by_purpose["measured"][:expected_settings["planned_arrivals"]]
    workload_hash = calibration["workload_sha256"]["a2_workload_rows.csv"]
    # The row list is tracked as text and may acquire CRLF on Windows checkout.
    workload_lf = hashlib.sha256(workload_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    require(workload_hash in {runner.sha(workload_path), workload_lf}, "Frozen workload hash differs")
    with TemporaryDirectory(prefix="a2-evidence-") as temp:
        for jtl in paths:
            run_id = jtl.stem
            meta = runner.read_json(jtl.with_suffix(".meta.json"))
            properties = dict(line.split("=", 1) for line in
                              jtl.with_suffix(".properties").read_text(encoding="utf-8-sig").splitlines()
                              if "=" in line and not line.lstrip().startswith(("#", "!")))
            require(run_id == meta["run_id"] == f"a2_{meta['config']}_speed_r{meta['run']}",
                    f"{run_id}: metadata ID differs")
            require(meta["restart_check"] and meta["seed"] == meta["run"],
                    f"{run_id}: restart check or repeat seed differs")
            require(meta["settings"] == expected_settings, f"{run_id}: calibration settings differ")
            require(properties["seed"] == str(meta["seed"])
                    and properties["schedule"] == expected_settings["schedule"]
                    and int(properties["response_timeout_ms"]) == expected_settings["response_timeout_s"] * 1000,
                    f"{run_id}: JMeter properties differ from run metadata")
            require(meta["workload_sha256"] == calibration["workload_sha256"],
                    f"{run_id}: recorded workload hashes differ")
            expected = runner.expected_config(meta["config"])
            require(meta["mode"] == expected["mode"] and meta["models"] == expected["models"],
                    f"{run_id}: metadata models or mode differ from configuration")
            runner.validate_health(meta["health_before_run"], expected)
            require(meta["health_before_run"]["all_configured_loaded"] is True,
                    f"{run_id}: pre-run model residency is missing from health evidence")
            require([row["row_id"] for row in meta["warmup"]] == by_purpose["warmup"],
                    f"{run_id}: warm-up rows differ")
            try:
                runner.validate_health(meta["health_after_run"], expected)
            except (ValueError, KeyError, TypeError) as issue:
                warnings.append(f"{run_id}: {issue} after speed run.")
            before_total = sum(meta["stats_before"].values())
            after_total = sum(meta["stats_after"].values())
            require(before_total == meta["stats_before_total"]
                    and after_total == meta["stats_after_total"]
                    and after_total - before_total == meta["stored_during_run"],
                    f"{run_id}: stored-ticket count differs from stats snapshots")
            require(meta["feeder_rows_used"] == prefix, f"{run_id}: recorded workload prefix differs")
            started = datetime.fromtimestamp(meta["schedule_started_ms"] / 1000, timezone.utc)
            require(started >= accuracy_finish and started >= calibrated_at,
                    f"{run_id}: scored load predates accuracy completion or calibration")
            samples = sorted(speed.read_jtl(jtl), key=lambda row: row["start"])
            emitted = [int(row["row_id"]) for row in samples]
            require(len(emitted) == len(set(emitted)) and set(emitted) <= set(prefix),
                    f"{run_id}: duplicate or unexpected JTL row IDs")
            require(len(emitted) != len(prefix) or emitted == prefix,
                    f"{run_id}: JTL workload order differs")
            log = speed.read_log(log_dir / f"{run_id}.log")
            warm_ids = {row["request_id"] for row in meta["warmup"]}
            require(len(warm_ids) == 3, f"{run_id}: duplicate warm-up request IDs")
            requests = [row for row in log if row.get("endpoint") == speed.LABEL]
            requests_by_id = {row["request_id"]: row for row in requests}
            require(len(requests) == len(requests_by_id), f"{run_id}: duplicate log request IDs")
            for warmup in meta["warmup"]:
                logged_warmup = requests_by_id[warmup["request_id"]]
                require(warmup["status"] == 200 and
                        (logged_warmup["row_id"], logged_warmup["status"], logged_warmup["run_id"]) ==
                        (warmup["row_id"], 200, run_id),
                        f"{run_id}: warm-up metadata differs from service log")
            measured = [row for row in log if row.get("endpoint") == speed.LABEL
                        and row["request_id"] not in warm_ids]
            logged = {row["request_id"]: row for row in measured}
            require(len(logged) == len(measured), f"{run_id}: duplicate log request IDs")
            for entry in measured:
                require(entry["run_id"] == run_id and entry["mode"] == expected["mode"],
                        f"{run_id}: logged run or mode differs from configuration")
                if expected["mode"] == "single":
                    require(entry["model"] == expected["models"][0],
                            f"{run_id}: logged model differs from configuration")
                    final_model = expected["models"][0]
                else:
                    require([entry["small_model"], entry["large_model"]] == expected["models"]
                            and entry["rule"] == expected["rule"]
                            and str(entry["rule_setting"]) == str(expected["rule_setting"]),
                            f"{run_id}: logged cascade settings differ from configuration")
                    require(entry["routing"] in ("decided", "not_reached"),
                            f"{run_id}: invalid logged routing state")
                    if entry["routing"] == "decided":
                        escalated = entry["small_category"] == "Unclassified" or (
                            entry["narrative_chars"] > expected["rule_setting"])
                        require(type(entry["escalated"]) is bool and entry["escalated"] == escalated,
                                f"{run_id}: logged escalation differs from frozen rule")
                        final_model = expected["models"][int(escalated)]
                    else:
                        require(entry["status"] != 200,
                                f"{run_id}: successful cascade request has no routing decision")
                        final_model = None
                if entry["status"] == 200:
                    require(entry["final_model"] == final_model,
                            f"{run_id}: logged final model differs from routing outcome")
            for sample in samples:
                if sample["request_id"] in logged:
                    require(logged[sample["request_id"]]["row_id"] == int(sample["row_id"]),
                            f"{run_id}: JTL and service log row IDs differ for a matched request")
            row, elapsed = speed.summarise_run(jtl, log_dir, Path(temp))
            require(row["reconciled"] == "yes", f"{run_id}: {row['reconcile_notes']}")
            if row["flags"]:
                warnings.append(f"{run_id}: {row['flags']}.")
            runs.append(row)
            pooled[run_id] = elapsed
            compare_rows(runner, summary / "timeline" / f"{run_id}.csv",
                         runner.read_csv(Path(temp) / "timeline" / f"{run_id}.csv"))

    coverage = Counter((row["config"], row["run"]) for row in runs)
    require(all(coverage[config, repeat] == 1 for config in required_configs for repeat in (1, 2, 3)),
            "Missing or duplicated required speed run")
    compare_rows(runner, summary / "a2_speed_runs.csv", runs)
    configs = speed.summarise_configs(runs, pooled)
    compare_rows(runner, summary / "a2_speed_configs.csv", configs)
    comparison, _ = rates.build_comparison(
        calibration_path=calibration_path, runs_path=summary / "a2_speed_runs.csv",
        configs_path=summary / "a2_speed_configs.csv", workload_path=workload_path,
        jtl_dir=jtl_dir, logs_dir=log_dir, client_peak_per_hour=9,
    )
    compare_rows(runner, summary / "a2_rate_comparison.csv", comparison)
    print(f"Speed: {len(runs)} reconciled runs, {sum(row['recorded'] for row in runs)} JTL samples")
    return {row["config"]: row for row in configs}


def check_tradeoff(root, runner, accuracy, speed):
    summary = root / "results/a2/summary"
    chart = runner.read_csv(summary / "a2_tradeoff.csv")
    overall = {row["config"]: row for row in accuracy["overall.csv"]}
    eligibility = {row["config"]: row for row in accuracy["eligibility.csv"]}
    require(len(chart) == len(overall) and {row["config"] for row in chart} == overall.keys(),
            "Trade-off table configuration coverage differs")
    for row in chart:
        config = row["config"]
        acc, eligible = overall[config], eligibility[config]
        failed = sorted(r["category"] for r in accuracy["per_category.csv"]
                        if r["config"] == config and not r["passes"])
        expected = {
            "overall_correct": str(acc["correct"]), "overall_total": str(acc["total"]),
            "overall_accuracy_percent": f"{acc['accuracy_percent']:.6f}",
            "overall_floor_percent": f"{acc['floor_percent']:.6f}",
            "overall_pass": "yes" if acc["passes"] else "no",
            "category_fail_count": str(len(failed)), "category_failures": "|".join(failed),
            "all_categories_pass": "no" if failed else "yes",
            "accuracy_eligible": "yes" if eligible["accuracy_eligible"] else "no",
            "must_speed_test": "yes" if eligible["must_speed_test"] else "no",
            "speed_available": "yes" if config in speed else "no",
        }
        timing = speed.get(config, {})
        for output, field in (("p50_mean_seconds", "p50_mean_ms"), ("p50_sd_seconds", "p50_sd_ms"),
                              ("pooled_p95_seconds", "pooled_p95_ms")):
            expected[output] = f"{timing[field] / 1000:.3f}" if field in timing else ""
        expected["pooled_n"] = str(timing.get("pooled_n", ""))
        fraction = timing.get("escalation_fraction_pooled", "")
        expected["escalation_fraction_pooled"] = f"{fraction:.3f}" if fraction != "" else ""
        for field, value in expected.items():
            require(row[field] == value, f"Trade-off {config}: {field} differs from source summaries")

    handoff = (root / "docs/bryan_a2_final_handoff.md").read_text(encoding="utf-8-sig")
    match = re.search(r"`results/a2/summary/a2_tradeoff\.png`\s*\|\s*`([0-9a-fA-F]{64})`", handoff)
    require(match is not None, "Trade-off chart checksum is missing from the handoff")
    check_hash(runner, summary / "a2_tradeoff.png", match.group(1))
    print(f"Trade-off: {len(chart)} configuration rows agree with sources and the chart hash matches")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository containing the saved A2 evidence")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    sys.path.insert(0, str(root / "scripts"))
    warnings = []
    try:
        import compare_a2_rates as rates
        import run_a2_accuracy as runner
        import summarize_a2_accuracy as scorer
        import summarize_a2_load as speed

        golden_ids, tickets = check_split(root, runner)
        print(f"Split: {len(golden_ids) - len(tickets)} odd tuning / {len(tickets)} even test")
        accuracy, finished = check_accuracy(root, runner, scorer, tickets, warnings)
        required = {row["config"] for row in accuracy["eligibility.csv"] if row["must_speed_test"]}
        timing = check_speed(root, runner, speed, rates, golden_ids, required, finished, warnings)
        check_tradeoff(root, runner, accuracy, timing)
    except (ImportError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(f"Evidence checks passed with {len(warnings)} recorded warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
