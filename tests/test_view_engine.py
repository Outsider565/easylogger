from __future__ import annotations

import pytest

from easylogger.models import ViewConfig
from easylogger.view_engine import apply_view


def test_apply_view_supports_pin_sort_hidden_alias_and_computed() -> None:
    records = [
        {"path": "run/c.scaler.json", "step": "100", "loss": 0.9, "note": "late"},
        {"path": "run/a.scaler.json", "step": "10", "loss": 0.3, "note": "alpha"},
        {"path": "run/b.scaler.json", "step": "2", "loss": 0.4},
    ]

    view = ViewConfig.model_validate(
        {
            "name": "demo",
            "pattern": r".*",
            "columns": {
                "order": ["path", "score", "loss", "step", "note"],
                "hidden": ["note"],
                "alias": {"loss": "Loss"},
                "computed": [
                    {"name": "score", "expr": 'row["loss"] * float(row["step"])'},
                    {"name": "uses_hidden", "expr": 'row["note"] if row["note"] else "missing"'},
                ],
            },
            "rows": {
                "pinned_ids": ["run/c.scaler.json"],
                "sort": {"by": "step", "direction": "asc"},
            },
        }
    )

    table = apply_view(records, view)

    assert table.visible_columns == ["path", "score", "loss", "step", "uses_hidden"]
    assert [row["path"] for row in table.rows] == [
        "run/c.scaler.json",
        "run/b.scaler.json",
        "run/a.scaler.json",
    ]

    rows = {row["path"]: row for row in table.rows}
    assert rows["run/b.scaler.json"]["note"] is None
    assert rows["run/b.scaler.json"]["uses_hidden"] == "missing"
    assert rows["run/a.scaler.json"]["score"] == 3.0


def test_computed_expression_failure_becomes_error_string() -> None:
    records = [{"path": "run/a.scaler.json", "loss": 0.1}]
    view = ViewConfig.model_validate(
        {
            "name": "demo",
            "pattern": ".*",
            "columns": {
                "computed": [{"name": "bad", "expr": 'row["missing"] + 1'}],
            },
            "rows": {"pinned_ids": [], "sort": {"by": None, "direction": "asc"}},
        }
    )

    table = apply_view(records, view)
    assert table.rows[0]["bad"].startswith("ERROR:")


def test_column_format_uses_python_template_and_reports_errors() -> None:
    records = [
        {"path": "run/a.scaler.json", "step": 7, "loss": 0.12345},
        {"path": "run/b.scaler.json", "step": 11, "loss": 0.4},
    ]
    view = ViewConfig.model_validate(
        {
            "name": "demo",
            "pattern": ".*",
            "columns": {
                "format": {
                    "step": "{d:03}",
                    "loss": "{d:.2f}",
                    "path": "{d:invalid}",
                },
            },
            "rows": {"pinned_ids": [], "sort": {"by": "step", "direction": "asc"}},
        }
    )

    table = apply_view(records, view)
    assert table.rows[0]["step"] == "007"
    assert table.rows[0]["loss"] == "0.12"
    assert table.rows[0]["path"].startswith("FORMAT_ERROR:")


@pytest.mark.parametrize(
    ("template", "value", "expected"),
    [
        ("{d:04}", 9, "0009"),
        ("{d:.1f}", 12.34, "12.3"),
        ("{d:.1%}", 0.256, "25.6%"),
        ("{d:,}", 12000, "12,000"),
    ],
)
def test_column_format_supports_multiple_template_types(
    template: str, value: int | float, expected: str
) -> None:
    records = [{"path": "run/a.scaler.json", "value": value}]
    view = ViewConfig.model_validate(
        {
            "name": "demo",
            "pattern": ".*",
            "columns": {"format": {"value": template}},
            "rows": {"pinned_ids": [], "sort": {"by": None, "direction": "asc"}},
        }
    )

    table = apply_view(records, view)
    assert table.rows[0]["value"] == expected


def test_column_format_does_not_affect_sorting_order() -> None:
    records = [
        {"path": "run/a.scaler.json", "step": 12},
        {"path": "run/b.scaler.json", "step": 2},
        {"path": "run/c.scaler.json", "step": 100},
    ]
    view = ViewConfig.model_validate(
        {
            "name": "demo",
            "pattern": ".*",
            "columns": {"format": {"step": "{d:04}"}},
            "rows": {"pinned_ids": [], "sort": {"by": "step", "direction": "asc"}},
        }
    )

    table = apply_view(records, view)
    assert [row["path"] for row in table.rows] == [
        "run/b.scaler.json",
        "run/a.scaler.json",
        "run/c.scaler.json",
    ]
    assert [row["step"] for row in table.rows] == ["0002", "0012", "0100"]


def test_column_format_coerces_numeric_like_strings() -> None:
    records = [{"path": "run/a.scaler.json", "latency_ms": "12.7"}]
    view = ViewConfig.model_validate(
        {
            "name": "demo",
            "pattern": ".*",
            "columns": {"format": {"latency_ms": "{d:.1f}ms"}},
            "rows": {"pinned_ids": [], "sort": {"by": None, "direction": "asc"}},
        }
    )

    table = apply_view(records, view)
    assert table.rows[0]["latency_ms"] == "12.7ms"
