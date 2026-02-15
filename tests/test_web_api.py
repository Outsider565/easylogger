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


def test_web_api_render_uses_cached_scan_until_refresh(tmp_path: Path) -> None:
    view = default_view("demo", r".*\.scaler\.json$")
    save_view(tmp_path, view)
    write(tmp_path / "logs" / "a.scaler.json", '{"step": 1, "loss": 0.2}')

    client = TestClient(create_app(tmp_path, "demo"))

    scan_resp = client.post("/api/scan", json={})
    assert scan_resp.status_code == 200
    assert scan_resp.json()["summary"]["parsed_records"] == 1

    write(tmp_path / "logs" / "b.scaler.json", '{"step": 2, "loss": 0.1}')

    render_resp = client.post("/api/render", json={})
    assert render_resp.status_code == 200
    render_paths = [row["path"] for row in render_resp.json()["rows"]]
    assert render_paths == ["logs/a.scaler.json"]

    refreshed = client.post("/api/scan", json={})
    refreshed_paths = sorted(row["path"] for row in refreshed.json()["rows"])
    assert refreshed_paths == ["logs/a.scaler.json", "logs/b.scaler.json"]


def test_web_api_supports_view_tabs_lifecycle(tmp_path: Path) -> None:
    save_view(tmp_path, default_view("demo", r".*\.scaler\.json$"))
    save_view(tmp_path, default_view("baseline", r".*\.json$"))
    client = TestClient(create_app(tmp_path, "demo"))

    list_resp = client.get("/api/views")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["views"] == ["baseline", "demo"]
    assert payload["active"] == "demo"

    create_resp = client.post(
        "/api/views/create",
        json={"name": "copy1", "from_name": "baseline"},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["name"] == "copy1"

    rename_resp = client.post(
        "/api/views/rename",
        json={"old_name": "copy1", "new_name": "renamed"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["name"] == "renamed"

    get_resp = client.get("/api/views/renamed")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "renamed"


def test_web_api_keeps_scan_cache_per_view(tmp_path: Path) -> None:
    view_a = default_view("a", r"a\.scaler\.json$")
    view_b = default_view("b", r"b\.scaler\.json$")
    save_view(tmp_path, view_a)
    save_view(tmp_path, view_b)
    write(tmp_path / "a.scaler.json", '{"step": 1}')
    write(tmp_path / "b.scaler.json", '{"step": 2}')

    client = TestClient(create_app(tmp_path, "a"))
    scan_a = client.post("/api/scan", json={"view_name": "a"})
    assert scan_a.status_code == 200
    assert [row["path"] for row in scan_a.json()["rows"]] == ["a.scaler.json"]

    scan_b = client.post("/api/scan", json={"view_name": "b"})
    assert scan_b.status_code == 200
    assert [row["path"] for row in scan_b.json()["rows"]] == ["b.scaler.json"]

    write(tmp_path / "a.scaler.json", '{"step": 9}')

    render_a = client.post("/api/render", json={"view_name": "a"})
    assert render_a.status_code == 200
    assert [row["path"] for row in render_a.json()["rows"]] == ["a.scaler.json"]
    # Cached render should still show old step before refresh-scan.
    assert render_a.json()["rows"][0]["step"] == 1
