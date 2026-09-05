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
