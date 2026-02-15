from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .models import ViewConfig

_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


@dataclass(slots=True)
class TableResult:
    all_columns: list[str]
    visible_columns: list[str]
    rows: list[dict[str, Any]]


def apply_view(records: Sequence[dict[str, Any]], view: ViewConfig) -> TableResult:
    rows, all_columns = _normalize_rows(records)
    _apply_computed_columns(rows, all_columns, view)

    ordered_columns = _ordered_columns(view.columns.order, all_columns)
    hidden_set = set(view.columns.hidden)
    visible_columns = [column for column in ordered_columns if column not in hidden_set]

    sorted_rows = _sort_rows(rows, view)
    _apply_display_formats(sorted_rows, view)
    return TableResult(all_columns=ordered_columns, visible_columns=visible_columns, rows=sorted_rows)


def _normalize_rows(records: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    discovered_columns: list[str] = ["path"]
    seen = {"path"}
    normalized_rows: list[dict[str, Any]] = []

    for record in records:
        copied = dict(record)
        copied.setdefault("path", None)
        normalized_rows.append(copied)

        for key in copied.keys():
            if key in seen:
                continue
            seen.add(key)
            discovered_columns.append(key)

    for row in normalized_rows:
        for column in discovered_columns:
            row.setdefault(column, None)

    return normalized_rows, discovered_columns


def _apply_computed_columns(rows: list[dict[str, Any]], all_columns: list[str], view: ViewConfig) -> None:
    builtins_scope = {"__builtins__": __builtins__}

    for computed in view.columns.computed:
        if computed.name not in all_columns:
            all_columns.append(computed.name)

        for row in rows:
            try:
                value = eval(computed.expr, builtins_scope, {"row": row})  # noqa: S307
            except Exception as exc:
                value = f"ERROR: {exc}"
            row[computed.name] = value


def _ordered_columns(configured_order: Iterable[str], all_columns: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    for column in configured_order:
        if column in all_columns and column not in seen:
            ordered.append(column)
            seen.add(column)

    for column in all_columns:
        if column in seen:
            continue
        ordered.append(column)
        seen.add(column)

    return ordered


def _sort_rows(rows: list[dict[str, Any]], view: ViewConfig) -> list[dict[str, Any]]:
    pinned_ids = view.rows.pinned_ids
    pinned_index = {pinned_id: index for index, pinned_id in enumerate(pinned_ids)}

    pinned_rows: list[dict[str, Any]] = []
    other_rows: list[dict[str, Any]] = []

    for row in rows:
        path = row.get("path")
        if isinstance(path, str) and path in pinned_index:
            pinned_rows.append(row)
        else:
            other_rows.append(row)

    pinned_rows.sort(key=lambda row: pinned_index[row["path"]])

    sort_field = view.rows.sort.by
    if sort_field:
        reverse = view.rows.sort.direction == "desc"
        other_rows.sort(key=lambda row: _sortable_value(row.get(sort_field)), reverse=reverse)

    return pinned_rows + other_rows


def _apply_display_formats(rows: list[dict[str, Any]], view: ViewConfig) -> None:
    for column_name, template in view.columns.format.items():
        if not isinstance(template, str) or not template:
            continue
        for row in rows:
            if column_name not in row:
                continue
            value = row[column_name]
            if value is None:
                continue
            try:
                row[column_name] = template.format(d=_coerce_format_value(value))
            except Exception as exc:
                row[column_name] = f"FORMAT_ERROR: {exc}"


def _coerce_format_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if _NUMERIC_RE.match(stripped):
            if "." not in stripped:
                try:
                    return int(stripped)
                except ValueError:
                    return float(stripped)
            return float(stripped)
    return value


def _sortable_value(value: Any) -> tuple[int, Any]:
    numeric = _to_float(value)
    if numeric is not None and not math.isnan(numeric):
        return (0, numeric)

    if value is None:
        return (2, "")

    return (1, str(value))


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if _NUMERIC_RE.match(stripped):
            return float(stripped)
    return None
