from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_IGNORED_DIRS = {".git", "node_modules", ".venv"}


@dataclass(slots=True)
class ScanWarning:
    path: str
    message: str


@dataclass(slots=True)
class ScanResult:
    records: list[dict[str, Any]]
    warnings: list[ScanWarning]
    summary: dict[str, int]


def _is_supported_scalar(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float, str)):
        return True
    return False


def scan_records(root: str | Path, pattern: str, ignored_dirs: set[str] | None = None) -> ScanResult:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Project root does not exist or is not a directory: {root_path}")

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern: {exc}") from exc

    ignored = ignored_dirs if ignored_dirs is not None else DEFAULT_IGNORED_DIRS

    records: list[dict[str, Any]] = []
    warnings: list[ScanWarning] = []
    total_files = 0
    matched_files = 0

    for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in ignored]

        for filename in filenames:
            total_files += 1
            file_path = Path(dirpath) / filename
            rel_path = file_path.relative_to(root_path).as_posix()
            if not regex.search(rel_path):
                continue

            matched_files += 1

            try:
                raw = file_path.read_text(encoding="utf-8")
                parsed = json.loads(raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                warnings.append(
                    ScanWarning(path=rel_path, message=f"Failed to parse JSON file: {exc}")
                )
                continue

            if not isinstance(parsed, dict):
                warnings.append(
                    ScanWarning(path=rel_path, message="JSON root is not an object; file skipped.")
                )
                continue

            row: dict[str, Any] = {"path": rel_path}
            for key, value in parsed.items():
                key_name = str(key)
                if _is_supported_scalar(value):
                    row[key_name] = value
                    continue

                row[key_name] = None
                warnings.append(
                    ScanWarning(
                        path=rel_path,
                        message=f"Field '{key_name}' is not a scalar (array/object); coerced to null.",
                    )
                )

            records.append(row)

    summary = {
        "total_files": total_files,
        "matched_files": matched_files,
        "parsed_records": len(records),
        "warning_count": len(warnings),
    }

    return ScanResult(records=records, warnings=warnings, summary=summary)
