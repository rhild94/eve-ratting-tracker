import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"

def valid_env(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return "EVE_CLIENT_ID=" in text and any(
            line.startswith("EVE_CLIENT_ID=") and line.split("=", 1)[1].strip()
            for line in text.splitlines()
        )
    except Exception:
        return False

def migrate_existing_config():
    if valid_env(ENV):
        return ENV
    candidates = []
    roots = [BASE.parent]
    home = Path.home()
    for name in ("Desktop", "Downloads", "Documents"):
        p = home / name
        if p.exists():
            roots.append(p)
    seen = set()
    for root in roots:
        try:
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                lname = child.name.lower()
                if "ratting" not in lname and "eve" not in lname:
                    continue
                candidate = child / ".env"
                if candidate.exists() and candidate.resolve() not in seen and valid_env(candidate):
                    seen.add(candidate.resolve())
                    candidates.append(candidate)
        except Exception:
            pass
    if candidates:
        source = max(candidates, key=lambda p: p.stat().st_mtime)
        shutil.copy2(source, ENV)
        print(f"Imported existing EVE configuration from: {source.parent}")
        return ENV
    return None

def wait_for_app(url, process, timeout=25):
    deadline = time.time() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Tracker stopped before the web interface started.")
        try:
            with opener.open(url, timeout=1) as response:
                if response.status in (200, 302):
                    return
        except Exception:
            pass
        time.sleep(.25)
    raise RuntimeError("Tracker did not start in time.")

def main():
    migrate_existing_config()
    process = subprocess.Popen([sys.executable, str(BASE / "app.py")], cwd=BASE)
    url = "http://127.0.0.1:8000/"
    try:
        wait_for_app(url, process)
        webbrowser.open(url)
        print("EVE Ratting Tracker is running.")
        print("Keep this window open while using the tracker. Press Ctrl+C to stop it.")
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
    except Exception as exc:
        print(f"Could not start tracker: {exc}")
        process.terminate()
        input("Press Enter to close...")

if __name__ == "__main__":
    main()
