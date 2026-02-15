from __future__ import annotations

from pathlib import Path

import pytest

from easylogger.models import ViewConfig
from easylogger.view_store import ViewNotFoundError, default_view, load_view, save_view, view_path


def test_save_and_load_view_roundtrip(tmp_path: Path) -> None:
    view = default_view(name="demo", pattern=r".*\\.scaler\\.json$")
    path = save_view(tmp_path, view)

    assert path == view_path(tmp_path, "demo")
    assert path.exists()

    loaded = load_view(tmp_path, "demo")
    assert loaded.model_dump() == view.model_dump()


def test_load_missing_view_has_actionable_message(tmp_path: Path) -> None:
    with pytest.raises(ViewNotFoundError) as exc_info:
        load_view(tmp_path, "missing")

    message = str(exc_info.value)
    assert str(tmp_path.resolve()) in message
    assert "missing" in message
    assert "easylogger create" in message


def test_alias_names_must_be_unique() -> None:
    with pytest.raises(ValueError):
        ViewConfig.model_validate(
            {
                "name": "demo",
                "pattern": r".*",
                "columns": {
                    "order": ["path"],
                    "hidden": [],
                    "alias": {"a": "x", "b": "x"},
                    "computed": [],
                },
                "rows": {"pinned_ids": [], "sort": {"by": None, "direction": "asc"}},
            }
        )
