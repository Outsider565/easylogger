from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .models import ScanRequest, ViewConfig
from .scanner import scan_records
from .view_engine import apply_view
from .view_store import ViewNotFoundError, load_view, save_view


def create_app(root: str | Path, view_name: str) -> FastAPI:
    root_path = Path(root).expanduser().resolve()
    web_root = Path(__file__).resolve().parent / "web"

    app = FastAPI(title="EasyLogger")

    @app.get("/api/meta")
    def get_meta() -> dict[str, str]:
        return {"root": str(root_path), "view_name": view_name}

    @app.get("/api/view", response_model=ViewConfig)
    def get_view() -> ViewConfig:
        try:
            return load_view(root_path, view_name)
        except ViewNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/view", response_model=ViewConfig)
    def post_view(view: ViewConfig) -> ViewConfig:
        if view.name != view_name:
            raise HTTPException(
                status_code=400,
                detail=f"View name mismatch. Expected '{view_name}', got '{view.name}'.",
            )
        save_view(root_path, view)
        return view

    @app.post("/api/scan")
    def post_scan(request: ScanRequest | None = None) -> dict:
        if request is not None and request.view is not None:
            active_view = request.view
        else:
            try:
                active_view = load_view(root_path, view_name)
            except ViewNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        scan_result = scan_records(root_path, active_view.pattern)
        table = apply_view(scan_result.records, active_view)

        return {
            "summary": scan_result.summary,
            "warnings": [
                {"path": warning.path, "message": warning.message}
                for warning in scan_result.warnings
            ],
            "columns": {
                "all": table.all_columns,
                "visible": table.visible_columns,
                "hidden": active_view.columns.hidden,
                "alias": active_view.columns.alias,
            },
            "rows": table.rows,
        }

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(web_root / "index.html")

    return app
