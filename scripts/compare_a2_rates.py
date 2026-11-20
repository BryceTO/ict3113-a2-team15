"""Compare Assignment 2 scheduled and achieved rates with the A1 client peak.

The script treats Zhengda's calibration record and speed summaries as the
authoritative derived inputs, then verifies that every summarized run has its
JTL, properties, metadata, and service log. It also checks that each run used
the frozen workload prefix and the common calibrated schedule.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any, Sequence


class RateComparisonError(ValueError):
    """Raised when Phase 4 evidence is incomplete or inconsistent."""


OUTPUT_FIELDS = [
    "config",
    "runs",
    "scheduled_rate_per_hour",
    "client_peak_per_hour",
    "scheduled_multiple_of_peak",
    "achieved_rate_per_hour_mean",
    "achieved_rate_per_hour_min_run",
    "achieved_multiple_of_peak_mean",
    "achieved_pct_of_scheduled",
    "planned_total",
    "completed_total",
    "errored_total",
    "unfinished_total",
    "all_runs_reconciled",
    "all_runs_achieved_above_client_peak",
    "queue_growth_flagged_runs",
    "no_queue_growth_flag",
    "p50_mean_seconds",
    "p50_sd_seconds",
    "pooled_p95_seconds",
    "pooled_n",
    "max_backlog",
    "escalation_fraction_pooled",
    "run_ids",
    "interpretation",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise RateComparisonError(f"CSV file not found: {path}") from exc
    with handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise RateComparisonError(f"{path} has no CSV header")
        rows = list(reader)
    if not rows:
        raise RateComparisonError(f"{path} contains no data rows")
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RateComparisonError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RateComparisonError(f"invalid JSON in {path}: {exc}") from exc


def _require_columns(rows: Sequence[dict[str, str]], required: set[str], path: Path) -> None:
    missing = sorted(required - rows[0].keys())
    if missing:
        raise RateComparisonError(
            f"{path} is missing required columns: {', '.join(missing)}"
        )


def _integer(row: dict[str, str], column: str, context: str) -> int:
    try:
        return int(row[column])
    except (KeyError, ValueError) as exc:
        raise RateComparisonError(
            f"{context} has invalid integer {column}={row.get(column)!r}"
        ) from exc


def _number(row: dict[str, str], column: str, context: str) -> float:
    try:
        return float(row[column])
    except (KeyError, ValueError) as exc:
        raise RateComparisonError(
            f"{context} has invalid number {column}={row.get(column)!r}"
        ) from exc


def _yes(value: str) -> bool:
    return value.strip().lower() in {"yes", "true", "1"}


def _close(left: float, right: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def _load_measured_prefix(path: Path, planned: int) -> list[int]:
    rows = _read_csv(path)
    _require_columns(rows, {"purpose", "order", "row_id"}, path)
    measured = [row for row in rows if row["purpose"].strip().lower() == "measured"]
    measured.sort(key=lambda row: _integer(row, "order", str(path)))
    orders = [_integer(row, "order", str(path)) for row in measured]
    if orders != list(range(1, len(measured) + 1)):
        raise RateComparisonError(f"{path} measured order values are not contiguous")
    if len(measured) < planned:
        raise RateComparisonError(
            f"{path} has {len(measured)} measured rows but schedule requires {planned}"
        )
    return [_integer(row, "row_id", str(path)) for row in measured[:planned]]


def _calibration_values(path: Path) -> dict[str, float | int]:
    calibration = _read_json(path)
    timings = calibration.get("calibration_ms")
    settings = calibration.get("settings")
    if not isinstance(timings, list) or len(timings) != 3:
        raise RateComparisonError(f"{path} must contain exactly three calibration_ms values")
    if not isinstance(settings, dict):
        raise RateComparisonError(f"{path} is missing settings")

    numeric_timings = [int(value) for value in timings]
    middle_ms = int(calibration.get("middle_ms", -1))
    if middle_ms != sorted(numeric_timings)[1]:
        raise RateComparisonError(
            f"{path} middle_ms {middle_ms} does not match the middle calibration timing"
        )

    required = {
        "s_seconds",
        "arrival_interval_s",
        "rate_per_min",
        "rate_per_hour",
        "arrival_window_s",
        "response_timeout_s",
        "drain_pause_s",
        "planned_arrivals",
    }
    missing = sorted(required - settings.keys())
    if missing:
        raise RateComparisonError(
            f"{path} settings are missing: {', '.join(missing)}"
        )

    values: dict[str, float | int] = {
        "middle_ms": middle_ms,
        "s_seconds": float(settings["s_seconds"]),
        "arrival_interval_s": float(settings["arrival_interval_s"]),
        "rate_per_min": float(settings["rate_per_min"]),
        "rate_per_hour": float(settings["rate_per_hour"]),
        "arrival_window_s": int(settings["arrival_window_s"]),
        "response_timeout_s": int(settings["response_timeout_s"]),
        "drain_pause_s": int(settings["drain_pause_s"]),
        "planned_arrivals": int(settings["planned_arrivals"]),
    }
    if not _close(float(values["arrival_interval_s"]), 2 * float(values["s_seconds"]), 0.02):
        raise RateComparisonError(f"{path} arrival interval is not 2 x S")
    if not _close(float(values["rate_per_hour"]), 60 * float(values["rate_per_min"]), 0.01):
        raise RateComparisonError(f"{path} hourly and per-minute rates disagree")
    return values


def _validate_raw_run(
    row: dict[str, str],
    *,
    jtl_dir: Path,
    logs_dir: Path,
    expected_prefix: Sequence[int],
    calibration: dict[str, float | int],
) -> None:
    run_id = row["run_id"]
    expected_files = [
        jtl_dir / f"{run_id}.jtl",
        jtl_dir / f"{run_id}.properties",
        jtl_dir / f"{run_id}.meta.json",
        logs_dir / f"{run_id}.log",
    ]
    missing = [str(path) for path in expected_files if not path.is_file()]
    if missing:
        raise RateComparisonError(
            f"{run_id} is missing raw evidence: {', '.join(missing)}"
        )

    metadata = _read_json(jtl_dir / f"{run_id}.meta.json")
    if metadata.get("run_id") != run_id:
        raise RateComparisonError(f"{run_id} metadata has a different run_id")
    if metadata.get("config") != row["config"]:
        raise RateComparisonError(f"{run_id} metadata config does not match the summary")
    if int(metadata.get("jmeter_exit_code", -1)) != 0:
        raise RateComparisonError(f"{run_id} JMeter exit code is not zero")
    if metadata.get("feeder_rows_used") != list(expected_prefix):
        raise RateComparisonError(f"{run_id} did not use the frozen workload prefix")

    settings = metadata.get("settings")
    if not isinstance(settings, dict):
        raise RateComparisonError(f"{run_id} metadata is missing settings")
    checks = {
        "s_seconds": float(calibration["s_seconds"]),
        "rate_per_min": float(calibration["rate_per_min"]),
        "arrival_window_s": float(calibration["arrival_window_s"]),
        "planned_arrivals": float(calibration["planned_arrivals"]),
    }
    for key, expected in checks.items():
        try:
            actual = float(settings[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise RateComparisonError(f"{run_id} metadata has invalid {key}") from exc
        if not _close(actual, expected, 1e-6):
            raise RateComparisonError(
                f"{run_id} metadata {key}={actual} differs from calibration {expected}"
            )


def build_comparison(
    *,
    calibration_path: Path,
    runs_path: Path,
    configs_path: Path,
    workload_path: Path,
    jtl_dir: Path,
    logs_dir: Path,
    client_peak_per_hour: float,
) -> tuple[list[dict[str, str]], dict[str, float | int]]:
    if client_peak_per_hour <= 0:
        raise RateComparisonError("client peak must be greater than zero")

    calibration = _calibration_values(calibration_path)
    planned = int(calibration["planned_arrivals"])
    expected_prefix = _load_measured_prefix(workload_path, planned)
    run_rows = _read_csv(runs_path)
    config_rows = _read_csv(configs_path)

    _require_columns(
        run_rows,
        {
            "run_id",
            "config",
            "run",
            "s_seconds",
            "rate_per_min",
            "window_s",
            "planned",
            "recorded",
            "completed",
            "errored",
            "unfinished",
            "throughput_per_s",
            "p50_ms",
            "max_backlog",
            "reconciled",
            "flags",
        },
        runs_path,
    )
    _require_columns(
        config_rows,
        {
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
        },
        configs_path,
    )

    seen_run_ids: set[str] = set()
    for row in run_rows:
        run_id = row["run_id"]
        if not run_id or run_id in seen_run_ids:
            raise RateComparisonError(f"duplicate or empty run_id in {runs_path}: {run_id!r}")
        seen_run_ids.add(run_id)

        context = f"run {run_id}"
        if not _close(_number(row, "s_seconds", context), float(calibration["s_seconds"])):
            raise RateComparisonError(f"{run_id} used a different S")
        if not _close(
            _number(row, "rate_per_min", context),
            float(calibration["rate_per_min"]),
        ):
            raise RateComparisonError(f"{run_id} used a different arrival rate")
        if _integer(row, "window_s", context) != int(calibration["arrival_window_s"]):
            raise RateComparisonError(f"{run_id} used a different arrival window")
        if _integer(row, "planned", context) != planned:
            raise RateComparisonError(f"{run_id} planned count differs from calibration")
        _validate_raw_run(
            row,
            jtl_dir=jtl_dir,
            logs_dir=logs_dir,
            expected_prefix=expected_prefix,
            calibration=calibration,
        )

    results: list[dict[str, str]] = []
    for config_row in config_rows:
        config = config_row["config"]
        context = f"config {config}"
        config_runs = [row for row in run_rows if row["config"] == config]
        expected_runs = _integer(config_row, "runs", context)
        if len(config_runs) != expected_runs:
            raise RateComparisonError(
                f"{config} expected {expected_runs} runs but found {len(config_runs)}"
            )
        run_numbers = sorted(_integer(row, "run", row["run_id"]) for row in config_runs)
        if run_numbers != list(range(1, expected_runs + 1)):
            raise RateComparisonError(f"{config} run numbers are incomplete or duplicated")

        run_ids = [row["run_id"] for row in sorted(config_runs, key=lambda row: int(row["run"]))]
        summary_run_ids = config_row["run_ids"].split("|")
        if run_ids != summary_run_ids:
            raise RateComparisonError(f"{config} run_ids disagree between summaries")

        planned_total = sum(_integer(row, "planned", row["run_id"]) for row in config_runs)
        completed_total = sum(_integer(row, "completed", row["run_id"]) for row in config_runs)
        errored_total = sum(_integer(row, "errored", row["run_id"]) for row in config_runs)
        unfinished_total = sum(_integer(row, "unfinished", row["run_id"]) for row in config_runs)
        recorded_total = sum(_integer(row, "recorded", row["run_id"]) for row in config_runs)
        aggregates = {
            "planned_total": planned_total,
            "completed_total": completed_total,
            "errored_total": errored_total,
            "unfinished_total": unfinished_total,
        }
        for column, actual in aggregates.items():
            if _integer(config_row, column, context) != actual:
                raise RateComparisonError(f"{config} {column} disagrees with per-run rows")
        if recorded_total != planned_total:
            raise RateComparisonError(f"{config} did not record every planned request")

        p50_values = [_number(row, "p50_ms", row["run_id"]) for row in config_runs]
        p50_mean_ms = _number(config_row, "p50_mean_ms", context)
        if not _close(p50_mean_ms, statistics.mean(p50_values), 0.11):
            raise RateComparisonError(f"{config} p50 mean disagrees with per-run rows")

        all_reconciled = _yes(config_row["all_reconciled"]) and all(
            _yes(row["reconciled"]) for row in config_runs
        )
        if not all_reconciled:
            raise RateComparisonError(f"{config} contains an unreconciled run")

        mean_throughput_per_s = _number(config_row, "throughput_per_s_mean", context)
        achieved_per_hour = mean_throughput_per_s * 3600
        per_run_hourly = [
            _number(row, "throughput_per_s", row["run_id"]) * 3600
            for row in config_runs
        ]
        achieved_min = min(per_run_hourly)
        scheduled_per_hour = float(calibration["rate_per_hour"])
        queue_growth_runs = sum(
            "queue growth" in row.get("flags", "").lower() for row in config_runs
        )
        max_backlog = max(_integer(row, "max_backlog", row["run_id"]) for row in config_runs)
        all_above_peak = all(value >= client_peak_per_hour for value in per_run_hourly)
        no_queue_flag = queue_growth_runs == 0

        escalation = config_row["escalation_fraction_pooled"].strip()
        escalation_display = "" if escalation == "" else f"{float(escalation):.3f}"
        interpretation = (
            f"All {completed_total}/{planned_total} requests completed with no errors or unfinished requests. "
            f"Mean achieved rate was {achieved_per_hour:.1f}/h "
            f"({achieved_per_hour / client_peak_per_hour:.1f}x the 9/h client peak)."
        )
        if no_queue_flag:
            interpretation += " No queue-growth run was flagged."
        else:
            interpretation += (
                f" Queue growth was flagged in {queue_growth_runs}/{expected_runs} runs, "
                "so the higher A2 rate was not cleanly sustained."
            )

        results.append(
            {
                "config": config,
                "runs": str(expected_runs),
                "scheduled_rate_per_hour": f"{scheduled_per_hour:.2f}",
                "client_peak_per_hour": f"{client_peak_per_hour:.2f}",
                "scheduled_multiple_of_peak": f"{scheduled_per_hour / client_peak_per_hour:.2f}",
                "achieved_rate_per_hour_mean": f"{achieved_per_hour:.2f}",
                "achieved_rate_per_hour_min_run": f"{achieved_min:.2f}",
                "achieved_multiple_of_peak_mean": f"{achieved_per_hour / client_peak_per_hour:.2f}",
                "achieved_pct_of_scheduled": f"{100 * achieved_per_hour / scheduled_per_hour:.2f}",
                "planned_total": str(planned_total),
                "completed_total": str(completed_total),
                "errored_total": str(errored_total),
                "unfinished_total": str(unfinished_total),
                "all_runs_reconciled": "yes",
                "all_runs_achieved_above_client_peak": "yes" if all_above_peak else "no",
                "queue_growth_flagged_runs": str(queue_growth_runs),
                "no_queue_growth_flag": "yes" if no_queue_flag else "no",
                "p50_mean_seconds": f"{p50_mean_ms / 1000:.3f}",
                "p50_sd_seconds": f"{_number(config_row, 'p50_sd_ms', context) / 1000:.3f}",
                "pooled_p95_seconds": f"{_number(config_row, 'pooled_p95_ms', context) / 1000:.3f}",
                "pooled_n": str(_integer(config_row, "pooled_n", context)),
                "max_backlog": str(max_backlog),
                "escalation_fraction_pooled": escalation_display,
                "run_ids": "|".join(run_ids),
                "interpretation": interpretation,
            }
        )

    represented_configs = {row["config"] for row in run_rows}
    summarized_configs = {row["config"] for row in config_rows}
    if represented_configs != summarized_configs:
        raise RateComparisonError(
            "configuration sets differ between per-run and per-configuration summaries"
        )

    results.sort(key=lambda row: float(row["p50_mean_seconds"]))
    return results, calibration


def write_comparison(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare A2 scheduled and achieved rates with the A1 client peak."
    )
    parser.add_argument(
        "--calibration",
        type=Path,
        default=Path("results/a2/calibration/a2_calibration.json"),
    )
    parser.add_argument(
        "--runs",
        type=Path,
        default=Path("results/a2/summary/a2_speed_runs.csv"),
    )
    parser.add_argument(
        "--configs",
        type=Path,
        default=Path("results/a2/summary/a2_speed_configs.csv"),
    )
    parser.add_argument(
        "--workload",
        type=Path,
        default=Path("jmeter/a2_workload_rows.csv"),
    )
    parser.add_argument("--jtl-dir", type=Path, default=Path("results/a2/jtl"))
    parser.add_argument("--logs-dir", type=Path, default=Path("results/logs"))
    parser.add_argument(
        "--client-peak-per-hour",
        type=float,
        default=9.0,
        help="A1 formal client peak in tickets/hour (default: 9)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/a2/summary/a2_rate_comparison.csv"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows, calibration = build_comparison(
            calibration_path=args.calibration,
            runs_path=args.runs,
            configs_path=args.configs,
            workload_path=args.workload,
            jtl_dir=args.jtl_dir,
            logs_dir=args.logs_dir,
            client_peak_per_hour=args.client_peak_per_hour,
        )
        write_comparison(args.output, rows)
    except RateComparisonError as exc:
        raise SystemExit(f"rate comparison failed: {exc}") from exc

    print(
        f"wrote {args.output}: configs={len(rows)}, "
        f"S={float(calibration['s_seconds']):.1f}s, "
        f"scheduled={float(calibration['rate_per_hour']):.2f}/h, "
        f"client_peak={args.client_peak_per_hour:.2f}/h"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
