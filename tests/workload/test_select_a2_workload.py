import csv
from pathlib import Path

import pytest

from scripts.select_a2_workload import (
    InputValidationError,
    load_golden_ids,
    load_source,
    main,
    percentile,
    select_workload,
)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_source(path: Path, count: int = 80) -> list[dict[str, object]]:
    rows = []
    for offset in range(count):
        length = 200 + offset * 20
        rows.append(
            {
                "row": 15000 + offset,
                "source_label": f"label-{offset % 7}",
                "narrative": "x" * length,
            }
        )
    write_csv(path, ["row", "source_label", "narrative"], rows)
    return rows


def make_golden(path: Path, row_ids: list[int]) -> None:
    write_csv(
        path,
        ["ROW", "NARRATIVE", "GOLDEN_LABEL"],
        [
            {
                "ROW": row_id,
                "NARRATIVE": f"golden {row_id}",
                "GOLDEN_LABEL": "Credit card",
            }
            for row_id in row_ids
        ],
    )


def test_percentile_uses_linear_n_minus_one_interpolation() -> None:
    assert percentile([0, 10, 20, 30], 0.25) == pytest.approx(7.5)
    assert percentile([0, 10, 20, 30], 0.90) == pytest.approx(27.0)


def test_selection_is_deterministic_disjoint_and_excludes_golden(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    golden_path = tmp_path / "golden.csv"
    make_source(source_path)
    golden_ids = list(range(15000, 15008))
    make_golden(golden_path, golden_ids)

    source = load_source(source_path)
    golden = load_golden_ids(golden_path)
    first, summary = select_workload(
        source, golden, measured_count=20, long_count=4
    )
    second, _ = select_workload(source, golden, measured_count=20, long_count=4)

    assert first == second
    assert summary.source_rows == 80
    assert summary.golden_rows == 8
    assert summary.eligible_rows == 72

    selected_ids = [item.ticket.row_id for item in first]
    assert len(selected_ids) == 26
    assert len(selected_ids) == len(set(selected_ids))
    assert not set(selected_ids) & set(golden_ids)

    assert sum(item.purpose == "warmup" for item in first) == 3
    assert sum(item.purpose == "calibration" for item in first) == 3
    assert sum(item.purpose == "measured" for item in first) == 20
    assert sum(
        item.purpose == "measured" and item.length_group == "long"
        for item in first
    ) == 4


def test_cli_writes_reproducible_auditable_output(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    golden_path = tmp_path / "golden.csv"
    first_output = tmp_path / "first.csv"
    second_output = tmp_path / "second.csv"
    make_source(source_path)
    make_golden(golden_path, list(range(15000, 15005)))

    common_args = [
        "--input",
        str(source_path),
        "--golden",
        str(golden_path),
        "--measured-count",
        "18",
        "--long-count",
        "3",
    ]
    assert main([*common_args, "--output", str(first_output)]) == 0
    assert main([*common_args, "--output", str(second_output)]) == 0
    assert first_output.read_bytes() == second_output.read_bytes()

    with first_output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == [
        "purpose",
        "order",
        "row_id",
        "source_label",
        "narrative_chars",
        "length_group",
    ]
    assert len(rows) == 24


def test_validate_only_does_not_write_output(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    golden_path = tmp_path / "golden.csv"
    output_path = tmp_path / "must-not-exist.csv"
    make_source(source_path)
    make_golden(golden_path, list(range(15000, 15005)))

    assert (
        main(
            [
                "--input",
                str(source_path),
                "--golden",
                str(golden_path),
                "--output",
                str(output_path),
                "--measured-count",
                "18",
                "--long-count",
                "3",
                "--validate-only",
            ]
        )
        == 0
    )
    assert not output_path.exists()


@pytest.mark.parametrize(
    ("fieldnames", "rows", "message"),
    [
        (
            ["row", "source_label"],
            [{"row": 15000, "source_label": "Credit card"}],
            "missing required columns: narrative",
        ),
        (
            ["row", "source_label", "narrative"],
            [
                {"row": 15000, "source_label": "Credit card", "narrative": "one"},
                {"row": 15000, "source_label": "Mortgage", "narrative": "two"},
            ],
            "duplicate row ID 15000",
        ),
        (
            ["row", "source_label", "narrative"],
            [{"row": 14999, "source_label": "Credit card", "narrative": "one"}],
            "outside Team 15's range",
        ),
        (
            ["row", "source_label", "narrative"],
            [{"row": 15000, "source_label": "Credit card", "narrative": "  "}],
            "empty narrative",
        ),
        (
            ["row", "source_label", "narrative"],
            [{"row": 15000, "source_label": "", "narrative": "one"}],
            "empty source_label",
        ),
    ],
)
def test_source_validation_rejects_bad_inputs(
    tmp_path: Path,
    fieldnames: list[str],
    rows: list[dict[str, object]],
    message: str,
) -> None:
    source_path = tmp_path / "source.csv"
    write_csv(source_path, fieldnames, rows)
    with pytest.raises(InputValidationError, match=message):
        load_source(source_path)


def test_selection_rejects_golden_rows_missing_from_source(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    golden_path = tmp_path / "golden.csv"
    make_source(source_path, count=40)
    make_golden(golden_path, [15000, 15999])

    with pytest.raises(InputValidationError, match="golden row.*missing"):
        select_workload(
            load_source(source_path),
            load_golden_ids(golden_path),
            measured_count=10,
            long_count=2,
        )


def test_selection_rejects_insufficient_candidates(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    golden_path = tmp_path / "golden.csv"
    make_source(source_path, count=30)
    make_golden(golden_path, [15000])

    with pytest.raises(InputValidationError, match="not enough"):
        select_workload(
            load_source(source_path),
            load_golden_ids(golden_path),
            measured_count=25,
            long_count=10,
        )
