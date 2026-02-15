from __future__ import annotations

from pathlib import Path

from easylogger.scanner import scan_records


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scan_records_handles_warnings_and_ignored_dirs(tmp_path: Path) -> None:
    write(tmp_path / "logs" / "ok.scaler.json", '{"step": 1, "loss": 0.5, "success": true}')
    write(tmp_path / "logs" / "nested.scaler.json", '{"step": 2, "meta": {"epoch": 1}}')
    write(tmp_path / "logs" / "bad.scaler.json", '{"step": 3')
    write(tmp_path / "logs" / "skip.txt", "not-json")
    write(tmp_path / ".git" / "ignored.scaler.json", '{"step": 999}')

    result = scan_records(tmp_path, r".*\.scaler\.json$")

    assert result.summary["matched_files"] == 3
    assert result.summary["parsed_records"] == 2
    assert result.summary["warning_count"] == 2

    by_path = {row["path"]: row for row in result.records}
    assert "logs/ok.scaler.json" in by_path
    assert by_path["logs/nested.scaler.json"]["meta"] is None

    warning_paths = [warning.path for warning in result.warnings]
    assert "logs/bad.scaler.json" in warning_paths
    assert all(".git" not in warning.path for warning in result.warnings)


def test_scan_records_rejects_non_directory_root(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")

    try:
        scan_records(file_path, r".*")
    except ValueError as exc:
        assert "not a directory" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-directory root")
