import csv
import json
from pathlib import Path

import pytest

from scripts.make_feeder import (
    InputValidationError,
    WorkloadRow,
    load_workload_rows,
    main,
    resolve_measured_tickets,
    serialise_feeder_lines,
)
from scripts.select_a2_workload import load_golden_ids, load_source


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    source_path = tmp_path / "source.csv"
    rows_path = tmp_path / "rows.csv"
    golden_path = tmp_path / "golden.csv"

    narratives = {
        15000: "golden ticket",
        15001: "warm-up ticket",
        15002: "calibration ticket",
        15003: 'first measured: quote " tab\t newline\n snowman \u2603',
        15004: "second measured",
        15005: "third measured",
    }
    write_csv(
        source_path,
        ["row", "source_label", "narrative"],
        [
            {"row": row_id, "source_label": "Credit card", "narrative": narrative}
            for row_id, narrative in narratives.items()
        ],
    )
    write_csv(
        golden_path,
        ["ROW", "NARRATIVE", "GOLDEN_LABEL"],
        [{"ROW": 15000, "NARRATIVE": "golden ticket", "GOLDEN_LABEL": "Credit card"}],
    )
    write_csv(
        rows_path,
        ["purpose", "order", "row_id", "source_label", "narrative_chars", "length_group"],
        [
            {"purpose": "warmup", "order": 1, "row_id": 15001},
            {"purpose": "calibration", "order": 1, "row_id": 15002},
            {"purpose": "measured", "order": 2, "row_id": 15003},
            {"purpose": "measured", "order": 1, "row_id": 15004},
            {"purpose": "measured", "order": 3, "row_id": 15005},
        ],
    )
    return source_path, rows_path, golden_path


def test_cli_writes_only_measured_rows_in_declared_order(tmp_path: Path) -> None:
    source_path, rows_path, golden_path = make_files(tmp_path)
    output_path = tmp_path / "feeder.tsv"

    assert (
        main(
            [
                "--input",
                str(source_path),
                "--rows",
                str(rows_path),
                "--golden",
                str(golden_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    physical_lines = output_path.read_text(encoding="ascii").splitlines()
    assert len(physical_lines) == 3
    assert [int(line.split("\t", 1)[0]) for line in physical_lines] == [15004, 15003, 15005]

    decoded = [json.loads(line.split("\t", 1)[1]) for line in physical_lines]
    assert decoded[1] == {
        "narrative": 'first measured: quote " tab\t newline\n snowman \u2603',
        "row_id": 15003,
    }


def test_feeder_generation_is_deterministic(tmp_path: Path) -> None:
    source_path, rows_path, golden_path = make_files(tmp_path)
    first = tmp_path / "first.tsv"
    second = tmp_path / "second.tsv"
    common = [
        "--input",
        str(source_path),
        "--rows",
        str(rows_path),
        "--golden",
        str(golden_path),
    ]
    main([*common, "--output", str(first)])
    main([*common, "--output", str(second)])
    assert first.read_bytes() == second.read_bytes()


def test_validate_only_does_not_write_output(tmp_path: Path) -> None:
    source_path, rows_path, golden_path = make_files(tmp_path)
    output_path = tmp_path / "must-not-exist.tsv"
    assert (
        main(
            [
                "--input",
                str(source_path),
                "--rows",
                str(rows_path),
                "--golden",
                str(golden_path),
                "--output",
                str(output_path),
                "--validate-only",
            ]
        )
        == 0
    )
    assert not output_path.exists()


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            [
                {"purpose": "measured", "order": 1, "row_id": 15003},
                {"purpose": "measured", "order": 2, "row_id": 15003},
            ],
            "duplicate row_id 15003",
        ),
        (
            [
                {"purpose": "measured", "order": 1, "row_id": 15003},
                {"purpose": "measured", "order": 1, "row_id": 15004},
            ],
            "duplicate measured order 1",
        ),
        (
            [
                {"purpose": "measured", "order": 1, "row_id": 15003},
                {"purpose": "measured", "order": 3, "row_id": 15004},
            ],
            "non-contiguous measured order",
        ),
        (
            [{"purpose": "other", "order": 1, "row_id": 15003}],
            "invalid purpose",
        ),
        (
            [{"purpose": "warmup", "order": 1, "row_id": 15001}],
            "contains no measured rows",
        ),
    ],
)
def test_workload_row_validation_rejects_invalid_specs(
    tmp_path: Path, rows: list[dict[str, object]], message: str
) -> None:
    rows_path = tmp_path / "rows.csv"
    write_csv(rows_path, ["purpose", "order", "row_id"], rows)
    with pytest.raises(InputValidationError, match=message):
        load_workload_rows(rows_path)


def test_workload_row_validation_requires_columns(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.csv"
    write_csv(rows_path, ["purpose", "row_id"], [{"purpose": "measured", "row_id": 15003}])
    with pytest.raises(InputValidationError, match="missing required columns: order"):
        load_workload_rows(rows_path)


def test_resolution_rejects_missing_source_rows(tmp_path: Path) -> None:
    source_path, _, golden_path = make_files(tmp_path)
    rows = [WorkloadRow("measured", 1, 15999)]
    with pytest.raises(InputValidationError, match="missing from the source"):
        resolve_measured_tickets(
            load_source(source_path), rows, load_golden_ids(golden_path)
        )


def test_resolution_rejects_any_golden_overlap(tmp_path: Path) -> None:
    source_path, _, golden_path = make_files(tmp_path)
    rows = [WorkloadRow("measured", 1, 15000)]
    with pytest.raises(InputValidationError, match="overlaps the golden set"):
        resolve_measured_tickets(
            load_source(source_path), rows, load_golden_ids(golden_path)
        )


def test_serialised_json_contains_no_raw_line_breaks_or_extra_tabs(tmp_path: Path) -> None:
    source_path, rows_path, golden_path = make_files(tmp_path)
    measured = resolve_measured_tickets(
        load_source(source_path),
        load_workload_rows(rows_path),
        load_golden_ids(golden_path),
    )
    lines = serialise_feeder_lines(measured)
    assert all(line.count("\t") == 1 for line in lines)
    assert all("\n" not in line and "\r" not in line for line in lines)
