from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path

import typer
import uvicorn

from .scanner import scan_records
from .view_store import ViewNotFoundError, default_view, load_view, save_view, view_path
from .web_api import create_app

app = typer.Typer(add_completion=False, help="EasyLogger CLI")


def _resolve_root(root: str) -> Path:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise typer.BadParameter(f"Root path does not exist or is not a directory: {root_path}")
    return root_path


@app.command()
def create(
    root: str = typer.Argument(..., help="Project root"),
    pattern: str = typer.Option(..., "--pattern", help="Regex used to match JSON log files"),
    name: str = typer.Option("default", "--name", help="View name"),
    warning_limit: int = typer.Option(20, "--warning-limit", min=0, help="Number of warnings to print"),
) -> None:
    """Create a view and run the first scan."""
    root_path = _resolve_root(root)

    try:
        view = default_view(name=name, pattern=pattern)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    saved_path = save_view(root_path, view)
    scan_result = scan_records(root_path, pattern)

    typer.echo(f"Created view '{name}' at {saved_path}")
    typer.echo(
        "Scan summary: "
        f"total_files={scan_result.summary['total_files']} "
        f"matched_files={scan_result.summary['matched_files']} "
        f"parsed_records={scan_result.summary['parsed_records']} "
        f"warnings={scan_result.summary['warning_count']}"
    )

    if scan_result.warnings:
        typer.echo("Warnings:")
        for warning in scan_result.warnings[:warning_limit]:
            typer.echo(f"- {warning.path}: {warning.message}")


@app.command()
def view(
    root: str = typer.Argument(..., help="Project root"),
    name: str = typer.Option("default", "--name", help="View name"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", min=1, max=65535, help="Bind port"),
    open_browser: bool = typer.Option(True, "--open-browser/--no-open-browser", help="Open browser automatically"),
) -> None:
    """Open a view in the local web server."""
    root_path = _resolve_root(root)

    try:
        load_view(root_path, name)
    except ViewNotFoundError:
        suggestion = f'easylogger create {root_path} --pattern "..." --name "{name}"'
        typer.echo(
            f"View '{name}' was not found under root '{root_path}'.\n"
            f"Create it with: {suggestion}",
            err=True,
        )
        raise typer.Exit(code=1)

    web_app = create_app(root_path, name)
    url = f"http://{host}:{port}"

    if open_browser:
        def _open_browser_later() -> None:
            time.sleep(0.3)
            webbrowser.open(url)

        threading.Thread(target=_open_browser_later, daemon=True).start()

    uvicorn.run(web_app, host=host, port=port)


if __name__ == "__main__":
    app()
