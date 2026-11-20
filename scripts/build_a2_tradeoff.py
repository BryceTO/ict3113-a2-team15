"""Build the Assignment 2 accuracy-versus-latency trade-off evidence.

The chart joins official even-row accuracy and three-run speed summaries by
configuration ID. Accuracy eligibility requires both the overall floor and all
seven category floors. Configurations without an A2 speed result remain in the
joined CSV and are explicitly annotated as unplotted on the chart.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


class TradeoffError(ValueError):
    """Raised when accuracy and speed evidence cannot be joined safely."""


DISPLAY_NAMES = {
    "llama3.2-1b": "Llama 3.2 1B",
    "gemma3-4b": "Gemma 3 4B",
    "mistral-7b-instruct": "Mistral 7B",
    "cascade_s1": "Cascade S1",
    "cascade_s2": "Cascade S2",
}

OUTPUT_FIELDS = [
    "config",
    "display_name",
    "overall_correct",
    "overall_total",
    "overall_accuracy_percent",
    "overall_floor_percent",
    "overall_pass",
    "category_fail_count",
    "category_failures",
    "all_categories_pass",
    "accuracy_eligible",
    "must_speed_test",
    "speed_available",
    "p50_mean_seconds",
    "p50_sd_seconds",
    "pooled_p95_seconds",
    "pooled_n",
    "escalation_fraction_pooled",
    "plot_status",
    "chart_note",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise TradeoffError(f"CSV file not found: {path}") from exc
    with handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise TradeoffError(f"{path} has no CSV header")
        rows = list(reader)
    if not rows:
        raise TradeoffError(f"{path} contains no data rows")
    return rows


def _require_columns(rows: Sequence[dict[str, str]], required: set[str], path: Path) -> None:
    missing = sorted(required - rows[0].keys())
    if missing:
        raise TradeoffError(f"{path} is missing required columns: {', '.join(missing)}")


def _bool(value: str, context: str) -> bool:
    normalised = value.strip().lower()
    if normalised in {"true", "yes", "1"}:
        return True
    if normalised in {"false", "no", "0"}:
        return False
    raise TradeoffError(f"{context} has invalid boolean {value!r}")


def _integer(row: dict[str, str], column: str, context: str) -> int:
    try:
        return int(row[column])
    except (KeyError, ValueError) as exc:
        raise TradeoffError(
            f"{context} has invalid integer {column}={row.get(column)!r}"
        ) from exc


def _number(row: dict[str, str], column: str, context: str) -> float:
    try:
        return float(row[column])
    except (KeyError, ValueError) as exc:
        raise TradeoffError(
            f"{context} has invalid number {column}={row.get(column)!r}"
        ) from exc


def _unique_by_config(rows: Sequence[dict[str, str]], path: Path) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        config = row.get("config", "").strip()
        if not config or config in indexed:
            raise TradeoffError(f"{path} has duplicate or empty config {config!r}")
        indexed[config] = row
    return indexed


def build_tradeoff(
    *,
    overall_path: Path,
    per_category_path: Path,
    floors_path: Path,
    eligibility_path: Path,
    speed_path: Path,
) -> tuple[list[dict[str, str]], float]:
    overall_rows = _read_csv(overall_path)
    category_rows = _read_csv(per_category_path)
    floor_rows = _read_csv(floors_path)
    eligibility_rows = _read_csv(eligibility_path)
    speed_rows = _read_csv(speed_path)

    _require_columns(
        overall_rows,
        {"config", "category", "correct", "total", "accuracy_percent", "floor_percent", "passes"},
        overall_path,
    )
    _require_columns(
        category_rows,
        {"config", "category", "correct", "total", "accuracy_percent", "floor_percent", "passes"},
        per_category_path,
    )
    _require_columns(
        floor_rows,
        {"category", "floor_percent"},
        floors_path,
    )
    _require_columns(
        eligibility_rows,
        {"config", "overall_pass", "all_categories_pass", "accuracy_eligible", "must_speed_test", "reason"},
        eligibility_path,
    )
    _require_columns(
        speed_rows,
        {
            "config",
            "runs",
            "all_reconciled",
            "p50_mean_ms",
            "p50_sd_ms",
            "pooled_p95_ms",
            "pooled_n",
            "escalation_fraction_pooled",
        },
        speed_path,
    )

    overall = _unique_by_config(overall_rows, overall_path)
    eligibility = _unique_by_config(eligibility_rows, eligibility_path)
    speed = _unique_by_config(speed_rows, speed_path)
    if set(overall) != set(eligibility):
        raise TradeoffError("overall and eligibility configuration sets differ")

    floors: dict[str, float] = {}
    for row in floor_rows:
        category = row["category"].strip()
        if not category or category in floors:
            raise TradeoffError(f"{floors_path} has duplicate or empty category {category!r}")
        floors[category] = _number(row, "floor_percent", f"floor {category}")
    if "overall" not in floors:
        raise TradeoffError(f"{floors_path} has no overall floor")
    overall_floor = floors["overall"]
    expected_categories = set(floors) - {"overall"}
    if len(expected_categories) != 7:
        raise TradeoffError(f"expected seven category floors, found {len(expected_categories)}")

    categories_by_config: dict[str, list[dict[str, str]]] = {config: [] for config in overall}
    for row in category_rows:
        config = row["config"]
        if config not in categories_by_config:
            raise TradeoffError(f"per-category data contains unknown config {config}")
        categories_by_config[config].append(row)

    results: list[dict[str, str]] = []
    for config, overall_row in overall.items():
        context = f"config {config}"
        if overall_row["category"].strip().lower() != "overall":
            raise TradeoffError(f"{context} overall row has category {overall_row['category']!r}")

        accuracy = _number(overall_row, "accuracy_percent", context)
        row_floor = _number(overall_row, "floor_percent", context)
        if not math.isclose(row_floor, overall_floor, rel_tol=0.0, abs_tol=1e-9):
            raise TradeoffError(f"{context} overall floor differs from floors.csv")
        computed_overall_pass = accuracy + 1e-12 >= overall_floor
        stated_overall_pass = _bool(overall_row["passes"], context)
        if computed_overall_pass != stated_overall_pass:
            raise TradeoffError(f"{context} overall pass flag disagrees with unrounded values")

        category_data = categories_by_config[config]
        category_names = {row["category"] for row in category_data}
        if category_names != expected_categories or len(category_data) != 7:
            raise TradeoffError(f"{context} does not contain exactly the seven floor categories")

        failures: list[str] = []
        for row in category_data:
            category = row["category"]
            category_accuracy = _number(row, "accuracy_percent", f"{context} {category}")
            category_floor = _number(row, "floor_percent", f"{context} {category}")
            if not math.isclose(category_floor, floors[category], rel_tol=0.0, abs_tol=1e-9):
                raise TradeoffError(f"{context} {category} floor differs from floors.csv")
            computed_pass = category_accuracy + 1e-12 >= category_floor
            if computed_pass != _bool(row["passes"], f"{context} {category}"):
                raise TradeoffError(f"{context} {category} pass flag disagrees with values")
            if not computed_pass:
                failures.append(category)
        failures.sort()
        all_categories_pass = not failures

        eligibility_row = eligibility[config]
        if _bool(eligibility_row["overall_pass"], context) != computed_overall_pass:
            raise TradeoffError(f"{context} eligibility overall flag disagrees")
        if _bool(eligibility_row["all_categories_pass"], context) != all_categories_pass:
            raise TradeoffError(f"{context} eligibility category flag disagrees")
        accuracy_eligible = _bool(eligibility_row["accuracy_eligible"], context)
        if accuracy_eligible != (computed_overall_pass and all_categories_pass):
            raise TradeoffError(f"{context} accuracy eligibility disagrees with both floors")
        must_speed_test = _bool(eligibility_row["must_speed_test"], context)
        speed_available = config in speed
        if must_speed_test and not speed_available:
            raise TradeoffError(f"{context} required a speed test but has no speed summary")
        if speed_available and not must_speed_test:
            raise TradeoffError(f"{context} has an unexpected speed result")

        p50_mean = ""
        p50_sd = ""
        pooled_p95 = ""
        pooled_n = ""
        escalation = ""
        if speed_available:
            speed_row = speed[config]
            if _integer(speed_row, "runs", context) != 3:
                raise TradeoffError(f"{context} does not have three speed runs")
            if not _bool(speed_row["all_reconciled"], context):
                raise TradeoffError(f"{context} speed summary is not reconciled")
            p50_mean = f"{_number(speed_row, 'p50_mean_ms', context) / 1000:.3f}"
            p50_sd = f"{_number(speed_row, 'p50_sd_ms', context) / 1000:.3f}"
            pooled_p95 = f"{_number(speed_row, 'pooled_p95_ms', context) / 1000:.3f}"
            pooled_n = str(_integer(speed_row, "pooled_n", context))
            raw_escalation = speed_row["escalation_fraction_pooled"].strip()
            escalation = "" if raw_escalation == "" else f"{float(raw_escalation):.3f}"

        if not speed_available:
            plot_status = "accuracy_failed_speed_unmeasured"
            note = "Failed accuracy floors; A2 speed not measured"
        elif accuracy_eligible:
            plot_status = "accuracy_eligible"
            note = "Passes overall and all category floors"
        elif computed_overall_pass:
            plot_status = "category_floor_failed"
            note = f"Fails category floor: {', '.join(failures)}"
        else:
            plot_status = "accuracy_failed"
            note = "Fails overall accuracy floor"

        results.append(
            {
                "config": config,
                "display_name": DISPLAY_NAMES.get(config, config),
                "overall_correct": str(_integer(overall_row, "correct", context)),
                "overall_total": str(_integer(overall_row, "total", context)),
                "overall_accuracy_percent": f"{accuracy:.6f}",
                "overall_floor_percent": f"{overall_floor:.6f}",
                "overall_pass": "yes" if computed_overall_pass else "no",
                "category_fail_count": str(len(failures)),
                "category_failures": "|".join(failures),
                "all_categories_pass": "yes" if all_categories_pass else "no",
                "accuracy_eligible": "yes" if accuracy_eligible else "no",
                "must_speed_test": "yes" if must_speed_test else "no",
                "speed_available": "yes" if speed_available else "no",
                "p50_mean_seconds": p50_mean,
                "p50_sd_seconds": p50_sd,
                "pooled_p95_seconds": pooled_p95,
                "pooled_n": pooled_n,
                "escalation_fraction_pooled": escalation,
                "plot_status": plot_status,
                "chart_note": note,
            }
        )

    if set(speed) != {row["config"] for row in results if row["speed_available"] == "yes"}:
        raise TradeoffError("speed summary contains a configuration absent from joined output")
    results.sort(
        key=lambda row: (
            row["speed_available"] != "yes",
            float(row["p50_mean_seconds"]) if row["p50_mean_seconds"] else math.inf,
        )
    )
    return results, overall_floor


def write_joined_csv(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def render_chart(path: Path, rows: Sequence[dict[str, str]], overall_floor: float) -> None:
    plotted = [row for row in rows if row["speed_available"] == "yes"]
    if not plotted:
        raise TradeoffError("no configurations have speed data to plot")

    figure, axis = plt.subplots(figsize=(10, 5.625), dpi=160)
    figure.patch.set_facecolor("white")
    axis.set_facecolor("white")

    eligible_color = "#2563EB"
    failure_color = "#DC2626"
    floor_color = "#B45309"
    label_offsets = {
        "gemma3-4b": (8, 8),
        "mistral-7b-instruct": (-92, 8),
        "cascade_s1": (8, -22),
        "cascade_s2": (8, 8),
    }

    for row in plotted:
        x = float(row["p50_mean_seconds"])
        y = float(row["overall_accuracy_percent"])
        eligible = row["accuracy_eligible"] == "yes"
        axis.scatter(
            [x],
            [y],
            s=120,
            marker="o" if eligible else "D",
            color=eligible_color if eligible else failure_color,
            edgecolor="white",
            linewidth=1.2,
            zorder=4,
        )
        accuracy_text = f"{y:.1f}%"
        latency_text = f"{x:.1f}s"
        label = f"{row['display_name']}\n{accuracy_text}, {latency_text}"
        dx, dy = label_offsets.get(row["config"], (8, 8))
        axis.annotate(
            label,
            (x, y),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=9,
            color="#111827",
            ha="left",
            va="bottom" if dy >= 0 else "top",
        )

    axis.axhline(
        overall_floor,
        color=floor_color,
        linestyle=(0, (5, 4)),
        linewidth=1.7,
        zorder=2,
    )
    axis.text(
        0.4,
        overall_floor + 0.45,
        f"Overall accuracy floor {overall_floor:.1f}%",
        color=floor_color,
        fontsize=9,
        ha="left",
        va="bottom",
    )

    max_x = max(float(row["p50_mean_seconds"]) for row in plotted)
    min_y = min(overall_floor, *(float(row["overall_accuracy_percent"]) for row in plotted))
    max_y = max(float(row["overall_accuracy_percent"]) for row in plotted)
    axis.set_xlim(0, max(35, max_x * 1.15))
    axis.set_ylim(max(0, min_y - 5.5), min(100, max_y + 5.5))
    axis.set_xlabel("Mean p50 latency (seconds, lower is better)", fontsize=10)
    axis.set_ylabel("Even-row test accuracy (%, higher is better)", fontsize=10)
    figure.text(
        0.094,
        0.965,
        "Accuracy and latency trade-off",
        fontsize=14,
        fontweight="bold",
        color="#111827",
        ha="left",
        va="top",
    )
    figure.text(
        0.094,
        0.925,
        "Latency is the mean of three run p50 values",
        fontsize=9,
        color="#4B5563",
        ha="left",
        va="top",
    )
    axis.grid(axis="y", color="#E5E7EB", linewidth=0.8)
    axis.grid(axis="x", visible=False)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color("#9CA3AF")
    axis.spines["bottom"].set_color("#9CA3AF")
    axis.tick_params(colors="#374151", labelsize=9)

    legend_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=eligible_color,
               markeredgecolor="white", markersize=9, label="Passes overall and category floors"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor=failure_color,
               markeredgecolor="white", markersize=8, label="Fails at least one category floor"),
        Line2D([0], [0], color=floor_color, linestyle=(0, (5, 4)), linewidth=1.7,
               label="Overall floor"),
    ]
    axis.legend(
        handles=legend_handles,
        loc="lower right",
        frameon=False,
        fontsize=8.5,
    )

    unplotted = [row for row in rows if row["speed_available"] != "yes"]
    if unplotted:
        summary = "; ".join(
            f"{row['display_name']} {float(row['overall_accuracy_percent']):.1f}% "
            "(accuracy failed; speed unmeasured)"
            for row in unplotted
        )
        axis.text(
            0.01,
            0.025,
            f"Not plotted: {summary}",
            transform=axis.transAxes,
            fontsize=8.2,
            color="#4B5563",
            ha="left",
            va="bottom",
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "#F3F4F6", "edgecolor": "none"},
        )

    failures = [row for row in plotted if row["category_fail_count"] != "0"]
    if failures:
        detail = "; ".join(
            f"{row['display_name']}: {row['category_failures'].replace('|', ', ')}"
            for row in failures
        )
        figure.text(
            0.08,
            0.015,
            f"Category-floor failures: {detail}",
            fontsize=8,
            color="#6B7280",
            ha="left",
            va="bottom",
        )

    figure.tight_layout(rect=(0.035, 0.06, 0.985, 0.89))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, facecolor="white")
    plt.close(figure)


def build_parser() -> argparse.ArgumentParser:
    base = Path("results/a2/accuracy/summary_reviewed_r1")
    parser = argparse.ArgumentParser(
        description="Build the A2 accuracy-versus-latency trade-off CSV and chart."
    )
    parser.add_argument("--overall", type=Path, default=base / "overall.csv")
    parser.add_argument("--per-category", type=Path, default=base / "per_category.csv")
    parser.add_argument("--floors", type=Path, default=base / "floors.csv")
    parser.add_argument("--eligibility", type=Path, default=base / "eligibility.csv")
    parser.add_argument(
        "--speed", type=Path, default=Path("results/a2/summary/a2_speed_configs.csv")
    )
    parser.add_argument(
        "--output-csv", type=Path, default=Path("results/a2/summary/a2_tradeoff.csv")
    )
    parser.add_argument(
        "--output-chart", type=Path, default=Path("results/a2/summary/a2_tradeoff.png")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows, floor = build_tradeoff(
            overall_path=args.overall,
            per_category_path=args.per_category,
            floors_path=args.floors,
            eligibility_path=args.eligibility,
            speed_path=args.speed,
        )
        write_joined_csv(args.output_csv, rows)
        render_chart(args.output_chart, rows, floor)
    except TradeoffError as exc:
        raise SystemExit(f"trade-off build failed: {exc}") from exc

    plotted = sum(row["speed_available"] == "yes" for row in rows)
    print(
        f"wrote {args.output_csv} and {args.output_chart}: "
        f"configs={len(rows)}, plotted={plotted}, overall_floor={floor:.6f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
