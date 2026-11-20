import csv
from pathlib import Path

import pytest
from PIL import Image

from scripts.build_a2_tradeoff import TradeoffError, build_tradeoff, main


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_fixture(tmp_path: Path) -> dict[str, Path]:
    overall = tmp_path / "overall.csv"
    per_category = tmp_path / "per_category.csv"
    floors = tmp_path / "floors.csv"
    eligibility = tmp_path / "eligibility.csv"
    speed = tmp_path / "speed.csv"
    output_csv = tmp_path / "tradeoff.csv"
    output_chart = tmp_path / "tradeoff.png"

    categories = [f"Category {index}" for index in range(1, 8)]
    floor_rows = [{"category": "overall", "floor_percent": 70.0}]
    floor_rows.extend({"category": category, "floor_percent": 60.0} for category in categories)
    write_csv(floors, ["category", "floor_percent"], floor_rows)

    configs = [
        ("eligible", 80.0, True, [], True, True),
        ("category_fail", 75.0, True, ["Category 2"], False, True),
        ("overall_fail", 40.0, False, categories, False, False),
    ]
    write_csv(
        overall,
        ["config", "category", "correct", "total", "accuracy_percent", "floor_percent", "passes"],
        [
            {
                "config": config,
                "category": "overall",
                "correct": int(accuracy),
                "total": 100,
                "accuracy_percent": accuracy,
                "floor_percent": 70.0,
                "passes": overall_pass,
            }
            for config, accuracy, overall_pass, _, _, _ in configs
        ],
    )

    category_rows = []
    for config, _, _, failures, _, _ in configs:
        for category in categories:
            passes = category not in failures
            category_rows.append(
                {
                    "config": config,
                    "category": category,
                    "correct": 8 if passes else 5,
                    "total": 10,
                    "accuracy_percent": 80.0 if passes else 50.0,
                    "floor_percent": 60.0,
                    "passes": passes,
                }
            )
    write_csv(
        per_category,
        ["config", "category", "correct", "total", "accuracy_percent", "floor_percent", "passes"],
        category_rows,
    )
    write_csv(
        eligibility,
        ["config", "overall_pass", "all_categories_pass", "accuracy_eligible", "must_speed_test", "reason"],
        [
            {
                "config": config,
                "overall_pass": overall_pass,
                "all_categories_pass": not failures,
                "accuracy_eligible": eligible,
                "must_speed_test": must_speed,
                "reason": "fixture",
            }
            for config, _, overall_pass, failures, eligible, must_speed in configs
        ],
    )
    write_csv(
        speed,
        [
            "config",
            "runs",
            "all_reconciled",
            "p50_mean_ms",
            "p50_sd_ms",
            "pooled_p95_ms",
            "pooled_n",
            "escalation_fraction_pooled",
        ],
        [
            {
                "config": "eligible",
                "runs": 3,
                "all_reconciled": True,
                "p50_mean_ms": 7000,
                "p50_sd_ms": 1000,
                "pooled_p95_ms": 12000,
                "pooled_n": 90,
                "escalation_fraction_pooled": "",
            },
            {
                "config": "category_fail",
                "runs": 3,
                "all_reconciled": True,
                "p50_mean_ms": 11000,
                "p50_sd_ms": 2000,
                "pooled_p95_ms": 20000,
                "pooled_n": 90,
                "escalation_fraction_pooled": 1.0,
            },
        ],
    )
    return {
        "overall": overall,
        "per_category": per_category,
        "floors": floors,
        "eligibility": eligibility,
        "speed": speed,
        "output_csv": output_csv,
        "output_chart": output_chart,
    }


def build(paths: dict[str, Path]):
    return build_tradeoff(
        overall_path=paths["overall"],
        per_category_path=paths["per_category"],
        floors_path=paths["floors"],
        eligibility_path=paths["eligibility"],
        speed_path=paths["speed"],
    )


def test_join_preserves_unplotted_accuracy_failure(tmp_path: Path) -> None:
    rows, floor = build(make_fixture(tmp_path))
    assert floor == 70.0
    by_config = {row["config"]: row for row in rows}
    assert by_config["eligible"]["plot_status"] == "accuracy_eligible"
    assert by_config["category_fail"]["plot_status"] == "category_floor_failed"
    assert by_config["category_fail"]["category_failures"] == "Category 2"
    assert by_config["overall_fail"]["plot_status"] == "accuracy_failed_speed_unmeasured"
    assert by_config["overall_fail"]["p50_mean_seconds"] == ""


def test_cli_writes_deterministic_csv_and_slide_sized_chart(tmp_path: Path) -> None:
    paths = make_fixture(tmp_path)
    args = [
        "--overall",
        str(paths["overall"]),
        "--per-category",
        str(paths["per_category"]),
        "--floors",
        str(paths["floors"]),
        "--eligibility",
        str(paths["eligibility"]),
        "--speed",
        str(paths["speed"]),
        "--output-csv",
        str(paths["output_csv"]),
        "--output-chart",
        str(paths["output_chart"]),
    ]
    assert main(args) == 0
    first_csv = paths["output_csv"].read_bytes()
    assert main(args) == 0
    assert paths["output_csv"].read_bytes() == first_csv
    with Image.open(paths["output_chart"]) as image:
        assert image.size == (1600, 900)


def test_rejects_category_pass_that_disagrees_with_values(tmp_path: Path) -> None:
    paths = make_fixture(tmp_path)
    rows = list(csv.DictReader(paths["per_category"].open(encoding="utf-8", newline="")))
    rows[0]["passes"] = "False"
    write_csv(paths["per_category"], list(rows[0]), rows)
    with pytest.raises(TradeoffError, match="pass flag disagrees"):
        build(paths)


def test_rejects_required_missing_speed_result(tmp_path: Path) -> None:
    paths = make_fixture(tmp_path)
    rows = list(csv.DictReader(paths["speed"].open(encoding="utf-8", newline="")))
    write_csv(paths["speed"], list(rows[0]), rows[:1])
    with pytest.raises(TradeoffError, match="required a speed test"):
        build(paths)
