import csv
import json
from pathlib import Path

import pytest

from scripts.compare_a2_rates import RateComparisonError, build_comparison, main


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_fixture(tmp_path: Path) -> dict[str, Path]:
    calibration = tmp_path / "calibration.json"
    runs = tmp_path / "runs.csv"
    configs = tmp_path / "configs.csv"
    workload = tmp_path / "workload.csv"
    jtl_dir = tmp_path / "jtl"
    logs_dir = tmp_path / "logs"
    output = tmp_path / "comparison.csv"
    jtl_dir.mkdir()
    logs_dir.mkdir()

    calibration.write_text(
        json.dumps(
            {
                "calibration_ms": [11506, 8506, 6183],
                "middle_ms": 8506,
                "settings": {
                    "s_seconds": 8.5,
                    "arrival_interval_s": 17,
                    "rate_per_min": 3.529412,
                    "rate_per_hour": 211.76,
                    "arrival_window_s": 510,
                    "response_timeout_s": 300,
                    "drain_pause_s": 360,
                    "planned_arrivals": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    write_csv(
        workload,
        ["purpose", "order", "row_id"],
        [
            {"purpose": "measured", "order": 1, "row_id": 15175},
            {"purpose": "measured", "order": 2, "row_id": 15176},
            {"purpose": "measured", "order": 3, "row_id": 15177},
        ],
    )

    run_rows: list[dict[str, object]] = []
    p50s = [6000, 7000, 8000]
    throughputs = [0.05, 0.052, 0.051]
    for run_number in range(1, 4):
        run_id = f"config_a_r{run_number}"
        run_rows.append(
            {
                "run_id": run_id,
                "config": "config_a",
                "run": run_number,
                "s_seconds": 8.5,
                "rate_per_min": 3.529412,
                "window_s": 510,
                "planned": 2,
                "recorded": 2,
                "completed": 2,
                "errored": 0,
                "unfinished": 0,
                "throughput_per_s": throughputs[run_number - 1],
                "p50_ms": p50s[run_number - 1],
                "max_backlog": run_number,
                "reconciled": "yes",
                "flags": "" if run_number != 2 else "possible queue growth",
            }
        )
        (jtl_dir / f"{run_id}.jtl").write_text("header\n", encoding="utf-8")
        (jtl_dir / f"{run_id}.properties").write_text("x=1\n", encoding="utf-8")
        (logs_dir / f"{run_id}.log").write_text("{}\n", encoding="utf-8")
        (jtl_dir / f"{run_id}.meta.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "config": "config_a",
                    "jmeter_exit_code": 0,
                    "feeder_rows_used": [15175, 15176],
                    "settings": {
                        "s_seconds": 8.5,
                        "rate_per_min": 3.529412,
                        "arrival_window_s": 510,
                        "planned_arrivals": 2,
                    },
                }
            ),
            encoding="utf-8",
        )

    write_csv(runs, list(run_rows[0]), run_rows)
    write_csv(
        configs,
        [
            "config",
            "runs",
            "run_ids",
            "all_reconciled",
            "p50_mean_ms",
            "p50_sd_ms",
            "pooled_p95_ms",
            "pooled_n",
            "planned_total",
            "completed_total",
            "errored_total",
            "unfinished_total",
            "throughput_per_s_mean",
            "escalation_fraction_pooled",
        ],
        [
            {
                "config": "config_a",
                "runs": 3,
                "run_ids": "config_a_r1|config_a_r2|config_a_r3",
                "all_reconciled": "True",
                "p50_mean_ms": 7000,
                "p50_sd_ms": 1000,
                "pooled_p95_ms": 9000,
                "pooled_n": 6,
                "planned_total": 6,
                "completed_total": 6,
                "errored_total": 0,
                "unfinished_total": 0,
                "throughput_per_s_mean": 0.051,
                "escalation_fraction_pooled": "",
            }
        ],
    )
    return {
        "calibration": calibration,
        "runs": runs,
        "configs": configs,
        "workload": workload,
        "jtl_dir": jtl_dir,
        "logs_dir": logs_dir,
        "output": output,
    }


def build(paths: dict[str, Path]):
    return build_comparison(
        calibration_path=paths["calibration"],
        runs_path=paths["runs"],
        configs_path=paths["configs"],
        workload_path=paths["workload"],
        jtl_dir=paths["jtl_dir"],
        logs_dir=paths["logs_dir"],
        client_peak_per_hour=9.0,
    )


def test_builds_rate_comparison_and_flags_queue_growth(tmp_path: Path) -> None:
    rows, calibration = build(make_fixture(tmp_path))
    assert calibration["middle_ms"] == 8506
    assert len(rows) == 1
    row = rows[0]
    assert row["config"] == "config_a"
    assert row["achieved_rate_per_hour_mean"] == "183.60"
    assert row["achieved_multiple_of_peak_mean"] == "20.40"
    assert row["queue_growth_flagged_runs"] == "1"
    assert row["no_queue_growth_flag"] == "no"
    assert row["all_runs_achieved_above_client_peak"] == "yes"


def test_cli_writes_deterministic_output(tmp_path: Path) -> None:
    paths = make_fixture(tmp_path)
    args = [
        "--calibration",
        str(paths["calibration"]),
        "--runs",
        str(paths["runs"]),
        "--configs",
        str(paths["configs"]),
        "--workload",
        str(paths["workload"]),
        "--jtl-dir",
        str(paths["jtl_dir"]),
        "--logs-dir",
        str(paths["logs_dir"]),
        "--output",
        str(paths["output"]),
    ]
    assert main(args) == 0
    first = paths["output"].read_bytes()
    assert main(args) == 0
    assert paths["output"].read_bytes() == first


def test_rejects_missing_raw_artifact(tmp_path: Path) -> None:
    paths = make_fixture(tmp_path)
    (paths["jtl_dir"] / "config_a_r2.jtl").unlink()
    with pytest.raises(RateComparisonError, match="missing raw evidence"):
        build(paths)


def test_rejects_schedule_mismatch(tmp_path: Path) -> None:
    paths = make_fixture(tmp_path)
    rows = list(csv.DictReader(paths["runs"].open(encoding="utf-8", newline="")))
    rows[0]["rate_per_min"] = "9.0"
    write_csv(paths["runs"], list(rows[0]), rows)
    with pytest.raises(RateComparisonError, match="different arrival rate"):
        build(paths)


def test_rejects_wrong_workload_prefix(tmp_path: Path) -> None:
    paths = make_fixture(tmp_path)
    meta_path = paths["jtl_dir"] / "config_a_r1.meta.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    metadata["feeder_rows_used"] = [15176, 15175]
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(RateComparisonError, match="frozen workload prefix"):
        build(paths)
