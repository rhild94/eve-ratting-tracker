"""Exercise real session middleware and ownership boundaries; only EVE is mocked."""
import asyncio
import importlib
import json
import os
import re
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.getenv("ACCOUNT_TEST_POSTGRES_URL") else []))
def isolated(monkeypatch, tmp_path, request):
    monkeypatch.setenv("TRACKER_DB_PATH", str(tmp_path / "accounts.db"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("EVE_CALLBACK_URL", "https://testserver/callback")
    monkeypatch.setenv("EVE_CLIENT_ID", "test-client")
    pg_admin=None
    if request.param == "postgres":
        import psycopg
        import uuid
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        pg_admin=psycopg.connect(os.environ["ACCOUNT_TEST_POSTGRES_URL"],autocommit=True)
        database="accounts_test_"+uuid.uuid4().hex
        pg_admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        monkeypatch.setenv("DATABASE_URL",make_conninfo(os.environ["ACCOUNT_TEST_POSTGRES_URL"],dbname=database))
    import app
    app = importlib.reload(app)
    async def sync(cid):
        assert await app.row_char(cid) is not None
    app.real_sync_character=app.sync_character
    monkeypatch.setattr(app, "sync_character", sync)
    yield app
    if pg_admin:
        pg_admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
        pg_admin.close()


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
    claims = {"sub":f"CHARACTER:EVE:{cid}","owner":owner or f"owner-{cid}","name":f"Pilot {cid}","exp":int(time.time())+1200}
    async def exchange(code, verifier):
        assert code == "valid-code" and len(verifier) >= 32
        return {"access_token":"secret-access", "refresh_token":"secret-refresh"}
    async def validate(token):
        assert token == "secret-access"
        return claims
    monkeypatch.setattr(app.accounts, "exchange", exchange)
    monkeypatch.setattr(app.accounts, "validate_token", validate)
    result = client.get("/callback", params={"code":"valid-code","state":state})
    if result.status_code == 303:
        info = client.get("/api/account").json()
        client.headers["X-CSRF-Token"] = info["csrf"]
    return result


def client(app):
    return TestClient(app.app, base_url="https://testserver", follow_redirects=False)


def boot(c, path):
    r = c.get(path)
    assert r.status_code == 200, r.text
    return json.loads(re.search(r'window\.__BOOTSTRAP__=(.*?);</script>',r.text,re.S)[1])


def start(c, cid, **extra):
    return c.post("/api/run/start",json={"anomaly":"Angel Haven","participants":[cid],**extra})


def test_cross_user_all_resource_boundaries_and_empty_account(isolated, monkeypatch):
    app=isolated
    a,b=client(app),client(app)
    assert authenticate(app,monkeypatch,a,1001).status_code==303
    run=start(a,1001).json();rid=run["run"]["id"];sid=run["session_id"]
    assert a.post(f"/api/run/{rid}/complete").status_code==200
    assert a.post(f"/api/run/{rid}/bonus",json={"notes":"PRIVATE-A","rare_spawn_value":9876}).status_code==200
    assert a.post("/api/session/end",json={"notes":"PRIVATE-SESSION-A"}).status_code==200
    with app.db() as db:
        db.execute("INSERT INTO ess_events(user_id,character_id,entry_id,date,amount,session_id) VALUES(1,1001,77,?,123,?)",(app.iso(),sid))
        before={t:[dict(r) for r in db.execute(f"SELECT * FROM {t}")] for t in ("runs","sessions","ess_events","characters")}
    assert authenticate(app,monkeypatch,b,2002).status_code==303
    dash=b.get("/api/dashboard?user_id=1").json()
    assert dash["recent"]==[] and dash["active"] is None and dash["session"] is None
    assert dash["stats"]["today_isk"]==dash["stats"]["today_ess"]==0
    assert [c["id"] for c in dash["characters"]]==[2002]
    for path in ("/", "/history?analytics=1", "/dashboard", "/progression", "/progression?view=characters", "/?view=settings"):
        r=b.get(path);assert "PRIVATE-A" not in r.text and "PRIVATE-SESSION-A" not in r.text and "Pilot 1001" not in r.text
    for method,path,payload in [
        ("GET",f"/api/run/{rid}",None), ("DELETE",f"/api/run/{rid}",None),
        ("POST",f"/api/run/{rid}/bonus",{"notes":"stolen","user_id":1}),
        ("POST",f"/api/run/{rid}/pause",{}), ("POST",f"/api/run/{rid}/complete",{}),
        ("GET",f"/api/session/{sid}",None), ("POST",f"/api/session/{sid}",{"notes":"stolen"}),
        ("DELETE",f"/api/session/{sid}",None), ("DELETE","/api/character/1001",None),
        ("POST","/api/character/1001/main",{}),
    ]:
        r=b.request(method,path,json=payload)
        assert r.status_code==404,(path,r.text)
    assert start(b,1001,user_id=1).status_code==404
    assert b.post("/ess/77/assign",data={"session_id":sid,"character_id":1001}).status_code==404
    b_run=start(b,2002,user_id=1).json()
    assert b_run["run"]["user_id"]==2
    with app.db() as db:
        db.execute("INSERT INTO ess_events(user_id,character_id,entry_id,date,amount) VALUES(2,2002,88,?,456)",(app.iso(),))
    assert b.post("/ess/88/assign",data={"session_id":sid}).status_code==404
    called=[]
    async def sync(cid):called.append(cid)
    monkeypatch.setattr(app,"sync_character",sync)
    assert b.post("/api/sync",json={"user_id":1,"character_id":1001}).status_code==200
    assert called==[2002]
    with app.db() as db:
        for t,rows in before.items():
            assert [dict(r) for r in db.execute(f"SELECT * FROM {t} WHERE user_id=1")]==rows,t
    assert a.get(f"/api/run/{rid}").json()["run"]["notes"]=="PRIVATE-A"


def test_login_connect_main_logout_and_csrf(isolated,monkeypatch):
    app=isolated;a=client(app);b=client(app)
    assert a.get("/api/dashboard").status_code==401
    assert "Log in with EVE Online" in a.get("/").text
    assert a.post("/access",data={"key":"old-key"}).status_code==401
    response=authenticate(app,monkeypatch,a,1001)
    assert response.status_code==303
    cookie=response.headers.get_list("set-cookie")[0].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    old_cookie=a.cookies.get("tracker_session")
    assert authenticate(app,monkeypatch,a,1002,connect=True).status_code==303
    assert old_cookie!=a.cookies.get("tracker_session")
    with app.db() as db:assert db.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]==1
    assert [x["role"] for x in a.get("/api/dashboard").json()["characters"]]==["main","alt"]
    assert authenticate(app,monkeypatch,b,2002).status_code==303
    assert authenticate(app,monkeypatch,b,1002,connect=True).status_code==409
    csrf=a.headers.pop("X-CSRF-Token")
    assert start(a,1001).status_code==403
    a.headers["X-CSRF-Token"]=csrf
    assert a.post("/api/character/1002/main",headers={"Origin":"https://attacker.example"}).status_code==403
    assert a.post("/api/character/1002/main").status_code==200
    assert a.get("/setup").status_code==404 and a.post("/setup",data={"client_id":"evil"}).status_code==404
    cookie=a.cookies.get("tracker_session")
    assert a.post("/logout").status_code==200
    a.cookies.set("tracker_session",cookie)
    assert a.get("/api/dashboard").status_code==401
    a.cookies.clear()
    assert authenticate(app,monkeypatch,a,1002).status_code==303
    assert a.get("/api/account").json()["id"]==1
    assert "secret-access" not in a.get("/").text
    assert a.get("/history").headers["cache-control"]=="no-store, private"


def test_oauth_state_binding_expiry_replay_and_session_change(isolated,monkeypatch):
    app=isolated;a=client(app);b=client(app)
    r=a.get("/login");state=parse_qs(urlsplit(r.headers["location"]).query)["state"][0]
    assert b.get("/callback",params={"state":state,"code":"valid-code"}).status_code==400
    with app.db() as db:db.execute("UPDATE oauth_states SET created_at=0")
    assert a.get("/callback",params={"state":state,"code":"valid-code"}).status_code==400
    assert authenticate(app,monkeypatch,a,1001).status_code==303
    r=a.post("/connect");state=parse_qs(urlsplit(r.json()["url"]).query)["state"][0]
    assert a.get("/callback",params={"state":state,"code":"valid-code"}).status_code==303
    assert a.get("/callback",params={"state":state,"code":"valid-code"}).status_code==400
    # A connect started under a now-revoked session cannot attach to a new account.
    a.headers["X-CSRF-Token"]=a.get("/api/account").json()["csrf"]
    r=a.post("/connect");state=parse_qs(urlsplit(r.json()["url"]).query)["state"][0]
    assert a.post("/logout").status_code==200
    assert a.get("/callback",params={"state":state,"code":"valid-code"}).status_code==400


def test_character_transfer_cannot_take_over_private_account(isolated,monkeypatch):
    app=isolated;a=client(app);b=client(app)
    assert authenticate(app,monkeypatch,a,1001).status_code==303
    assert authenticate(app,monkeypatch,b,1001,owner="new-eve-owner").status_code==409
    assert b.get("/api/dashboard").status_code==401


def test_main_hud_and_scoped_private_cache(isolated,monkeypatch):
    app=isolated;a=client(app);b=client(app)
    authenticate(app,monkeypatch,a,1001);authenticate(app,monkeypatch,a,1002,connect=True);authenticate(app,monkeypatch,b,2002)
    with app.db() as db:
        db.execute("UPDATE characters SET cache_system_name='Main system',cache_security=-0.7,cache_affiliation='Main alliance' WHERE character_id=1001")
        db.execute("UPDATE characters SET cache_system_name='Alt system',cache_security=1 WHERE character_id=1002")
    assert a.get("/api/dashboard").json()["hud"]["system_name"]=="Main system"
    assert a.get("/api/dashboard").json()["hud"]["security_class"]=="Null Sec"
    assert b.get("/api/dashboard").json()["hud"]["system_name"] is None
    assert a.post("/api/character/1002/main").status_code==200
    assert a.get("/api/dashboard").json()["hud"]["system_name"]=="Alt system"
    async def exercise():
        context=app.account_context.set(1)
        try:
            with app.db() as db:
                db.execute("INSERT INTO esi_cache(cache_key,payload_json,expires_at,updated_at) VALUES(?,?,?,?)",('user:1:/characters/1001/location/?{}','{"solar_system_id":123}',"2099-01-01T00:00:00+00:00",app.iso()))
            assert (await app.esi_get('/characters/1001/location/',token='a'))["solar_system_id"]==123
            app.account_context.set(2)
            class NoNetwork:
                def __init__(self,**kwargs):raise RuntimeError("cache miss")
            monkeypatch.setattr(app.httpx,"AsyncClient",NoNetwork)
            with pytest.raises(RuntimeError,match="cache miss"):
                await app.esi_get('/characters/1001/location/',token='b')
            with pytest.raises(Exception):await app.sync_character(1001)
        finally:app.account_context.reset(context)
    monkeypatch.setattr(app,"sync_character",app.real_sync_character)
    asyncio.run(exercise())


def test_legacy_migration_preserves_rows_and_never_first_login_claim(isolated,monkeypatch,tmp_path):
    app=isolated
    real_migrate=app.migrate
    if app.USE_POSTGRES:
        # Recreate the legacy schema in this dedicated, disposable test database.
        with app.db() as db:
            db.execute("DROP SCHEMA public CASCADE")
            db.execute("CREATE SCHEMA public")
    monkeypatch.setattr(app,"DB",tmp_path/'legacy.db')
    monkeypatch.setattr(app,"migrate",lambda *args:None)
    app.init_db()
    token=jwt.encode({"sub":"CHARACTER:EVE:1001","owner":"owner-1001"},"migration-fixture-secret-32-bytes!!",algorithm="HS256")
    with app.db() as db:
        db.execute("INSERT INTO characters(character_id,name,access_token,refresh_token,expires_at,connected_at,character_role) VALUES(1001,'Rafael',?,'keep-refresh',9999999999,?,'main')",(token,app.iso()))
        db.execute("INSERT INTO sessions(id,started_at,ended_at,status,loot_value,notes) VALUES(7,?,?,'complete',12345,'legacy session')",(app.iso(),app.iso()))
        db.execute("INSERT INTO runs(id,anomaly,started_at,ended_at,participants_json,status,session_id,combined_bounty,paused_seconds,notes) VALUES(8,'Angel Haven',?,?,'[1001]','complete',7,54321,13,'legacy run')",(app.iso(),app.iso()))
        db.execute("INSERT INTO ess_events(entry_id,character_id,date,amount,session_id) VALUES(9,1001,?,333,7)",(app.iso(),))
        db.execute("INSERT INTO wallet_entries(entry_id,character_id,date,amount,raw_json) VALUES(10,1001,?,444,'{}')",(app.iso(),))
        db.execute("INSERT INTO skill_snapshots(character_id,captured_at,total_sp,skills_json,queue_json) VALUES(1001,?,123,'[]','[]')",(app.iso(),))
        tables=("characters","sessions","runs","ess_events","wallet_entries","skill_snapshots")
        before={t:[dict(r) for r in db.execute(f"SELECT * FROM {t}")] for t in tables}
    monkeypatch.setattr(app,"migrate",real_migrate)
    app.init_db();app.init_db()
    with app.db() as db:
        for t,rows in before.items():
            after=[dict(r) for r in db.execute(f"SELECT * FROM {t}")]
            assert len(rows)==len(after)
            for old,new in zip(rows,after):
                assert all(new[k]==v for k,v in old.items()),t
                assert new["user_id"]==1
    b=client(app);assert authenticate(app,monkeypatch,b,2002).status_code==303
    assert b.get("/api/dashboard").json()["recent"]==[]
    a=client(app);assert authenticate(app,monkeypatch,a,1001).status_code==303
    assert a.get("/api/run/8").json()["run"]["combined_bounty"]==54321
    assert a.get("/api/session/7").json()["session"]["loot_value"]==12345


def test_jwt_signature_issuer_audience_expiry_and_owner(isolated,monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from types import SimpleNamespace
    app=isolated
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    monkeypatch.setattr(app.accounts.jwks,"get_signing_key_from_jwt",lambda token:SimpleNamespace(key=key.public_key()))
    claims={"sub":"CHARACTER:EVE:1001","owner":"owner-a","iss":"https://login.eveonline.com","aud":["test-client","EVE Online"],"azp":"test-client","iat":int(time.time()),"exp":int(time.time())+600}
    assert asyncio.run(app.accounts.validate_token(jwt.encode(claims,key,algorithm="RS256")))["owner"]=="owner-a"
    for changes in ({"iss":"evil"},{"aud":["wrong","EVE Online"]},{"aud":["test-client"]},{"azp":"wrong"},{"exp":1},{"owner":""},{"sub":"wrong"}):
        with pytest.raises(Exception):asyncio.run(app.accounts.validate_token(jwt.encode({**claims,**changes},key,algorithm="RS256")))
    with pytest.raises(Exception):asyncio.run(app.accounts.validate_token(jwt.encode(claims,rsa.generate_private_key(public_exponent=65537,key_size=2048),algorithm="RS256")))
