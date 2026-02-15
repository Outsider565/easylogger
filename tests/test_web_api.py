from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from easylogger.models import ComputedColumn
from easylogger.view_store import default_view, save_view
from easylogger.web_api import create_app


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_web_api_scan_and_view_endpoints(tmp_path: Path) -> None:
    view = default_view("demo", r".*\.scaler\.json$")
    view.columns.computed = [ComputedColumn(name="double_step", expr='row["step"] * 2')]
    save_view(tmp_path, view)

    write(tmp_path / "logs" / "a.scaler.json", '{"step": 2, "loss": 0.4}')
    write(tmp_path / "logs" / "b.scaler.json", '{"step": 5, "loss": 0.3, "meta": {"bad": 1}}')

    client = TestClient(create_app(tmp_path, "demo"))

    view_resp = client.get("/api/view")
    assert view_resp.status_code == 200
    assert view_resp.json()["name"] == "demo"

    scan_resp = client.post("/api/scan", json={})
    assert scan_resp.status_code == 200

    payload = scan_resp.json()
    assert payload["summary"]["parsed_records"] == 2
    assert payload["summary"]["warning_count"] == 1
    assert "double_step" in payload["columns"]["all"]

    rows = {row["path"]: row for row in payload["rows"]}
    assert rows["logs/a.scaler.json"]["double_step"] == 4
    assert rows["logs/b.scaler.json"]["meta"] is None


def test_web_api_rejects_view_name_mismatch(tmp_path: Path) -> None:
    view = default_view("demo", r".*")
    save_view(tmp_path, view)

    client = TestClient(create_app(tmp_path, "demo"))
    payload = view.model_dump()
    payload["name"] = "other"

    resp = client.post("/api/view", json=payload)
    assert resp.status_code == 400


def test_web_api_serves_index(tmp_path: Path) -> None:
    view = default_view("demo", r".*")
    save_view(tmp_path, view)

    client = TestClient(create_app(tmp_path, "demo"))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "EasyLogger" in resp.text

    static_resp = client.get("/static/styles.css")
    assert static_resp.status_code == 200
    assert "body" in static_resp.text
