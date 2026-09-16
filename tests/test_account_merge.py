"""Regression coverage for merging an accidentally-created standalone account into an existing tracker account."""
import importlib
import os
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.getenv("ACCOUNT_TEST_POSTGRES_URL") else []))
def isolated_merge(monkeypatch, tmp_path, request):
    monkeypatch.setenv("TRACKER_DB_PATH", str(tmp_path / "account-merge.db"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("EVE_CALLBACK_URL", "https://testserver/callback")
    monkeypatch.setenv("EVE_CLIENT_ID", "test-client")
    pg_admin = None
    if request.param == "postgres":
        import psycopg
        import uuid
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        pg_admin = psycopg.connect(os.environ["ACCOUNT_TEST_POSTGRES_URL"], autocommit=True)
        database = "account_merge_test_" + uuid.uuid4().hex
        pg_admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        monkeypatch.setenv("DATABASE_URL", make_conninfo(os.environ["ACCOUNT_TEST_POSTGRES_URL"], dbname=database))
    import app
    app = importlib.reload(app)

    async def sync(cid):
        assert await app.row_char(cid) is not None

    monkeypatch.setattr(app, "sync_character", sync)
    yield app
    if pg_admin:
        pg_admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
        pg_admin.close()


def tracker_client(app):
    return TestClient(app.app, base_url="https://testserver", follow_redirects=False)


def authenticate(app, monkeypatch, client, cid, *, connect=False, owner=None):
    if connect:
        start = client.post("/connect")
        assert start.status_code == 200, start.text
        url = start.json()["url"]
    else:
        start = client.get("/login")
        assert start.status_code == 303, start.text
        url = start.headers["location"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    claims = {
        "sub": f"CHARACTER:EVE:{cid}",
        "owner": owner or f"owner-{cid}",
        "name": f"Pilot {cid}",
        "exp": int(time.time()) + 1200,
    }

    async def exchange(code, verifier):
        assert code == "valid-code" and len(verifier) >= 32
        return {"access_token": "secret-access", "refresh_token": "secret-refresh"}

    async def validate(token):
        assert token == "secret-access"
        return claims

    monkeypatch.setattr(app.accounts, "exchange", exchange)
    monkeypatch.setattr(app.accounts, "validate_token", validate)
    result = client.get("/callback", params={"code": "valid-code", "state": state})
    if result.status_code == 303:
        info = client.get("/api/account").json()
        client.headers["X-CSRF-Token"] = info["csrf"]
    return result


def test_clean_standalone_main_can_attach_to_existing_account(isolated_merge, monkeypatch):
    app = isolated_merge
    destination = tracker_client(app)
    source = tracker_client(app)

    assert authenticate(app, monkeypatch, destination, 1001).status_code == 303
    assert authenticate(app, monkeypatch, source, 2002).status_code == 303
    assert destination.get("/api/account").json()["id"] == 1
    assert source.get("/api/account").json()["id"] == 2
    stale_source_cookie = source.cookies.get("tracker_session")

    # This reproduces the production flow: the standalone character is now added
    # from the already-authenticated Main account.
    assert authenticate(app, monkeypatch, destination, 2002, connect=True).status_code == 303
    assert destination.get("/api/account").json()["id"] == 1
    chars = {c["id"]: c["role"] for c in destination.get("/api/dashboard").json()["characters"]}
    assert chars == {1001: "main", 2002: "alt"}

    with app.db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 1
        assert db.execute("SELECT COUNT(*) AS n FROM characters WHERE user_id=2").fetchone()["n"] == 0
        assert db.execute("SELECT COUNT(*) AS n FROM auth_sessions WHERE user_id=2").fetchone()["n"] == 0

    stale = tracker_client(app)
    stale.cookies.set("tracker_session", stale_source_cookie)
    assert stale.get("/api/dashboard").status_code == 401


def test_merge_preserves_source_history_characters_and_destination_main(isolated_merge, monkeypatch):
    app = isolated_merge
    destination = tracker_client(app)
    source = tracker_client(app)

    assert authenticate(app, monkeypatch, destination, 1001).status_code == 303
    assert authenticate(app, monkeypatch, source, 2002).status_code == 303
    assert authenticate(app, monkeypatch, source, 2003, connect=True).status_code == 303

    run = source.post("/api/run/start", json={"anomaly": "Angel Haven", "participants": [2002]}).json()
    rid, sid = run["run"]["id"], run["session_id"]
    assert source.post(f"/api/run/{rid}/complete").status_code == 200
    assert source.post(f"/api/run/{rid}/bonus", json={"notes": "SOURCE-RUN", "rare_spawn_value": 9876}).status_code == 200
    assert source.post("/api/session/end", json={"notes": "SOURCE-SESSION", "loot_value": 1234}).status_code == 200

    with app.db() as db:
        db.execute("INSERT INTO ess_events(user_id,character_id,entry_id,date,amount,session_id) VALUES(2,2002,7001,?,321,?)", (app.iso(), sid))
        db.execute("INSERT INTO wallet_entries(user_id,entry_id,character_id,date,amount,raw_json) VALUES(2,7002,2002,?,654,'{}')", (app.iso(),))
        db.execute("INSERT INTO skill_snapshots(user_id,character_id,captured_at,total_sp,skills_json,queue_json) VALUES(2,2002,?,777,'[]','[]')", (app.iso(),))
        source_counts = {table: db.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=2").fetchone()["n"] for table in app.OWNED_TABLES}

    stale_source_cookie = source.cookies.get("tracker_session")
    assert authenticate(app, monkeypatch, destination, 2002, connect=True).status_code == 303

    chars = {c["id"]: c["role"] for c in destination.get("/api/dashboard").json()["characters"]}
    assert chars == {1001: "main", 2002: "alt", 2003: "alt"}
    assert destination.get(f"/api/run/{rid}").json()["run"]["notes"] == "SOURCE-RUN"
    assert destination.get(f"/api/session/{sid}").json()["session"]["notes"] == "SOURCE-SESSION"

    with app.db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 1
        assert db.execute("SELECT primary_character_id FROM users WHERE id=1").fetchone()["primary_character_id"] == 1001
        assert db.execute("SELECT COUNT(*) AS n FROM characters WHERE user_id=1 AND character_role='main'").fetchone()["n"] == 1
        for table, count in source_counts.items():
            assert db.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=2").fetchone()["n"] == 0
            assert db.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=1").fetchone()["n"] >= count
        assert db.execute("SELECT amount FROM ess_events WHERE user_id=1 AND character_id=2002 AND entry_id=7001").fetchone()["amount"] == 321
        assert db.execute("SELECT amount FROM wallet_entries WHERE user_id=1 AND character_id=2002 AND entry_id=7002").fetchone()["amount"] == 654
        assert db.execute("SELECT total_sp FROM skill_snapshots WHERE user_id=1 AND character_id=2002 AND total_sp=777").fetchone()["total_sp"] == 777
        assert db.execute("SELECT COUNT(*) AS n FROM auth_sessions WHERE user_id=2").fetchone()["n"] == 0

    stale = tracker_client(app)
    stale.cookies.set("tracker_session", stale_source_cookie)
    assert stale.get("/api/dashboard").status_code == 401
