from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from easylogger.cli import app
from easylogger.view_store import default_view, save_view

runner = CliRunner()


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_create_command_creates_view_and_scans(tmp_path: Path) -> None:
    write(tmp_path / "logs" / "a.scaler.json", '{"step": 1, "loss": 0.2}')

    result = runner.invoke(
        app,
        [
            "create",
            str(tmp_path),
            "--pattern",
            r".*\.scaler\.json$",
            "--name",
            "demo",
        ],
    )

    assert result.exit_code == 0
    assert (tmp_path / ".easylogger" / "views" / "demo.json").exists()
    assert "Created view 'demo'" in result.output
    assert "matched_files=1" in result.output


def test_view_command_reports_missing_view(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["view", str(tmp_path), "--name", "missing", "--no-open-browser"],
    )

    assert result.exit_code == 1
    assert "View 'missing' was not found" in result.output
    assert "easylogger create" in result.output


def test_view_command_runs_uvicorn(tmp_path: Path, monkeypatch) -> None:
    save_view(tmp_path, default_view("demo", r".*"))

    called: dict[str, object] = {}

    def fake_run(web_app, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port
        called["app"] = web_app

    monkeypatch.setattr("easylogger.cli.uvicorn.run", fake_run)

    result = runner.invoke(
        app,
        [
            "view",
            str(tmp_path),
            "--name",
            "demo",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--no-open-browser",
        ],
    )

    assert result.exit_code == 0
    assert called["host"] == "0.0.0.0"
    assert called["port"] == 9000
