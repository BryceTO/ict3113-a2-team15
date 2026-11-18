"""Select a deterministic Assignment 2 speed-test workload.

The private Team 15 extract is the source of ticket narratives. All rows in the
frozen golden set are excluded because they are reserved for tuning and accuracy
measurement. The output records three disjoint purposes:

* ``warmup`` - three tickets used to warm the models before a run;
* ``calibration`` - three tickets used to obtain the top-model calibration time;
* ``measured`` - the ordered tickets supplied to the JMeter speed test.

Ticket length bands follow the existing Assignment 1 evidence: typical tickets
are within the interquartile range (p25-p75) and long tickets are at or above
p90. Percentiles are calculated from the complete Team 15 extract before golden
rows are excluded. Selection is deterministic; no random sampling is used.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


TEAM15_MIN_ROW = 15000
TEAM15_MAX_ROW = 15999


class InputValidationError(ValueError):
    """Raised when a source file cannot safely produce a workload."""


@dataclass(frozen=True)
class Ticket:
    row_id: int
    source_label: str
    narrative: str

    @property
    def narrative_chars(self) -> int:
        return len(self.narrative)


@dataclass(frozen=True)
class SelectedTicket:
    purpose: str
    order: int
    ticket: Ticket
    length_group: str


@dataclass(frozen=True)
class SelectionSummary:
    source_rows: int
    golden_rows: int
    eligible_rows: int
    typical_min_chars: float
    typical_max_chars: float
    long_min_chars: float


def _normalise_headers(fieldnames: Sequence[str] | None, path: Path) -> dict[str, str]:
    if not fieldnames:
        raise InputValidationError(f"{path} has no CSV header")

    mapping: dict[str, str] = {}
    for original in fieldnames:
        normalised = original.strip().lower()
        if normalised in mapping:
            raise InputValidationError(
                f"{path} has duplicate columns after case normalisation: {original!r}"
            )
        mapping[normalised] = original
    return mapping


def load_source(path: Path) -> list[Ticket]:
    """Load and validate the private Team 15 source extract."""

    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise InputValidationError(f"source file not found: {path}") from exc

    with handle:
        reader = csv.DictReader(handle)
        headers = _normalise_headers(reader.fieldnames, path)
        required = {"row", "source_label", "narrative"}
        missing = sorted(required - headers.keys())
        if missing:
            raise InputValidationError(
                f"{path} is missing required columns: {', '.join(missing)}"
            )

        tickets: list[Ticket] = []
        seen: set[int] = set()
        for csv_row_number, row in enumerate(reader, start=2):
            raw_id = (row.get(headers["row"]) or "").strip()
            try:
                row_id = int(raw_id)
            except ValueError as exc:
                raise InputValidationError(
                    f"{path}:{csv_row_number} has a non-numeric row ID: {raw_id!r}"
                ) from exc

            if not TEAM15_MIN_ROW <= row_id <= TEAM15_MAX_ROW:
                raise InputValidationError(
                    f"{path}:{csv_row_number} row {row_id} is outside Team 15's "
                    f"range {TEAM15_MIN_ROW}-{TEAM15_MAX_ROW}"
                )
            if row_id in seen:
                raise InputValidationError(f"{path} contains duplicate row ID {row_id}")
            seen.add(row_id)

            narrative = row.get(headers["narrative"]) or ""
            if not narrative.strip():
                raise InputValidationError(
                    f"{path}:{csv_row_number} row {row_id} has an empty narrative"
                )

            source_label = (row.get(headers["source_label"]) or "").strip()
            if not source_label:
                raise InputValidationError(
                    f"{path}:{csv_row_number} row {row_id} has an empty source_label"
                )

            tickets.append(
                Ticket(
                    row_id=row_id,
                    source_label=source_label,
                    narrative=narrative,
                )
            )

    if not tickets:
        raise InputValidationError(f"{path} contains no data rows")
    return tickets


def load_golden_ids(path: Path) -> set[int]:
    """Load and validate row IDs from the complete frozen golden set."""

    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise InputValidationError(f"golden-set file not found: {path}") from exc

    with handle:
        reader = csv.DictReader(handle)
        headers = _normalise_headers(reader.fieldnames, path)
        if "row" not in headers:
            raise InputValidationError(f"{path} is missing required column: ROW")

        golden_ids: set[int] = set()
        for csv_row_number, row in enumerate(reader, start=2):
            raw_id = (row.get(headers["row"]) or "").strip()
            try:
                row_id = int(raw_id)
            except ValueError as exc:
                raise InputValidationError(
                    f"{path}:{csv_row_number} has a non-numeric row ID: {raw_id!r}"
                ) from exc
            if row_id in golden_ids:
                raise InputValidationError(f"{path} contains duplicate row ID {row_id}")
            golden_ids.add(row_id)

    if not golden_ids:
        raise InputValidationError(f"{path} contains no golden-set rows")
    return golden_ids


def percentile(values: Iterable[int], proportion: float) -> float:
    """Return a linearly interpolated percentile using the (n-1) convention."""

    ordered = sorted(values)
    if not ordered:
        raise InputValidationError("cannot calculate a percentile of an empty sequence")
    if not 0.0 <= proportion <= 1.0:
        raise ValueError("percentile proportion must be between 0 and 1")
    if len(ordered) == 1:
        return float(ordered[0])

    position = (len(ordered) - 1) * proportion
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _select_evenly(candidates: Sequence[Ticket], count: int, group_name: str) -> list[Ticket]:
    if count < 0:
        raise InputValidationError(f"{group_name} count cannot be negative")
    if count == 0:
        return []
    if len(candidates) < count:
        raise InputValidationError(
            f"not enough {group_name} candidates: need {count}, found {len(candidates)}"
        )
    if count == 1:
        return [candidates[(len(candidates) - 1) // 2]]

    indices = [round(index * (len(candidates) - 1) / (count - 1)) for index in range(count)]
    if len(set(indices)) != count:
        raise InputValidationError(
            f"could not select {count} unique {group_name} candidates deterministically"
        )
    return [candidates[index] for index in indices]


def _without(candidates: Sequence[Ticket], excluded: Iterable[Ticket]) -> list[Ticket]:
    excluded_ids = {ticket.row_id for ticket in excluded}
    return [ticket for ticket in candidates if ticket.row_id not in excluded_ids]


def select_workload(
    source: Sequence[Ticket],
    golden_ids: set[int],
    *,
    measured_count: int,
    long_count: int,
    warmup_count: int = 3,
    calibration_count: int = 3,
) -> tuple[list[SelectedTicket], SelectionSummary]:
    """Select disjoint warm-up, calibration, and measured ticket groups."""

    if measured_count <= 0:
        raise InputValidationError("measured_count must be greater than zero")
    if long_count < 0 or long_count > measured_count:
        raise InputValidationError("long_count must be between zero and measured_count")
    if warmup_count <= 0 or calibration_count <= 0:
        raise InputValidationError("warmup_count and calibration_count must be positive")

    source_by_id = {ticket.row_id: ticket for ticket in source}
    missing_golden = sorted(golden_ids - source_by_id.keys())
    if missing_golden:
        preview = ", ".join(str(row_id) for row_id in missing_golden[:10])
        suffix = "..." if len(missing_golden) > 10 else ""
        raise InputValidationError(
            f"{len(missing_golden)} golden row(s) are missing from the source: {preview}{suffix}"
        )

    lengths = [ticket.narrative_chars for ticket in source]
    typical_min = percentile(lengths, 0.25)
    typical_max = percentile(lengths, 0.75)
    long_min = percentile(lengths, 0.90)

    eligible = [ticket for ticket in source if ticket.row_id not in golden_ids]
    typical_candidates = sorted(
        (
            ticket
            for ticket in eligible
            if typical_min <= ticket.narrative_chars <= typical_max
        ),
        key=lambda ticket: (ticket.narrative_chars, ticket.row_id),
    )
    long_candidates = sorted(
        (ticket for ticket in eligible if ticket.narrative_chars >= long_min),
        key=lambda ticket: (ticket.narrative_chars, ticket.row_id),
    )

    warmups = _select_evenly(typical_candidates, warmup_count, "warm-up")
    remaining_typical = _without(typical_candidates, warmups)
    calibrations = _select_evenly(
        remaining_typical, calibration_count, "calibration"
    )
    remaining_typical = _without(remaining_typical, calibrations)

    measured_typical_count = measured_count - long_count
    measured_typical = _select_evenly(
        remaining_typical, measured_typical_count, "measured typical"
    )
    measured_long = _select_evenly(long_candidates, long_count, "measured long")

    all_selected_ids = [
        ticket.row_id
        for ticket in (*warmups, *calibrations, *measured_typical, *measured_long)
    ]
    if len(all_selected_ids) != len(set(all_selected_ids)):
        raise InputValidationError("selection groups overlap; no workload was written")
    golden_overlap = sorted(set(all_selected_ids) & golden_ids)
    if golden_overlap:
        raise InputValidationError(
            f"selection overlaps the golden set: {', '.join(map(str, golden_overlap))}"
        )

    selected: list[SelectedTicket] = []
    for order, ticket in enumerate(sorted(warmups, key=lambda item: item.row_id), start=1):
        selected.append(SelectedTicket("warmup", order, ticket, "typical"))
    for order, ticket in enumerate(
        sorted(calibrations, key=lambda item: item.row_id), start=1
    ):
        selected.append(SelectedTicket("calibration", order, ticket, "typical"))

    measured_groups = [
        *(SelectedTicket("measured", 0, ticket, "typical") for ticket in measured_typical),
        *(SelectedTicket("measured", 0, ticket, "long") for ticket in measured_long),
    ]
    measured_groups.sort(key=lambda item: item.ticket.row_id)
    selected.extend(
        SelectedTicket(item.purpose, order, item.ticket, item.length_group)
        for order, item in enumerate(measured_groups, start=1)
    )

    summary = SelectionSummary(
        source_rows=len(source),
        golden_rows=len(golden_ids),
        eligible_rows=len(eligible),
        typical_min_chars=typical_min,
        typical_max_chars=typical_max,
        long_min_chars=long_min,
    )
    return selected, summary


def write_selection(path: Path, selected: Sequence[SelectedTicket]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "purpose",
                "order",
                "row_id",
                "source_label",
                "narrative_chars",
                "length_group",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for item in selected:
            writer.writerow(
                {
                    "purpose": item.purpose,
                    "order": item.order,
                    "row_id": item.ticket.row_id,
                    "source_label": item.ticket.source_label,
                    "narrative_chars": item.ticket.narrative_chars,
                    "length_group": item.length_group,
                }
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Select deterministic warm-up, calibration, and measured A2 tickets "
            "while excluding the complete golden set."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docsbryan/team15_rows.csv"),
        help="private Team 15 source CSV (default: docsbryan/team15_rows.csv)",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path("golden_set/golden_set.csv"),
        help="complete frozen golden-set CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("jmeter/a2_workload_rows.csv"),
        help="ordered workload row-list CSV",
    )
    parser.add_argument(
        "--measured-count",
        type=int,
        default=30,
        help="number of measured speed-test tickets (provisional default: 30)",
    )
    parser.add_argument(
        "--long-count",
        type=int,
        default=6,
        help="number of measured tickets drawn from the p90+ length band (default: 6)",
    )
    parser.add_argument("--warmup-count", type=int, default=3)
    parser.add_argument("--calibration-count", type=int, default=3)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate inputs and selection feasibility without writing an output file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = load_source(args.input)
        golden_ids = load_golden_ids(args.golden)
        selected, summary = select_workload(
            source,
            golden_ids,
            measured_count=args.measured_count,
            long_count=args.long_count,
            warmup_count=args.warmup_count,
            calibration_count=args.calibration_count,
        )
        if not args.validate_only:
            write_selection(args.output, selected)
    except InputValidationError as exc:
        raise SystemExit(f"workload selection failed: {exc}") from exc

    measured = [item for item in selected if item.purpose == "measured"]
    measured_long = [item for item in measured if item.length_group == "long"]
    action = "validated" if args.validate_only else f"wrote {args.output}"
    print(
        f"{action}: source={summary.source_rows}, golden={summary.golden_rows}, "
        f"eligible={summary.eligible_rows}, measured={len(measured)}, "
        f"long={len(measured_long)}, warmup={args.warmup_count}, "
        f"calibration={args.calibration_count}"
    )
    print(
        "length bands (characters): "
        f"typical={summary.typical_min_chars:.2f}-{summary.typical_max_chars:.2f}, "
        f"long>={summary.long_min_chars:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
