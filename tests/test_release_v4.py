import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
from playwright.sync_api import expect


def base_url(page):
    u = page.url
    for marker in ["/dashboard", "/history", "/progression", "/?"]:
        if marker in u:
            u = u.split(marker)[0]
    return u.rstrip("/")


def upsert_alt(test_app, cid=90000002, name="Second Pilot", connected=1):
    db = test_app["work"] / "ratting_tracker.db"
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db) as c:
        c.execute(
            """INSERT INTO characters(user_id,
                character_id,name,access_token,refresh_token,expires_at,connected_at,
                cache_system_name,cache_ship_name,last_esi_sync,character_role,connected
            ) VALUES(1,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(character_id) DO UPDATE SET
                name=excluded.name,access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,expires_at=excluded.expires_at,
                connected_at=excluded.connected_at,cache_system_name=excluded.cache_system_name,
                cache_ship_name=excluded.cache_ship_name,last_esi_sync=excluded.last_esi_sync,
                character_role=excluded.character_role,connected=excluded.connected""",
            (cid, name, "fake-token-2", "fake-refresh-2", 4102444800, now,
             "W-16DY", "Praxis", now, "alt", connected),
        )
    return cid


def test_history_pagination_income_rendering_and_visualizations(page, test_app):
    db = test_app["work"] / "ratting_tracker.db"
    now = datetime.now(timezone.utc)
    with sqlite3.connect(db) as c:
        for i in range(35):
            start = now - timedelta(hours=3, minutes=i * 2 + 1)
            end = start + timedelta(minutes=1)
            cur = c.execute(
                "INSERT INTO sessions(user_id,started_at,ended_at,status,loot_value,salvage_value,notes) VALUES(1,?,?,'complete',0,0,'')",
                (start.isoformat(), end.isoformat()),
            )
            sid = cur.lastrowid
            c.execute(
                """INSERT INTO runs(user_id,
                    anomaly,variant,started_at,ended_at,participants_json,notes,status,
                    combined_bounty,system_name,ships_json,session_id,escalation_name,
                    escalation_status,escalation_sale_value,rare_spawn_type,rare_spawn_value,
                    paused_seconds,esi_synced_at
                ) VALUES(1,?,?,?,?,?,?, 'complete',?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "Angel Hub", "Default", start.isoformat(), end.isoformat(), "[90000001]", "",
                    1_000_000 + i, "W-16DY", "[]", sid,
                    "Angel Cartel Naval Shipyard" if i == 0 else None,
                    "Sold" if i == 0 else None,
                    123_000_000 if i == 0 else 0,
                    None, 0, 0, end.isoformat(),
                ),
            )
    page.goto(base_url(page) + "/history?days=7")
    expect(page.locator('[data-pagination="runs"]')).to_contain_text("Page 1 of 2")
    expect(page.locator('[data-pagination="sessions"]')).to_contain_text("Page 1 of 2")
    expect(page.locator(".history-metrics .metric-card").first.locator("b")).to_have_text("35")
    expect(page.locator(".escalation-list")).to_contain_text("123M ISK")
    expect(page.locator(".history-main tbody tr")).to_have_count(30)
    expect(page.locator("#chart")).to_be_visible()
    expect(page.locator("#chartTooltip")).to_have_count(1)
    expect(page.locator(".income-legend")).to_contain_text("Lower ISK")
    expect(page.locator(".income-legend")).to_contain_text("Higher ISK")
    colors = page.evaluate("() => [incomeColor(0).css, incomeColor(100000000).css]")
    assert colors[0] != colors[1]
    page.locator('[data-pagination="runs"] a').filter(has_text="Next").click()
    expect(page).to_have_url(re.compile(r"run_page=2"))
    expect(page.locator(".history-main tbody tr")).to_have_count(5)


def test_progression_luck_statistics_render_from_all_recent_sites(page, test_app):
    db = test_app["work"] / "ratting_tracker.db"
    now = datetime.now(timezone.utc)
    rare = ["Commander", "Dreadnought", "Titan", "Other"]
    with sqlite3.connect(db) as c:
        for i in range(4):
            start = now - timedelta(minutes=20 + i * 3)
            end = start + timedelta(minutes=2)
            c.execute(
                """INSERT INTO runs(user_id,
                    anomaly,variant,started_at,ended_at,participants_json,notes,status,
                    combined_bounty,system_name,ships_json,escalation_name,escalation_status,
                    escalation_sale_value,rare_spawn_type,rare_spawn_value,paused_seconds,
                    esi_synced_at
                ) VALUES(1,?,?,?,?,?,?, 'complete',?,?,?,?,?,?,?,?,?,?)""",
                (
                    "Angel Hub", "Default", start.isoformat(), end.isoformat(), "[90000001]", "",
                    10_000_000, "W-16DY", "[]",
                    "Angel Cartel Naval Shipyard" if i < 2 else None,
                    "Pending" if i < 2 else None, 0,
                    rare[i], (i + 1) * 1_000_000, 0, end.isoformat(),
                ),
            )
    page.goto(base_url(page) + "/progression?days=7")
    expect(page.locator("#sitePerformanceV3")).to_be_visible()
    luck = page.locator(".luck-section")
    expect(luck).to_be_visible()
    expect(luck).to_contain_text("Total dropped")
    expect(luck).to_contain_text("50.0%")
    expect(luck).to_contain_text("Angel Cartel Naval Shipyard")
    for label in rare:
        expect(luck).to_contain_text(label)
    expect(luck).to_contain_text("10M ISK")
    expect(page.locator(".skill-snapshot")).to_have_count(0)


def test_remove_character_preserves_historical_run(page, test_app):
    cid = upsert_alt(test_app)
    db = test_app["work"] / "ratting_tracker.db"
    now = datetime.now(timezone.utc)
    with sqlite3.connect(db) as c:
        c.execute(
            """INSERT INTO runs(user_id,
                anomaly,variant,started_at,ended_at,participants_json,notes,status,
                combined_bounty,system_name,ships_json,paused_seconds,esi_synced_at
            ) VALUES(1,?,?,?,?,?,?, 'complete',?,?,?,?,?)""",
            ("Angel Hub", "Default", (now-timedelta(minutes=2)).isoformat(), now.isoformat(),
             json.dumps([cid]), "historical-alt-run", 12_000_000, "W-16DY", "[]", 0,
             now.isoformat()),
        )
        rid = c.execute("SELECT id FROM runs WHERE notes='historical-alt-run'").fetchone()[0]
    page.goto(base_url(page) + "/progression?view=characters")
    card = page.locator(".character-card-xl").filter(has_text="Second Pilot")
    expect(card).to_be_visible()
    page.once("dialog", lambda d: d.accept())
    card.locator("button").filter(has_text="Remove Character").click()
    expect(page.locator(".character-card-xl").filter(has_text="Second Pilot")).to_have_count(0)
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM runs WHERE id=?", (rid,)).fetchone()[0] == 1
        assert c.execute("SELECT connected FROM characters WHERE character_id=?", (cid,)).fetchone()[0] == 0


def test_both_characters_ess_are_aggregated_without_key_collision(test_app):
    cid2 = upsert_alt(test_app)
    db = test_app["work"] / "ratting_tracker.db"
    now = datetime.now(timezone.utc)
    try:
        with sqlite3.connect(db) as c:
            c.execute("DELETE FROM wallet_entries")
            c.execute(
                "INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json) VALUES(1,?,?,?,?,?,?,?,?)",
                (777, 90000001, now.isoformat(), 10_000_000, 0, "ess_escrow_transfer", "", "{}"),
            )
            c.execute(
                "INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,balance,ref_type,description,raw_json) VALUES(1,?,?,?,?,?,?,?,?)",
                (777, cid2, now.isoformat(), 20_000_000, 0, "ess_escrow_transfer", "", "{}"),
            )
        with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app["base_url"], timeout=5) as client:
            dash = client.get("/api/dashboard").json()
            assert dash["stats"]["today_ess"] == 30_000_000

            started = client.post("/api/run/start", json={
                "anomaly": "Angel Hub", "variant": "Default",
                "participants": [90000001, cid2], "notes": "ess aggregation"
            }).json()
            sid = started["session_id"]
            rid = started["run"]["id"]
            assert client.post(f"/api/run/{rid}/complete").status_code == 200
            assert client.post("/api/session/end", json={"loot_value": 0, "salvage_value": 0, "notes": ""}).status_code == 200

            with sqlite3.connect(db) as c:
                c.execute(
                    "INSERT INTO ess_events(user_id,entry_id,character_id,date,amount,session_id,match_status) VALUES(1,?,?,?,?,?,'manual')",
                    (888, 90000001, now.isoformat(), 3_000_000, sid),
                )
                c.execute(
                    "INSERT INTO ess_events(user_id,entry_id,character_id,date,amount,session_id,match_status) VALUES(1,?,?,?,?,?,'manual')",
                    (888, cid2, now.isoformat(), 4_000_000, sid),
                )
            html = client.get("/dashboard?days=7").text
            m = re.search(r"window\.__BOOTSTRAP__=(.*?);</script>", html, re.S)
            assert m, "dashboard bootstrap missing"
            perf = json.loads(m.group(1))["perf"]
            row = next(x for x in perf["rows"] if x["id"] == sid)
            assert row["ess"] == 7_000_000
            assert row["ratting_isk"] >= 7_000_000
    finally:
        with sqlite3.connect(db) as c:
            c.execute("UPDATE characters SET connected=0,character_role='alt' WHERE character_id=?", (cid2,))
            c.execute("DELETE FROM wallet_entries WHERE character_id=?", (cid2,))
