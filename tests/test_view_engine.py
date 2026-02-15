from __future__ import annotations

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
