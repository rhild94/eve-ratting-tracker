import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest


def client(test_app, timeout=5):
    return httpx.Client(
        cookies=test_app["cookies"],
        headers=test_app["headers"],
        base_url=test_app["base_url"],
        timeout=timeout,
        trust_env=False,
    )


def start_run(c, anomaly="Angel Haven", **extra):
    payload = {
        "anomaly": anomaly,
        "variant": "Default",
        "participants": [90000001],
        "notes": "",
        **extra,
    }
    return c.post("/api/run/start", json=payload)


def test_run_lifecycle_validation_persistence_and_session_completion(test_app):
    with client(test_app) as c:
        invalid = c.post("/api/run/start", json={
            "anomaly": "Angel Haven", "variant": "Default",
            "participants": [], "notes": ""
        })
        assert invalid.status_code == 400
        assert c.get("/api/dashboard").json()["active"] is None

        client_started = datetime.now(timezone.utc) - timedelta(seconds=120)
        server_before = datetime.now(timezone.utc)
        response = start_run(
            c,
            notes="automated smoke test",
            client_started_at=client_started.isoformat(),
        )
        server_after = datetime.now(timezone.utc)
        assert response.status_code == 200, response.text
        payload = response.json()
        run = payload["run"]
        rid, sid = run["id"], payload["session_id"]
        assert run["system_name"] == "W-16DY"
        persisted_start = datetime.fromisoformat(run["started_at"])
        assert server_before - timedelta(seconds=1) <= persisted_start <= server_after + timedelta(seconds=1)
        assert (persisted_start - client_started).total_seconds() > 100

        paused = c.post(f"/api/run/{rid}/pause")
        assert paused.status_code == 200
        assert paused.json()["run"]["is_paused"] is True
        resumed = c.post(f"/api/run/{rid}/pause")
        assert resumed.status_code == 200
        assert resumed.json()["run"]["is_paused"] is False

        completed = c.post(f"/api/run/{rid}/complete")
        assert completed.status_code == 200
        assert completed.json()["bounty_pending"] is True
        assert completed.json()["run"]["duration_seconds"] < 10
        dashboard = c.get("/api/dashboard").json()
        assert dashboard["active"] is None
        assert len(dashboard["recent"]) == 1
        assert dashboard["esi"]["pending_runs"] == 1

        saved_bonus = c.post(f"/api/run/{rid}/bonus", json={
            "escalation_name": "Angel Capital Staging",
            "escalation_status": "Sold",
            "escalation_sale_value": 123456789,
            "rare_spawn_type": "Commander",
            "rare_spawn_name": "Test Commander",
            "rare_spawn_value": 5000000,
            "notes": "saved locally",
        })
        assert saved_bonus.status_code == 200, saved_bonus.text
        saved = c.get(f"/api/run/{rid}").json()["run"]
        assert saved["escalation_status"] == "Sold"
        assert saved["escalation_sale_value"] == 123456789
        assert saved["rare_spawn_value"] == 5000000
        assert saved["notes"] == "saved locally"

        pending = c.post(f"/api/run/{rid}/bonus", json={
            "escalation_name": "Angel Capital Staging",
            "escalation_status": "Pending",
            "escalation_sale_value": 30000000,
            "rare_spawn_type": "Commander",
            "rare_spawn_name": "Test Commander",
            "rare_spawn_value": 5000000,
        })
        assert pending.status_code == 200
        saved = c.get(f"/api/run/{rid}").json()["run"]
        assert saved["escalation_status"] == "Pending"
        assert saved["escalation_sale_value"] == 0

        ended = c.post("/api/session/end", json={
            "loot_value": 10000000,
            "salvage_value": 20000000,
            "notes": "session complete",
        })
        assert ended.status_code == 200
        session = c.get(f"/api/session/{sid}").json()["session"]
        assert session["loot_value"] == 10000000
        assert session["salvage_value"] == 20000000
        assert session["notes"] == "session complete"
        assert c.get("/api/dashboard").json()["session"] is None


def test_dashboard_sync_health_and_history_ess_identity(test_app):
    db = test_app["work"] / "ratting_tracker.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE account_sync_state SET last_attempt=?,last_success=?,last_error=?,next_check=? WHERE user_id=1",
            ("2026-09-05T12:00:00+00:00", "2026-09-05T11:30:00+00:00",
             "simulated ESI outage", "2026-09-05T12:30:00+00:00"),
        )
        conn.execute(
            "INSERT INTO ess_events(user_id,entry_id,character_id,date,amount) VALUES(1,?,?,?,?)",
            (999001, 90000001, "2026-09-05T06:25:00+00:00", 12230000),
        )

    with client(test_app) as c:
        esi = c.get("/api/dashboard").json()["esi"]
        assert esi["interval_minutes"] == 30
        assert esi["last_error"] == "simulated ESI outage"
        assert esi["last_success"] == "2026-09-05T11:30:00+00:00"
        assert esi["next_check"] == "2026-09-05T12:30:00+00:00"

        history = c.get("/history")
        assert history.status_code == 200
        assert "Playwright Pilot" in history.text
        assert "Character ID" not in history.text
        assert "Unassigned" not in history.text


def test_run_and_session_deletion_are_responsive_under_immediate_restart(test_app):
    with client(test_app) as c:
        response = start_run(c, notes="delete regression")
        rid = response.json()["run"]["id"]
        assert c.post(f"/api/run/{rid}/complete").status_code == 200
        started = time.monotonic()
        deleted = c.delete(f"/api/run/{rid}")
        assert deleted.status_code == 200, deleted.text
        assert time.monotonic() - started < 2.0
        assert c.get(f"/api/run/{rid}").status_code == 404

        response = start_run(c, notes="concurrency regression")
        rid = response.json()["run"]["id"]
        assert c.post(f"/api/run/{rid}/complete").status_code == 200
        assert c.post("/api/session/end", json={"loot_value": 0, "salvage_value": 0, "notes": ""}).status_code == 200

    with sqlite3.connect(test_app["work"] / "ratting_tracker.db") as db:
        sid = db.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()[0]

    results = {}
    gate = threading.Barrier(2)

    def do_delete():
        gate.wait()
        with client(test_app, timeout=10) as c:
            results["delete"] = c.delete(f"/api/session/{sid}")

    def do_start():
        gate.wait()
        time.sleep(0.02)
        with client(test_app, timeout=10) as c:
            results["start"] = start_run(c, anomaly="Angel Hub", notes="after delete")

    t1 = threading.Thread(target=do_delete)
    t2 = threading.Thread(target=do_start)
    t1.start(); t2.start(); t1.join(); t2.join()

    assert results["delete"].status_code != 500
    assert results["start"].status_code != 500
    assert results["start"].status_code in (200, 409)


def test_progression_renders_empty_and_cached_snapshot(test_app):
    db = test_app["work"] / "ratting_tracker.db"
    with client(test_app) as c:
        empty = c.get("/progression")
        assert empty.status_code == 200
        assert '"page": "progression"' in empty.text

        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO type_names(type_id,name) VALUES(?,?)", (3300, "Gunnery"))
            conn.execute(
                "INSERT INTO skill_snapshots(user_id,character_id,captured_at,total_sp,skills_json,queue_json) VALUES(1,?,?,?,?,?)",
                (90000001, "2026-09-05T12:00:00+00:00", 1234567,
                 '[{"skill_id": 3300, "trained_skill_level": 3}]',
                 '[{"skill_id": 3300, "finished_level": 4, "finish_date": "2026-09-06T12:00:00Z"}]'),
            )

        populated = c.get("/progression")
        assert populated.status_code == 200
        assert '"total_sp": 1234567' in populated.text
        assert '"skill": "Gunnery"' in populated.text


def test_history_session_update_api(test_app):
    with client(test_app) as c:
        response = start_run(c)
        rid, sid = response.json()["run"]["id"], response.json()["session_id"]
        assert c.post(f"/api/run/{rid}/complete").status_code == 200
        assert c.post("/api/session/end", json={
            "loot_value": 1000000, "salvage_value": 2000000, "notes": "old"
        }).status_code == 200
        updated = c.post(f"/api/session/{sid}", json={
            "loot_value": 3000000, "salvage_value": 4000000, "notes": "updated"
        })
        assert updated.status_code == 200
        session = c.get(f"/api/session/{sid}").json()["session"]
        assert session["loot_value"] == 3000000
        assert session["salvage_value"] == 4000000
        assert session["notes"] == "updated"


def test_dashboard_main_character_and_background_smoke(test_app):
    with client(test_app) as c:
        dashboard = c.get("/dashboard")
        assert dashboard.status_code == 200
        assert '"page": "dashboard"' in dashboard.text
        assert '"perf":' in dashboard.text

        main = c.post("/api/character/90000001/main")
        assert main.status_code == 200, main.text
        chars = c.get("/api/dashboard").json()["characters"]
        assert chars[0]["id"] == 90000001
        assert chars[0]["role"] == "main"

        background = c.get("/art/eve-bg.webp")
        assert background.status_code == 200
        assert background.headers["content-type"].startswith("image/webp")
        assert background.content[:4] == b"RIFF"
        assert background.content[8:12] == b"WEBP"
        assert int.from_bytes(background.content[4:8], "little") + 8 == len(background.content)
        assert len(background.content) > 30000


def test_bounty_tick_is_allocated_across_overlapping_sites(test_app):
    db = test_app["work"] / "ratting_tracker.db"
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM wallet_entries")
        c.execute("""INSERT INTO sessions(user_id,id,started_at,ended_at,status) VALUES(1,?,?,?,'complete')""",
                  (101, "2026-09-05T12:00:00+00:00", "2026-09-05T12:20:00+00:00"))
        c.execute("""INSERT INTO runs(user_id,
            id,anomaly,variant,started_at,ended_at,participants_json,notes,status,
            combined_bounty,system_name,ships_json,session_id,paused_seconds
        ) VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (201, "Angel Haven", "Gas Haven · Chemical Factory", "2026-09-05T12:00:00+00:00",
                   "2026-09-05T12:10:00+00:00", "[90000001]", "", 'complete', 0, "W-16DY", "[]", 101, 0))
        c.execute("""INSERT INTO runs(user_id,
            id,anomaly,variant,started_at,ended_at,participants_json,notes,status,
            combined_bounty,system_name,ships_json,session_id,paused_seconds
        ) VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (202, "Angel Haven", "Gas Haven · Chemical Factory", "2026-09-05T12:10:00+00:00",
                   "2026-09-05T12:20:00+00:00", "[90000001]", "", 'complete', 0, "W-16DY", "[]", 101, 0))
        c.execute("""INSERT INTO wallet_entries(user_id,
            entry_id,character_id,date,amount,balance,ref_type,description,raw_json
        ) VALUES(1,?,?,?,?,?,?,?,?)""",
                  (7001, 90000001, "2026-09-05T12:20:00+00:00", 20000000, 0, "bounty_prizes", "tick", "{}"))

    env = os.environ.copy()
    env["TRACKER_DB_PATH"] = str(db)
    env["ESI_AUTO_SYNC_INITIAL_DELAY_SECONDS"] = "3600"
    proc = subprocess.run(
        [sys.executable, "-c", "import app; app.account_context.set(1); app.reconcile_bounties()"],
        cwd=test_app["work"], env=env, capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    with sqlite3.connect(db) as c:
        values = [x[0] for x in c.execute(
            "SELECT combined_bounty FROM runs WHERE id IN (201,202) ORDER BY id"
        )]
    assert values[0] == pytest.approx(10000000, rel=1e-6)
    assert values[1] == pytest.approx(10000000, rel=1e-6)
    assert sum(values) == pytest.approx(20000000, rel=1e-6)


def test_multi_character_wallet_totals_and_entry_id_scoping(test_app):
    db = test_app["work"] / "ratting_tracker.db"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    same_entry_id = 99112233
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM wallet_entries")
        c.execute("""INSERT OR REPLACE INTO characters(user_id,
            character_id,name,access_token,refresh_token,expires_at,connected_at,
            cache_system_name,cache_ship_name,last_esi_sync,character_role
        ) VALUES(1,?,?,?,?,?,?,?,?,?,?)""",
        (90000002, "Second Pilot", "fake-token", "fake-refresh", 4102444800, now,
         "W-16DY", "Praxis", now, "alt"))
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (same_entry_id, 90000001, now, 3920000, 0, "bounty_prizes", "main", "{}"))
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (same_entry_id, 90000002, now, 4080000, 0, "bounty_prizes", "alt", "{}"))
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (8103, 90000001, now, 12230000, 0, "ess_escrow_transfer", "ESS", "{}"))
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (8104, 90000002, now, 11770000, 0, "ess_escrow_transfer", "ESS", "{}"))

    try:
        with client(test_app) as c:
            stats = c.get("/api/dashboard").json()["stats"]
            assert stats["today_isk"] == pytest.approx(8000000)
            assert stats["today_ess"] == pytest.approx(24000000)
            assert stats["today_sites"] == 0
            assert stats["today_seconds"] == 0

        with sqlite3.connect(db) as c:
            rows = c.execute(
                "SELECT character_id,amount FROM wallet_entries WHERE entry_id=? ORDER BY character_id",
                (same_entry_id,),
            ).fetchall()
            assert rows == [(90000001, 3920000.0), (90000002, 4080000.0)]
    finally:
        with sqlite3.connect(db) as c:
            c.execute("DELETE FROM wallet_entries WHERE character_id=90000002 OR entry_id IN (?,8103)", (same_entry_id,))
            c.execute("DELETE FROM characters WHERE character_id=90000002")
