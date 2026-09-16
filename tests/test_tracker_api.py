import pytest
import httpx


def test_local_run_lifecycle_and_bonus_persistence(test_app):
    base = test_app["base_url"]
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=5) as c:
        r = c.post("/api/run/start", json={
            "anomaly": "Angel Haven",
            "variant": "Default",
            "participants": [90000001],
            "notes": "automated smoke test",
        })
        assert r.status_code == 200, r.text
        run = r.json()["run"]
        rid = run["id"]
        assert run["system_name"] == "W-16DY"

        r = c.post(f"/api/run/{rid}/pause")
        assert r.status_code == 200
        assert r.json()["run"]["is_paused"] is True

        r = c.post(f"/api/run/{rid}/pause")
        assert r.status_code == 200
        assert r.json()["run"]["is_paused"] is False

        r = c.post(f"/api/run/{rid}/complete")
        assert r.status_code == 200
        assert r.json()["bounty_pending"] is True

        r = c.post(f"/api/run/{rid}/bonus", json={
            "escalation_name": "Angel Capital Staging",
            "escalation_status": "Sold",
            "escalation_sale_value": 123456789,
            "rare_spawn_type": "Commander",
            "rare_spawn_name": "Test Commander",
            "rare_spawn_value": 5000000,
            "notes": "saved locally",
        })
        assert r.status_code == 200, r.text

        r = c.get(f"/api/run/{rid}")
        assert r.status_code == 200
        saved = r.json()["run"]
        assert saved["escalation_status"] == "Sold"
        assert saved["escalation_sale_value"] == 123456789
        assert saved["rare_spawn_value"] == 5000000
        assert saved["notes"] == "saved locally"


def test_dashboard_reports_completed_run_as_pending_esi(test_app):
    base = test_app["base_url"]
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=5) as c:
        r = c.post("/api/run/start", json={
            "anomaly": "Angel Hub", "variant": "Default",
            "participants": [90000001], "notes": ""
        })
        rid = r.json()["run"]["id"]
        assert c.post(f"/api/run/{rid}/complete").status_code == 200
        d = c.get("/api/dashboard").json()
        assert d["active"] is None
        assert len(d["recent"]) == 1
        assert d["esi"]["pending_runs"] == 1


def test_end_session_saves_loot_and_salvage(test_app):
    base = test_app["base_url"]
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=5) as c:
        r = c.post("/api/run/start", json={
            "anomaly": "Angel Haven", "variant": "Default",
            "participants": [90000001], "notes": ""
        })
        rid = r.json()["run"]["id"]
        c.post(f"/api/run/{rid}/complete")
        r = c.post("/api/session/end", json={
            "loot_value": 10000000,
            "salvage_value": 20000000,
            "notes": "session complete",
        })
        assert r.status_code == 200
        d = c.get("/api/dashboard").json()
        assert d["session"] is None


def test_invalid_start_is_rejected_without_creating_run(test_app):
    base = test_app["base_url"]
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=5) as c:
        r = c.post("/api/run/start", json={
            "anomaly": "Angel Haven", "variant": "Default",
            "participants": [], "notes": ""
        })
        assert r.status_code == 400
        assert c.get("/api/dashboard").json()["active"] is None


def test_dashboard_exposes_esi_sync_health(test_app):
    import sqlite3
    db = test_app["work"] / "ratting_tracker.db"
    with sqlite3.connect(db) as c:
        c.execute(
            "UPDATE account_sync_state SET last_attempt=?,last_success=?,last_error=?,next_check=? WHERE user_id=1",
            ("2026-09-05T12:00:00+00:00", "2026-09-05T11:30:00+00:00",
             "simulated ESI outage", "2026-09-05T12:30:00+00:00"),
        )
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as c:
        e = c.get("/api/dashboard").json()["esi"]
        assert e["interval_minutes"] == 30
        assert e["last_error"] == "simulated ESI outage"
        assert e["last_success"] == "2026-09-05T11:30:00+00:00"
        assert e["next_check"] == "2026-09-05T12:30:00+00:00"


def test_delete_completed_run_returns_promptly(test_app):
    import time
    base = test_app["base_url"]
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=5) as c:
        r = c.post("/api/run/start", json={
            "anomaly": "Angel Haven",
            "variant": "Default",
            "participants": [90000001],
            "notes": "delete regression",
        })
        rid = r.json()["run"]["id"]
        assert c.post(f"/api/run/{rid}/complete").status_code == 200
        started = time.monotonic()
        r = c.delete(f"/api/run/{rid}")
        elapsed = time.monotonic() - started
        assert r.status_code == 200, r.text
        assert elapsed < 2.0
        assert c.get(f"/api/run/{rid}").status_code == 404


def test_progression_page_loads_without_snapshots(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as c:
        r = c.get("/progression")
        assert r.status_code == 200
        assert '"page": "progression"' in r.text


def test_session_update_api(test_app):
    base = test_app["base_url"]
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=5) as c:
        r = c.post("/api/run/start", json={"anomaly":"Angel Haven","variant":"Default","participants":[90000001],"notes":""})
        rid = r.json()["run"]["id"]
        c.post(f"/api/run/{rid}/complete")
        c.post("/api/session/end", json={"loot_value":1000000,"salvage_value":2000000,"notes":"old"})
        import sqlite3
        with sqlite3.connect(test_app["work"] / "ratting_tracker.db") as db:
            sid = db.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()[0]
        r = c.post(f"/api/session/{sid}", json={"loot_value":3000000,"salvage_value":4000000,"notes":"updated"})
        assert r.status_code == 200
        j = c.get(f"/api/session/{sid}").json()["session"]
        assert j["loot_value"] == 3000000
        assert j["salvage_value"] == 4000000
        assert j["notes"] == "updated"


def test_progression_uses_cached_snapshot_and_names(test_app):
    import sqlite3, json
    db = test_app["work"] / "ratting_tracker.db"
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO type_names(type_id,name) VALUES(?,?)", (3300, "Gunnery"))
        c.execute("INSERT INTO skill_snapshots(user_id,character_id,captured_at,total_sp,skills_json,queue_json) VALUES(1,?,?,?,?,?)",
                  (90000001, "2026-09-05T12:00:00+00:00", 1234567,
                   json.dumps([{"skill_id":3300,"trained_skill_level":3}]),
                   json.dumps([{"skill_id":3300,"finished_level":4,"finish_date":"2026-09-06T12:00:00Z"}])))
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as c:
        r = c.get("/progression")
        assert r.status_code == 200
        assert '"total_sp": 1234567' in r.text
        assert '"skill": "Gunnery"' in r.text


def test_ess_history_shows_character_name_without_assignment_controls(test_app):
    import sqlite3
    db = test_app["work"] / "ratting_tracker.db"
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO ess_events(user_id,entry_id,character_id,date,amount) VALUES(1,?,?,?,?)",
                  (999001,90000001,"2026-09-05T06:25:00+00:00",12230000))
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as c:
        r = c.get("/history")
        assert r.status_code == 200
        assert "Playwright Pilot" in r.text
        assert "Character ID" not in r.text
        assert "Unassigned" not in r.text


def test_delete_session_and_immediate_start_never_500(test_app):
    import sqlite3
    import threading
    import time

    base = test_app["base_url"]
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=5) as c:
        r = c.post("/api/run/start", json={
            "anomaly":"Angel Haven","variant":"Default",
            "participants":[90000001],"notes":"concurrency regression"
        })
        rid = r.json()["run"]["id"]
        assert c.post(f"/api/run/{rid}/complete").status_code == 200
        assert c.post("/api/session/end", json={"loot_value":0,"salvage_value":0,"notes":""}).status_code == 200

    with sqlite3.connect(test_app["work"] / "ratting_tracker.db") as db:
        sid = db.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()[0]

    results = {}
    gate = threading.Barrier(2)

    def do_delete():
        gate.wait()
        with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=10) as c:
            results["delete"] = c.delete(f"/api/session/{sid}")

    def do_start():
        gate.wait()
        time.sleep(0.02)
        with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base, timeout=10) as c:
            results["start"] = c.post("/api/run/start", json={
                "anomaly":"Angel Hub","variant":"Default",
                "participants":[90000001],"notes":"after delete"
            })

    t1=threading.Thread(target=do_delete)
    t2=threading.Thread(target=do_start)
    t1.start();t2.start();t1.join();t2.join()

    assert results["delete"].status_code != 500
    assert results["start"].status_code != 500
    assert results["start"].status_code in (200,409)


def test_client_start_time_is_preserved(test_app):
    from datetime import datetime, timezone
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as c:
        r = c.post("/api/run/start", json={
            "anomaly":"Angel Haven","variant":"Default",
            "participants":[90000001],"notes":"",
            "client_started_at":started,
        })
        assert r.status_code == 200, r.text
        actual = r.json()["run"]["started_at"]
        assert actual.startswith(started[:19])


def test_main_character_role_endpoint(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as c:
        r = c.post("/api/character/90000001/main")
        assert r.status_code == 200, r.text
        chars = c.get("/api/dashboard").json()["characters"]
        assert chars[0]["id"] == 90000001
        assert chars[0]["role"] == "main"


def test_bounty_tick_is_allocated_across_overlapping_sites(test_app):
    import os
    import sqlite3
    import subprocess
    import sys

    db = test_app["work"] / "ratting_tracker.db"
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM wallet_entries")
        c.execute("""INSERT INTO sessions(user_id,id,started_at,ended_at,status) VALUES(1,?,?,?,'complete')""",
                  (101,"2026-09-05T12:00:00+00:00","2026-09-05T12:20:00+00:00"))
        c.execute("""INSERT INTO runs(user_id,
            id,anomaly,variant,started_at,ended_at,participants_json,notes,status,
            combined_bounty,system_name,ships_json,session_id,paused_seconds
        ) VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (201,"Angel Haven","Gas Haven · Chemical Factory","2026-09-05T12:00:00+00:00",
                   "2026-09-05T12:10:00+00:00","[90000001]","",'complete',0,"W-16DY","[]",101,0))
        c.execute("""INSERT INTO runs(user_id,
            id,anomaly,variant,started_at,ended_at,participants_json,notes,status,
            combined_bounty,system_name,ships_json,session_id,paused_seconds
        ) VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (202,"Angel Haven","Gas Haven · Chemical Factory","2026-09-05T12:10:00+00:00",
                   "2026-09-05T12:20:00+00:00","[90000001]","",'complete',0,"W-16DY","[]",101,0))
        c.execute("""INSERT INTO wallet_entries(user_id,
            entry_id,character_id,date,amount,balance,ref_type,description,raw_json
        ) VALUES(1,?,?,?,?,?,?,?,?)""",
                  (7001,90000001,"2026-09-05T12:20:00+00:00",20000000,0,"bounty_prizes","tick","{}"))

    env=os.environ.copy()
    env["TRACKER_DB_PATH"]=str(db)
    env["ESI_AUTO_SYNC_INITIAL_DELAY_SECONDS"]="3600"
    p=subprocess.run([sys.executable,"-c","import app; app.account_context.set(1); app.reconcile_bounties()"],
                     cwd=test_app["work"],env=env,capture_output=True,text=True,timeout=15)
    assert p.returncode == 0, p.stdout + p.stderr

    with sqlite3.connect(db) as c:
        vals=[x[0] for x in c.execute("SELECT combined_bounty FROM runs WHERE id IN (201,202) ORDER BY id")]
    assert vals[0] == pytest.approx(10000000, rel=1e-6)
    assert vals[1] == pytest.approx(10000000, rel=1e-6)
    assert sum(vals) == pytest.approx(20000000, rel=1e-6)


def test_dashboard_page_loads(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as c:
        r=c.get("/dashboard")
        assert r.status_code == 200
        assert '"page": "dashboard"' in r.text
        assert '"perf":' in r.text


def test_today_wallet_cards_sum_all_connected_characters_without_runs(test_app):
    import sqlite3
    from datetime import datetime, timezone

    db=test_app["work"] / "ratting_tracker.db"
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM wallet_entries")
        c.execute("""INSERT OR REPLACE INTO characters(user_id,
            character_id,name,access_token,refresh_token,expires_at,connected_at,
            cache_system_name,cache_ship_name,last_esi_sync,character_role
        ) VALUES(1,?,?,?,?,?,?,?,?,?,?)""",
        (90000002,"Second Pilot","fake-token","fake-refresh",4102444800,now,
         "W-16DY","Praxis",now,"alt"))
        # Two characters: bounty must be combined even with zero tracked runs.
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (8101,90000001,now,3920000,0,"bounty_prizes","main tick","{}"))
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (8102,90000002,now,4080000,0,"bounty_prizes","alt tick","{}"))
        # ESS is a day-level wallet metric and must not require a session/run.
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (8103,90000001,now,12230000,0,"ess_escrow_transfer","ESS","{}"))
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (8104,90000002,now,11770000,0,"ess_escrow_transfer","ESS","{}"))

    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"],timeout=5) as c:
        stats=c.get("/api/dashboard").json()["stats"]
        assert stats["today_isk"] == pytest.approx(8000000)
        assert stats["today_ess"] == pytest.approx(24000000)
        assert stats["today_sites"] == 0
        assert stats["today_seconds"] == 0

    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM wallet_entries WHERE entry_id IN (8101,8102,8103,8104)")
        c.execute("DELETE FROM characters WHERE character_id=90000002")


def test_wallet_entry_ids_are_scoped_per_character(test_app):
    import sqlite3
    from datetime import datetime, timezone

    db=test_app["work"] / "ratting_tracker.db"
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM wallet_entries")
        c.execute("""INSERT OR REPLACE INTO characters(user_id,
            character_id,name,access_token,refresh_token,expires_at,connected_at,
            cache_system_name,cache_ship_name,last_esi_sync,character_role
        ) VALUES(1,?,?,?,?,?,?,?,?,?,?)""",
        (90000002,"Second Pilot","fake-token","fake-refresh",4102444800,now,
         "W-16DY","Praxis",now,"alt"))
        # ESI journal entry ids can collide across characters. Both rows must survive.
        same_entry_id=99112233
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (same_entry_id,90000001,now,3920000,0,"bounty_prizes","main","{}"))
        c.execute("""INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json)
                     VALUES(1,?,?,?,?,?,?,?,?)""",
                  (same_entry_id,90000002,now,4080000,0,"bounty_prizes","alt","{}"))

    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"],timeout=5) as c:
        stats=c.get("/api/dashboard").json()["stats"]
        assert stats["today_isk"] == pytest.approx(8000000)

    with sqlite3.connect(db) as c:
        rows=c.execute("SELECT character_id,amount FROM wallet_entries WHERE entry_id=? ORDER BY character_id",(same_entry_id,)).fetchall()
        assert rows == [(90000001,3920000.0),(90000002,4080000.0)]
        c.execute("DELETE FROM wallet_entries WHERE entry_id=?",(same_entry_id,))
        c.execute("DELETE FROM characters WHERE character_id=90000002")


def test_hd_background_payload_is_complete_webp(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as c:
        r=c.get("/art/eve-bg.webp")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/webp")
        assert r.content[:4] == b"RIFF"
        assert r.content[8:12] == b"WEBP"
        assert int.from_bytes(r.content[4:8],"little")+8 == len(r.content)
        assert len(r.content) > 30000


def test_non_sold_escalation_value_is_cleared_by_backend(test_app):
    base=test_app["base_url"]
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=base,timeout=5) as c:
        r=c.post("/api/run/start",json={"anomaly":"Angel Hub","variant":"Default","participants":[90000001],"notes":""});rid=r.json()["run"]["id"]
        assert c.post(f"/api/run/{rid}/complete").status_code==200
        assert c.post(f"/api/run/{rid}/bonus",json={"escalation_name":"Angel Capital Staging","escalation_status":"Sold","escalation_sale_value":30000000}).status_code==200
        assert c.post(f"/api/run/{rid}/bonus",json={"escalation_name":"Angel Capital Staging","escalation_status":"Pending","escalation_sale_value":30000000}).status_code==200
        saved=c.get(f"/api/run/{rid}").json()["run"]
        assert saved["escalation_status"]=="Pending" and saved["escalation_sale_value"]==0
