from __future__ import annotations

import json
from pathlib import Path

from .models import ViewConfig


class ViewNotFoundError(FileNotFoundError):
    pass


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("View name cannot be empty.")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("View name cannot include path separators.")
    return normalized


def views_dir(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / ".easylogger" / "views"


def view_path(root: str | Path, name: str) -> Path:
    return views_dir(root) / f"{_normalize_name(name)}.json"


def list_views(root: str | Path) -> list[str]:
    base = views_dir(root)
    if not base.exists():
        return []
    return sorted(path.stem for path in base.glob("*.json"))


def default_view(name: str, pattern: str) -> ViewConfig:
    return ViewConfig.model_validate(
        {
            "name": name,
            "pattern": pattern,
            "columns": {
                "order": ["path"],
                "hidden": [],
                "alias": {},
                "format": {},
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


def create_view_from(root: str | Path, name: str, from_name: str) -> ViewConfig:
    new_name = _normalize_name(name)
    source_name = _normalize_name(from_name)
    if view_path(root, new_name).exists():
        raise ValueError(f"View '{new_name}' already exists.")

    source = load_view(root, source_name)
    copied = source.model_copy(deep=True)
    copied.name = new_name
    save_view(root, copied)
    return copied


def rename_view(root: str | Path, old_name: str, new_name: str) -> ViewConfig:
    old_normalized = _normalize_name(old_name)
    new_normalized = _normalize_name(new_name)
    if old_normalized == new_normalized:
        return load_view(root, old_normalized)

    old_path = view_path(root, old_normalized)
    if not old_path.exists():
        raise ViewNotFoundError(f"View '{old_normalized}' does not exist.")

    new_path = view_path(root, new_normalized)
    if new_path.exists():
        raise ValueError(f"View '{new_normalized}' already exists.")

    view = load_view(root, old_normalized)
    view.name = new_normalized
    save_view(root, view)
    old_path.unlink(missing_ok=True)
    return view
