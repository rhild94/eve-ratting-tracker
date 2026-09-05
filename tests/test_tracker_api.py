import httpx


def test_local_run_lifecycle_and_bonus_persistence(test_app):
    base = test_app["base_url"]
    with httpx.Client(base_url=base, timeout=5) as c:
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
    with httpx.Client(base_url=base, timeout=5) as c:
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
    with httpx.Client(base_url=base, timeout=5) as c:
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
    with httpx.Client(base_url=base, timeout=5) as c:
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
            "UPDATE esi_sync_state SET last_attempt=?,last_success=?,last_error=?,next_check=? WHERE id=1",
            ("2026-09-05T12:00:00+00:00", "2026-09-05T11:30:00+00:00",
             "simulated ESI outage", "2026-09-05T12:30:00+00:00"),
        )
    with httpx.Client(base_url=test_app["base_url"], timeout=5) as c:
        e = c.get("/api/dashboard").json()["esi"]
        assert e["interval_minutes"] == 30
        assert e["last_error"] == "simulated ESI outage"
        assert e["last_success"] == "2026-09-05T11:30:00+00:00"
        assert e["next_check"] == "2026-09-05T12:30:00+00:00"


def test_delete_completed_run_returns_promptly(test_app):
    import time
    base = test_app["base_url"]
    with httpx.Client(base_url=base, timeout=5) as c:
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
    with httpx.Client(base_url=test_app["base_url"], timeout=5) as c:
        r = c.get("/progression")
        assert r.status_code == 200
        assert "Character Progression" in r.text


def test_session_update_api(test_app):
    base = test_app["base_url"]
    with httpx.Client(base_url=base, timeout=5) as c:
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
        c.execute("INSERT INTO skill_snapshots(character_id,captured_at,total_sp,skills_json,queue_json) VALUES(?,?,?,?,?)",
                  (90000001, "2026-09-05T12:00:00+00:00", 1234567,
                   json.dumps([{"skill_id":3300,"trained_skill_level":3}]),
                   json.dumps([{"skill_id":3300,"finished_level":4,"finish_date":"2026-09-06T12:00:00Z"}])))
    with httpx.Client(base_url=test_app["base_url"], timeout=5) as c:
        r = c.get("/progression")
        assert r.status_code == 200
        assert "1,234,567 SP" in r.text
        assert "Gunnery" in r.text


def test_ess_history_shows_character_name_without_assignment_controls(test_app):
    import sqlite3
    db = test_app["work"] / "ratting_tracker.db"
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO ess_events(entry_id,character_id,date,amount) VALUES(?,?,?,?)",
                  (999001,90000001,"2026-09-05T06:25:00+00:00",12230000))
    with httpx.Client(base_url=test_app["base_url"], timeout=5) as c:
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
    with httpx.Client(base_url=base, timeout=5) as c:
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
        with httpx.Client(base_url=base, timeout=10) as c:
            results["delete"] = c.delete(f"/api/session/{sid}")

    def do_start():
        gate.wait()
        time.sleep(0.02)
        with httpx.Client(base_url=base, timeout=10) as c:
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
