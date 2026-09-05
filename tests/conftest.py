import os
import shutil
import socket
import shutil as shell_shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(url, timeout=12):
    import httpx
    deadline = time.time() + timeout
    last = None
    with httpx.Client(timeout=1, trust_env=False) as client:
        while time.time() < deadline:
            try:
                r = client.get(url)
                if r.status_code == 200:
                    return
            except Exception as e:
                last = e
            time.sleep(0.15)
    raise RuntimeError(f"Test server did not start: {last}")


@pytest.fixture(scope="session")
def test_app(tmp_path_factory):
    work = tmp_path_factory.mktemp("eve_ratting_tracker")
    for name in ["app.py", "static", "templates"]:
        src = PROJECT_ROOT / name
        dst = work / name
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    port = free_port()
    env = os.environ.copy()
    env.update({
        "TRACKER_HOST": "127.0.0.1",
        "TRACKER_PORT": str(port),
        "EVE_CLIENT_ID": "",
        "EVE_CLIENT_SECRET": "",
        "EVE_CALLBACK_URL": f"http://127.0.0.1:{port}/callback",
        "PYTHONUNBUFFERED": "1",
        "ESI_AUTO_SYNC_INITIAL_DELAY_SECONDS": "3600",
        "ESI_AUTO_SYNC_SECONDS": "1800",
    })

    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=work,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        try:
            wait_for_server(base_url)
        except Exception as exc:
            proc.terminate()
            try:
                output, _ = proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()
            raise RuntimeError(f"{exc}\n--- app.py output ---\n{output}") from exc
        db = work / "ratting_tracker.db"
        now = "2026-09-05T12:00:00+00:00"
        with sqlite3.connect(db) as c:
            c.execute(
                """INSERT INTO characters(
                    character_id,name,access_token,refresh_token,expires_at,connected_at,
                    cache_system_name,cache_ship_name,last_esi_sync
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (90000001, "Playwright Pilot", "fake-token", "fake-refresh", 4102444800, now,
                 "W-16DY", "Praxis", now),
            )
        yield {"base_url": base_url, "work": work, "process": proc}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        if not executable:
            executable = shell_shutil.which("chromium") or shell_shutil.which("google-chrome") or shell_shutil.which("msedge")
        if not executable:
            for candidate in [
                "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
                r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
            ]:
                if Path(candidate).exists():
                    executable = candidate
                    break
        kwargs = {"headless": True, "args": ["--no-proxy-server", "--proxy-bypass-list=<-loopback>"]}
        if executable:
            kwargs["executable_path"] = executable
        b = p.chromium.launch(**kwargs)
        yield b
        b.close()


@pytest.fixture()
def page(browser, test_app):
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(5000)
    page.goto(test_app["base_url"])
    yield page
    context.close()


@pytest.fixture(autouse=True)
def clean_runtime_data(test_app):
    db = test_app["work"] / "ratting_tracker.db"
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM ess_events")
        c.execute("DELETE FROM runs")
        c.execute("DELETE FROM sessions")
    yield
