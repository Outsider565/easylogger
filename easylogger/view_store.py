from __future__ import annotations

import json
from pathlib import Path

from .models import ViewConfig


class ViewNotFoundError(FileNotFoundError):
    pass


def views_dir(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / ".easylogger" / "views"


def view_path(root: str | Path, name: str) -> Path:
    return views_dir(root) / f"{name}.json"


def default_view(name: str, pattern: str) -> ViewConfig:
    return ViewConfig.model_validate(
        {
            "name": name,
            "pattern": pattern,
            "columns": {
                "order": ["path"],
                "hidden": [],
                "alias": {},
                "computed": [],
            },
            "rows": {
                "pinned_ids": [],
                "sort": {
                    "by": None,
                    "direction": "asc",
                },
            },
        }
    )


def save_view(root: str | Path, view: ViewConfig) -> Path:
    target = view_path(root, view.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(view.model_dump_json(indent=2), encoding="utf-8")
    return target


def load_view(root: str | Path, name: str) -> ViewConfig:
    target = view_path(root, name)
    if not target.exists():
        root_path = Path(root).expanduser().resolve()
        msg = (
            f"View '{name}' does not exist under root '{root_path}'. "
            f"Create one with: easylogger create {root_path} --pattern \"...\" --name \"{name}\""
        )
        raise ViewNotFoundError(msg)

    try:
        raw = target.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read view file: {target} ({exc})") from exc

    return ViewConfig.model_validate(payload)
