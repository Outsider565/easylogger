from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import CreateViewRequest, RenameViewRequest, ScanRequest, ViewConfig
from .scanner import scan_records
from .view_engine import apply_view
from .view_store import (
    ViewNotFoundError,
    create_view_from,
    list_views,
    load_view,
    rename_view,
    save_view,
)


def create_app(root: str | Path, view_name: str) -> FastAPI:
    root_path = Path(root).expanduser().resolve()
    web_root = Path(__file__).resolve().parent / "web"

    app = FastAPI(title="EasyLogger")
    app.mount("/static", StaticFiles(directory=web_root), name="static")

    active_view_name = view_name
    cached_records: dict[str, list[dict]] = {}
    cached_scan_meta: dict[str, tuple[dict, list[dict]]] = {}

    def _load_view_or_404(name: str) -> ViewConfig:
        try:
            return load_view(root_path, name)
        except ViewNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _resolve_view_and_name(request: ScanRequest | None) -> tuple[str, ViewConfig]:
        nonlocal active_view_name

        if request is not None and request.view is not None:
            resolved_name = request.view.name
            if request.view_name and request.view_name != resolved_name:
                raise HTTPException(
                    status_code=400,
                    detail=f"View name mismatch: payload name is '{resolved_name}', request name is '{request.view_name}'.",
                )
            active_view_name = resolved_name
            return resolved_name, request.view

        target_name = request.view_name if request and request.view_name else active_view_name
        view = _load_view_or_404(target_name)
        active_view_name = target_name
        return target_name, view

    def _response_from_records(
        records: list[dict],
        active_view: ViewConfig,
        summary: dict,
        warnings: list[dict],
    ) -> dict:
        table = apply_view(records, active_view)
        return {
            "summary": summary,
            "warnings": warnings,
            "columns": {
                "all": table.all_columns,
                "visible": table.visible_columns,
                "hidden": active_view.columns.hidden,
                "alias": active_view.columns.alias,
            },
            "rows": table.rows,
        }

    @app.get("/api/meta")
    def get_meta() -> dict[str, str]:
        return {"root": str(root_path), "view_name": active_view_name}

    @app.get("/api/views")
    def get_views() -> dict[str, object]:
        names = list_views(root_path)
        return {"views": names, "active": active_view_name}

    # Backward-compatible endpoint for current active view.
    @app.get("/api/view", response_model=ViewConfig)
    def get_view() -> ViewConfig:
        return _load_view_or_404(active_view_name)

    # Backward-compatible endpoint for current active view.
    @app.post("/api/view", response_model=ViewConfig)
    def post_view(view: ViewConfig) -> ViewConfig:
        nonlocal active_view_name

        if view.name != active_view_name:
            raise HTTPException(
                status_code=400,
                detail=f"View name mismatch. Expected '{active_view_name}', got '{view.name}'.",
            )
        save_view(root_path, view)
        active_view_name = view.name
        return view

    @app.post("/api/views/create", response_model=ViewConfig)
    def post_create_view(request: CreateViewRequest) -> ViewConfig:
        try:
            return create_view_from(root_path, request.name, request.from_name)
        except ViewNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/views/rename", response_model=ViewConfig)
    def post_rename_view(request: RenameViewRequest) -> ViewConfig:
        nonlocal active_view_name

        try:
            renamed = rename_view(root_path, request.old_name, request.new_name)
        except ViewNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if active_view_name == request.old_name:
            active_view_name = request.new_name

        if request.old_name in cached_records:
            cached_records[request.new_name] = cached_records.pop(request.old_name)
        if request.old_name in cached_scan_meta:
            cached_scan_meta[request.new_name] = cached_scan_meta.pop(request.old_name)

        return renamed

    @app.get("/api/views/{name}", response_model=ViewConfig)
    def get_view_by_name(name: str) -> ViewConfig:
        nonlocal active_view_name
        active_view_name = name
        return _load_view_or_404(name)

    @app.post("/api/views/{name}", response_model=ViewConfig)
    def save_view_by_name(name: str, view: ViewConfig) -> ViewConfig:
        nonlocal active_view_name
        if view.name != name:
            raise HTTPException(
                status_code=400,
                detail=f"View name mismatch. URL name is '{name}', payload name is '{view.name}'.",
            )
        save_view(root_path, view)
        active_view_name = name
        return view

    @app.post("/api/scan")
    def post_scan(request: ScanRequest | None = None) -> dict:
        resolved_name, active_view = _resolve_view_and_name(request)

        scan_result = scan_records(root_path, active_view.pattern)
        records = [dict(record) for record in scan_result.records]
        warnings = [
            {"path": warning.path, "message": warning.message}
            for warning in scan_result.warnings
        ]

        cached_records[resolved_name] = records
        cached_scan_meta[resolved_name] = (scan_result.summary, warnings)

        return _response_from_records(records, active_view, scan_result.summary, warnings)

    @app.post("/api/render")
    def post_render(request: ScanRequest | None = None) -> dict:
        resolved_name, active_view = _resolve_view_and_name(request)

        if resolved_name not in cached_records:
            scan_result = scan_records(root_path, active_view.pattern)
            records = [dict(record) for record in scan_result.records]
            warnings = [
                {"path": warning.path, "message": warning.message}
                for warning in scan_result.warnings
            ]
            cached_records[resolved_name] = records
            cached_scan_meta[resolved_name] = (scan_result.summary, warnings)
            return _response_from_records(records, active_view, scan_result.summary, warnings)

        summary, warnings = cached_scan_meta.get(
            resolved_name,
            (
                {
                    "total_files": 0,
                    "matched_files": 0,
                    "parsed_records": len(cached_records[resolved_name]),
                    "warning_count": 0,
                },
                [],
            ),
        )
        records = [dict(record) for record in cached_records[resolved_name]]
        return _response_from_records(records, active_view, summary, warnings)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(web_root / "index.html")

    return app
