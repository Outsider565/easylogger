from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from easylogger.view_store import default_view, save_view
from easylogger.web_api import create_app


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_until_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:  # noqa: S310
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.1)
            continue
    raise RuntimeError(f"Server did not become ready in time: {url}")


@pytest.fixture()
def frontend_env(tmp_path: Path):
    view = default_view("demo", r".*\.scaler\.json$")
    save_view(tmp_path, view)

    _write(tmp_path / "logs" / "a.scaler.json", '{"step": 1, "loss": 0.2, "note": "first"}')

    port = _pick_free_port()
    app = create_app(tmp_path, "demo")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    _wait_until_ready(f"{base_url}/api/meta")

    try:
        yield {
            "root": tmp_path,
            "base_url": base_url,
            "view_file": tmp_path / ".easylogger" / "views" / "demo.json",
        }
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture()
def page():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"Playwright Chromium is unavailable: {exc}")

        context = browser.new_context()
        active_page = context.new_page()
        try:
            yield active_page
        finally:
            context.close()
            browser.close()


def _open_app(page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".column-row")


def test_frontend_refresh_reloads_scan_results(frontend_env, page) -> None:
    _open_app(page, frontend_env["base_url"])

    expect(page.locator("tbody tr")).to_have_count(1)

    _write(
        frontend_env["root"] / "logs" / "b.scaler.json",
        '{"step": 2, "loss": 0.1, "note": "second"}',
    )

    # The app should not auto-refresh.
    expect(page.locator("tbody tr")).to_have_count(1)

    page.get_by_role("button", name="Refresh").click()
    expect(page.locator("tbody tr")).to_have_count(2)


def test_frontend_save_view_persists_column_configuration(frontend_env, page) -> None:
    _open_app(page, frontend_env["base_url"])

    loss_row = page.locator(".column-row", has=page.locator("span.column-name", has_text="loss"))
    loss_row.locator("input[placeholder='alias']").fill("Loss Score")

    step_row = page.locator(".column-row", has=page.locator("span.column-name", has_text="step"))
    step_row.locator("input[type='checkbox']").evaluate("element => element.click()")

    page.get_by_role("button", name="Add computed column").click()
    computed_rows = page.locator(".computed-row")
    last_row = computed_rows.nth(computed_rows.count() - 1)
    last_row.locator("input").nth(0).fill("double_step")
    last_row.locator("input").nth(1).fill('row["step"] * 2')

    page.get_by_role("button", name="Save View").click()

    expect(page.locator("text=Unsaved changes")).to_have_count(0)
    expect(page.locator("th", has_text="Loss Score")).to_have_count(1)

    headers = page.locator("th").all_inner_texts()
    assert "step" not in headers
    assert any(text.startswith("double_step") for text in headers)

    persisted = json.loads(frontend_env["view_file"].read_text(encoding="utf-8"))
    assert persisted["columns"]["alias"]["loss"] == "Loss Score"
    assert "step" in persisted["columns"]["hidden"]
    assert any(
        item["name"] == "double_step" and item["expr"] == 'row["step"] * 2'
        for item in persisted["columns"]["computed"]
    )


def test_frontend_beforeunload_warning_logic_when_dirty(frontend_env, page) -> None:
    _open_app(page, frontend_env["base_url"])

    clean_state_blocks = page.evaluate(
        """
        () => {
          const event = new Event('beforeunload', { cancelable: true });
          window.dispatchEvent(event);
          return event.defaultPrevented;
        }
        """
    )
    assert clean_state_blocks is False

    path_row = page.locator(".column-row", has=page.locator("span.column-name", has_text="path"))
    path_row.locator("input[placeholder='alias']").fill("Log Path")

    dirty_state_blocks = page.evaluate(
        """
        () => {
          const event = new Event('beforeunload', { cancelable: true });
          window.dispatchEvent(event);
          return event.defaultPrevented;
        }
        """
    )
    assert dirty_state_blocks is True


def test_frontend_bulk_visibility_and_drag_reorder(frontend_env, page) -> None:
    _open_app(page, frontend_env["base_url"])

    page.get_by_role("button", name="All invisible").click()
    expect(page.locator("th")).to_have_count(1)
    expect(page.locator("th").first).to_have_text("Row")

    page.get_by_role("button", name="All visible").click()
    visible_headers = page.locator("th").all_inner_texts()
    assert any(text.startswith("path") for text in visible_headers)
    assert any(text.startswith("loss") for text in visible_headers)
    assert any(text.startswith("step") for text in visible_headers)

    loss_row = page.locator(".column-row", has=page.locator("span.column-name", has_text="loss"))
    path_row = page.locator(".column-row", has=page.locator("span.column-name", has_text="path"))
    loss_row.locator(".drag-handle").drag_to(path_row.locator(".drag-handle"))

    expect(page.locator("th.sortable").first).to_contain_text("loss")

    page.get_by_role("button", name="Save View").click()
    persisted = json.loads(frontend_env["view_file"].read_text(encoding="utf-8"))
    assert persisted["columns"]["order"][0] == "loss"


def test_frontend_table_sort_and_pin_controls(frontend_env, page) -> None:
    _write(frontend_env["root"] / "logs" / "b.scaler.json", '{"step": 3, "loss": 0.05}')
    _write(frontend_env["root"] / "logs" / "c.scaler.json", '{"step": 2, "loss": 0.6}')
    _open_app(page, frontend_env["base_url"])
    page.get_by_role("button", name="Refresh").click()

    row_by_path = lambda path: page.locator("tbody tr", has=page.locator("td", has_text=path))

    row_by_path("logs/b.scaler.json").get_by_role("button", name="Pin").click()
    row_by_path("logs/c.scaler.json").get_by_role("button", name="Pin").click()

    row_by_path("logs/c.scaler.json").locator(".row-drag-handle").drag_to(
        row_by_path("logs/b.scaler.json").locator(".row-drag-handle")
    )

    step_header = page.locator("th.sortable", has_text="step")
    step_header.click()
    step_header.click()

    first_two_paths = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('tbody tr'))
          .slice(0, 2)
          .map((row) => row.querySelectorAll('td')[1].innerText.trim())
        """
    )
    assert first_two_paths == ["logs/c.scaler.json", "logs/b.scaler.json"]

    page.get_by_role("button", name="Save View").click()
    persisted = json.loads(frontend_env["view_file"].read_text(encoding="utf-8"))
    assert persisted["rows"]["pinned_ids"][:2] == ["logs/c.scaler.json", "logs/b.scaler.json"]
    assert persisted["rows"]["sort"]["by"] == "step"
    assert persisted["rows"]["sort"]["direction"] == "desc"
