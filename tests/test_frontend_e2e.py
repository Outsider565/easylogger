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
    step_row.get_by_role("checkbox").click()

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
    assert "double_step" in headers

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
