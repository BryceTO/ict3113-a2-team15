"""Build the Assignment 2 JMeter feeder from the frozen workload row list.

The committed row list defines which tickets are measured and their exact order.
The private Team 15 extract supplies the narratives. Warm-up and calibration rows
remain in the row list for auditability but are not written to the measured feeder.

Each output line has this format::

    <row_id> TAB <complete JSON request body>

``json.dumps`` escapes quotes, newlines, tabs, and non-ASCII characters. Therefore
each request remains on one physical TSV line and the only raw tab is the delimiter.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from scripts.select_a2_workload import (
        InputValidationError,
        TEAM15_MAX_ROW,
        TEAM15_MIN_ROW,
        Ticket,
        load_golden_ids,
        load_source,
    )
except ModuleNotFoundError:  # Supports: python scripts/make_feeder.py
    from select_a2_workload import (  # type: ignore[no-redef]
        InputValidationError,
        TEAM15_MAX_ROW,
        TEAM15_MIN_ROW,
        Ticket,
        load_golden_ids,
        load_source,
    )


ALLOWED_PURPOSES = {"warmup", "calibration", "measured"}


@dataclass(frozen=True)
class WorkloadRow:
    purpose: str
    order: int
    row_id: int


def _normalise_headers(fieldnames: Sequence[str] | None, path: Path) -> dict[str, str]:
    if not fieldnames:
        raise InputValidationError(f"{path} has no CSV header")

    headers: dict[str, str] = {}
    for original in fieldnames:
        normalised = original.strip().lower()
        if normalised in headers:
            raise InputValidationError(
                f"{path} has duplicate columns after case normalisation: {original!r}"
            )
        headers[normalised] = original
    return headers


def load_workload_rows(path: Path) -> list[WorkloadRow]:
    """Load and validate the ordered workload specification."""

    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise InputValidationError(f"workload row-list file not found: {path}") from exc

    with handle:
        reader = csv.DictReader(handle)
        headers = _normalise_headers(reader.fieldnames, path)
        required = {"purpose", "order", "row_id"}
        missing = sorted(required - headers.keys())
        if missing:
            raise InputValidationError(
                f"{path} is missing required columns: {', '.join(missing)}"
            )

        workload_rows: list[WorkloadRow] = []
        seen_ids: set[int] = set()
        seen_orders: set[tuple[str, int]] = set()

        for csv_row_number, row in enumerate(reader, start=2):
            purpose = (row.get(headers["purpose"]) or "").strip().lower()
            if purpose not in ALLOWED_PURPOSES:
                raise InputValidationError(
                    f"{path}:{csv_row_number} has invalid purpose {purpose!r}; "
                    f"expected one of {', '.join(sorted(ALLOWED_PURPOSES))}"
                )

            raw_order = (row.get(headers["order"]) or "").strip()
            try:
                order = int(raw_order)
            except ValueError as exc:
                raise InputValidationError(
                    f"{path}:{csv_row_number} has non-numeric order {raw_order!r}"
                ) from exc
            if order <= 0:
                raise InputValidationError(
                    f"{path}:{csv_row_number} order must be positive, found {order}"
                )

            raw_id = (row.get(headers["row_id"]) or "").strip()
            try:
                row_id = int(raw_id)
            except ValueError as exc:
                raise InputValidationError(
                    f"{path}:{csv_row_number} has non-numeric row_id {raw_id!r}"
                ) from exc
            if not TEAM15_MIN_ROW <= row_id <= TEAM15_MAX_ROW:
                raise InputValidationError(
                    f"{path}:{csv_row_number} row {row_id} is outside Team 15's "
                    f"range {TEAM15_MIN_ROW}-{TEAM15_MAX_ROW}"
                )
            if row_id in seen_ids:
                raise InputValidationError(f"{path} contains duplicate row_id {row_id}")
            seen_ids.add(row_id)

            order_key = (purpose, order)
            if order_key in seen_orders:
                raise InputValidationError(
                    f"{path} contains duplicate {purpose} order {order}"
                )
            seen_orders.add(order_key)
            workload_rows.append(WorkloadRow(purpose, order, row_id))

    if not workload_rows:
        raise InputValidationError(f"{path} contains no workload rows")

    for purpose in sorted(ALLOWED_PURPOSES):
        orders = sorted(row.order for row in workload_rows if row.purpose == purpose)
        if not orders:
            if purpose == "measured":
                raise InputValidationError(f"{path} contains no measured rows")
            continue
        expected = list(range(1, len(orders) + 1))
        if orders != expected:
            raise InputValidationError(
                f"{path} has non-contiguous {purpose} order values: "
                f"expected {expected}, found {orders}"
            )

    return workload_rows


def resolve_measured_tickets(
    source: Sequence[Ticket],
    workload_rows: Sequence[WorkloadRow],
    golden_ids: set[int],
) -> list[Ticket]:
    """Resolve measured rows to source tickets after cross-file validation."""

    requested_ids = {row.row_id for row in workload_rows}
    golden_overlap = sorted(requested_ids & golden_ids)
    if golden_overlap:
        preview = ", ".join(str(row_id) for row_id in golden_overlap[:10])
        suffix = "..." if len(golden_overlap) > 10 else ""
        raise InputValidationError(
            f"workload row list overlaps the golden set: {preview}{suffix}"
        )

    source_by_id = {ticket.row_id: ticket for ticket in source}
    missing_ids = sorted(requested_ids - source_by_id.keys())
    if missing_ids:
        preview = ", ".join(str(row_id) for row_id in missing_ids[:10])
        suffix = "..." if len(missing_ids) > 10 else ""
        raise InputValidationError(
            f"{len(missing_ids)} workload row(s) are missing from the source: "
            f"{preview}{suffix}"
        )

    measured_rows = sorted(
        (row for row in workload_rows if row.purpose == "measured"),
        key=lambda row: row.order,
    )
    measured = [source_by_id[row.row_id] for row in measured_rows]
    if len(measured) != len(measured_rows):
        raise InputValidationError("resolved measured-ticket count does not match row list")
    return measured


def serialise_feeder_lines(tickets: Sequence[Ticket]) -> list[str]:
    """Return one safe, ASCII-only TSV line per ticket."""

    lines: list[str] = []
    for ticket in tickets:
        body = json.dumps(
            {"narrative": ticket.narrative, "row_id": ticket.row_id},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        if "\t" in body or "\n" in body or "\r" in body:
            raise InputValidationError(
                f"row {ticket.row_id} produced unsafe raw whitespace in JSON"
            )
        lines.append(f"{ticket.row_id}\t{body}")
    return lines


def write_feeder(path: Path, lines: Sequence[str]) -> None:
    if not lines:
        raise InputValidationError("refusing to write an empty feeder")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")

    written_lines = path.read_text(encoding="ascii").splitlines()
    if len(written_lines) != len(lines):
        raise InputValidationError(
            f"feeder output-count mismatch: expected {len(lines)}, "
            f"wrote {len(written_lines)}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the measured JMeter feeder from the committed A2 workload "
            "row list and private Team 15 extract."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docsbryan/team15_rows.csv"),
        help="private Team 15 source CSV (default: docsbryan/team15_rows.csv)",
    )
    parser.add_argument(
        "--rows",
        type=Path,
        default=Path("jmeter/a2_workload_rows.csv"),
        help="committed A2 workload row-list CSV",
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
        default=Path("jmeter/feeder.tsv"),
        help="generated JMeter feeder TSV",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and resolve all rows without writing the feeder",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = load_source(args.input)
        workload_rows = load_workload_rows(args.rows)
        golden_ids = load_golden_ids(args.golden)
        measured = resolve_measured_tickets(source, workload_rows, golden_ids)
        lines = serialise_feeder_lines(measured)
        if not args.validate_only:
            write_feeder(args.output, lines)
    except InputValidationError as exc:
        raise SystemExit(f"feeder generation failed: {exc}") from exc

    action = "validated" if args.validate_only else f"wrote {args.output}"
    print(
        f"{action}: measured={len(measured)}, source={len(source)}, "
        f"row_list={len(workload_rows)}, golden={len(golden_ids)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
