"""Account boundary, transactional legacy migration, and EVE SSO sessions."""
import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
from contextvars import ContextVar
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

account_context = ContextVar("account_id", default=None)
OWNED_TABLES = ("characters", "runs", "sessions", "ess_events", "wallet_entries", "skill_snapshots")
SUPABASE_API_ROLES = ("anon", "authenticated", "service_role")
COOKIE = "tracker_session"
SESSION_SECONDS = 60 * 60 * 24 * 14


def user_id():
    uid = account_context.get()
    if type(uid) is not int or uid <= 0:
        raise HTTPException(401, "Authentication required")
    return uid


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _pg_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def harden_postgres_schema(c, postgres):
    """Keep the direct-Postgres backend private from Supabase client API roles.

    RLS is enabled but not forced: the application's direct database role owns its
    tables and therefore keeps owner access, while Data API roles get no grants.
    Default privileges are also revoked so later migrations do not re-expose new
    tables, sequences, or functions before the next startup hardening pass.
    """
    if not postgres:
        return

    roles = {
        r["rolname"]
        for r in c.execute(
            "SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role')"
        ).fetchall()
    }
    tables = c.execute(
        """SELECT cls.relname
             FROM pg_class cls
             JOIN pg_namespace ns ON ns.oid=cls.relnamespace
            WHERE ns.nspname='public'
              AND cls.relkind IN ('r','p')
              AND cls.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
            ORDER BY cls.relname"""
    ).fetchall()
    sequences = c.execute(
        """SELECT cls.relname
             FROM pg_class cls
             JOIN pg_namespace ns ON ns.oid=cls.relnamespace
            WHERE ns.nspname='public'
              AND cls.relkind='S'
              AND cls.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
            ORDER BY cls.relname"""
    ).fetchall()

    for row in tables:
        table = _pg_ident(row["relname"])
        c.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        for role in roles:
            c.execute(f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM {_pg_ident(role)}")

    for row in sequences:
        sequence = _pg_ident(row["relname"])
        for role in roles:
            c.execute(f"REVOKE ALL PRIVILEGES ON SEQUENCE public.{sequence} FROM {_pg_ident(role)}")

    # This project owns the public schema for tracker data. Client-facing Supabase
    # roles must never execute public-schema functions directly. Revoke both global
    # and public-schema defaults: PostgreSQL applies global defaults before schema
    # defaults, so a schema-local REVOKE alone cannot cancel a global grant.
    for role in roles:
        role_ident = _pg_ident(role)
        c.execute(f"REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM {role_ident}")
        c.execute(f"ALTER DEFAULT PRIVILEGES REVOKE ALL ON TABLES FROM {role_ident}")
        c.execute(f"ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM {role_ident}")
        c.execute(f"ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM {role_ident}")
        c.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role_ident}")
        c.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role_ident}")
        c.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM {role_ident}")
    c.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    c.execute("ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")

    print(
        "PostgreSQL public schema hardened: "
        + json.dumps(
            {
                "rls_tables": [r["relname"] for r in tables],
                "sequences": [r["relname"] for r in sequences],
                "revoked_roles": sorted(roles),
            }
        ),
        flush=True,
    )


def migrate(c, postgres, ensure_col):
    """Run once, in the same transaction as schema initialization. Never claim on login."""
    if postgres:
        c.execute("SELECT pg_advisory_xact_lock(684294031)")
    serial = "BIGSERIAL" if postgres else "INTEGER"
    c.execute(f"CREATE TABLE IF NOT EXISTS users(id {serial} PRIMARY KEY,created_at BIGINT NOT NULL,primary_character_id BIGINT)")
    c.execute("CREATE TABLE IF NOT EXISTS account_migrations(version INTEGER PRIMARY KEY,completed_at BIGINT NOT NULL,summary_json TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),csrf_token TEXT NOT NULL,expires_at BIGINT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS account_sync_state(user_id BIGINT PRIMARY KEY REFERENCES users(id),last_attempt TEXT,last_success TEXT,last_error TEXT,next_check TEXT)")
    ensure_col(c, "users", "favorite_sites_json TEXT")
    ensure_col(c, "users", "last_site TEXT")
    for definition in ("browser_hash TEXT", "intent TEXT", "user_id BIGINT", "session_hash TEXT"):
        ensure_col(c, "oauth_states", definition)
    ensure_col(c, "characters", "owner_hash TEXT")
    for definition in ("cache_security DOUBLE PRECISION", "cache_affiliation TEXT", "location_updated_at TEXT"):
        ensure_col(c, "characters", definition)
    if not c.execute("SELECT 1 FROM account_migrations WHERE version=1").fetchone():
        if postgres:
            c.execute("LOCK TABLE characters,runs,sessions,ess_events,wallet_entries,skill_snapshots IN ACCESS EXCLUSIVE MODE")
        before = {t: c.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in OWNED_TABLES}
        chars = c.execute("SELECT * FROM characters ORDER BY connected_at,character_id").fetchall()
        if any(before.values()) and not chars:
            raise RuntimeError("Legacy data has no character identity; explicit administrator migration required")
        for table in OWNED_TABLES:
            ensure_col(c, table, "user_id BIGINT REFERENCES users(id)")
        if chars:
            mains = [r for r in chars if r["character_role"] == "main"]
            if len(mains) != 1:
                raise RuntimeError("Legacy migration requires exactly one explicit Main character")
            primary = mains[0]["character_id"]
            c.execute("INSERT INTO users(id,created_at,primary_character_id) VALUES(1,?,?)", (int(time.time()), primary))
            for table in OWNED_TABLES:
                c.execute(f"UPDATE {table} SET user_id=1 WHERE user_id IS NULL")
            # Existing server-held SSO tokens pin character ownership across EVE transfers.
            # They are trusted migration input, never tokens supplied by a browser.
            for ch in chars:
                if not ch["access_token"] and not ch["connected"]:
                    # Retired alts retain their history and ownership reservation.
                    # Only an authenticated owner may reconnect them later.
                    continue
                try:
                    claims = jwt.decode(ch["access_token"], options={"verify_signature": False})
                    owner = claims.get("owner")
                    if claims.get("sub") != f"CHARACTER:EVE:{ch['character_id']}" or not owner:
                        raise ValueError("Missing character identity")
                except Exception:
                    raise RuntimeError("Legacy character lacks an owner identity; administrator migration required") from None
                c.execute("UPDATE characters SET owner_hash=? WHERE character_id=?", (owner, ch["character_id"]))
            c.execute("INSERT INTO account_sync_state(user_id,last_attempt,last_success,last_error,next_check) SELECT 1,last_attempt,last_success,NULL,next_check FROM esi_sync_state WHERE id=1")
            if postgres:
                c.execute("SELECT setval(pg_get_serial_sequence('users','id'),1,true)")
        after = {t: c.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in OWNED_TABLES}
        if before != after:
            raise RuntimeError("Migration row count mismatch")
        c.execute("DELETE FROM oauth_states")
        # Cached ESI responses are disposable; old entries had no account boundary.
        c.execute("DELETE FROM esi_cache")
        c.execute("INSERT INTO account_migrations(version,completed_at,summary_json) VALUES(1,?,?)", (int(time.time()), json.dumps({"before": before, "after": after, "legacy_user_id": 1 if chars else None})))
        if chars:
            for table,count in before.items():
                if c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=1").fetchone()["n"] != count:
                    raise RuntimeError("Legacy account ownership verification failed")
        print("Account migration v1 verified: " + json.dumps({"legacy_user_id":1 if chars else None,"preserved_rows":after}), flush=True)
    for table in OWNED_TABLES:
        c.execute(f"CREATE INDEX IF NOT EXISTS {table}_user_idx ON {table}(user_id)")
        if postgres:
            c.execute(f"ALTER TABLE {table} ALTER COLUMN user_id SET NOT NULL")
        else:
            # SQLite cannot add NOT NULL to an existing populated column.
            for operation in ("INSERT", "UPDATE"):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_owner_{operation.lower()} BEFORE {operation} ON {table} WHEN NEW.user_id IS NULL OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.user_id) BEGIN SELECT RAISE(ABORT,'Account ownership required'); END")
    harden_postgres_schema(c, postgres)


def create_session(c, uid):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    c.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (int(time.time()),))
    c.execute("INSERT INTO auth_sessions(token_hash,user_id,csrf_token,expires_at) VALUES(?,?,?,?)", (digest(token), uid, csrf, int(time.time()) + SESSION_SECONDS))
    return token, csrf


class Accounts:
    def __init__(self, db, client_id, client_secret, callback_url, scopes):
        self.db, self.client_id, self.client_secret = db, client_id, client_secret
        self.callback_url, self.scopes = callback_url, scopes
        url = urlsplit(callback_url)
        self.origin = f"{url.scheme}://{url.netloc}"
        self.secure = bool(os.getenv("RENDER")) or url.scheme == "https"
        self.jwks = jwt.PyJWKClient("https://login.eveonline.com/oauth/jwks", timeout=15)

    def session(self, request):
        raw = request.cookies.get(COOKIE, "")
        if not raw:
            return None
        with self.db() as c:
            r = c.execute("SELECT s.*,u.primary_character_id FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires_at>?", (digest(raw), int(time.time()))).fetchone()
        return dict(r) if r else None

    async def middleware(self, request, call_next):
        path = request.url.path
        public = path in ("/login", "/callback", "/health") or path.startswith(("/static/", "/art/"))
        session = self.session(request)
        request.state.account = session
        if not public and not session:
            if path.startswith("/api/") or request.method != "GET":
                response = JSONResponse({"detail": "Authentication required"}, 401)
            else:
                response = HTMLResponse('<!doctype html><html><head><title>EVE Ratting Tracker</title><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="background:#08111d;color:#e7edf7;font-family:system-ui;display:grid;place-items:center;min-height:95vh"><main><h1>EVE Ratting Tracker</h1><p>Your characters. Your private tracker.</p><a style="color:#7dcfff" href="/login">Log in with EVE Online</a></main></body></html>')
        elif not public and request.method not in ("GET", "HEAD", "OPTIONS") and not self.csrf_ok(request, session):
            response = JSONResponse({"detail": "Invalid CSRF token"}, 403)
        else:
            context = account_context.set(int(session["user_id"]) if session else None)
            try:
                response = await call_next(request)
            finally:
                account_context.reset(context)
        if not path.startswith(("/static/", "/art/")):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Vary"] = "Cookie"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if self.secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def csrf_ok(self, request, session):
        origin = request.headers.get("origin")
        if origin and origin != self.origin:
            return False
        return bool(session and secrets.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf_token"]))

    def bootstrap(self, request):
        session = request.state.account
        return {"id": session["user_id"], "csrf": session["csrf_token"]}

    async def begin(self, request, intent="login"):
        session = self.session(request)
        if intent == "connect" and not session:
            raise HTTPException(401, "Authentication required")
        if intent == "login" and session:
            return RedirectResponse("/", 303)
        if not self.client_id:
            return HTMLResponse("EVE login is not configured. Contact the administrator.", 503)
        state, browser, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        with self.db() as c:
            c.execute("DELETE FROM oauth_states WHERE created_at<?", (int(time.time()) - 600,))
            c.execute("INSERT INTO oauth_states(state,created_at,code_verifier,browser_hash,intent,user_id,session_hash) VALUES(?,?,?,?,?,?,?)", (digest(state), int(time.time()), verifier, digest(browser), intent, session["user_id"] if session else None, session["token_hash"] if session else None))
        response = RedirectResponse("https://login.eveonline.com/v2/oauth/authorize/?" + urlencode({"response_type": "code", "redirect_uri": self.callback_url, "client_id": self.client_id, "scope": " ".join(self.scopes), "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}), 303)
        if intent == "connect":
            response = JSONResponse({"url": response.headers["location"]})
        response.set_cookie("tracker_oauth", browser, httponly=True, secure=self.secure, samesite="lax", max_age=600, path="/callback")
        return response

    async def validate_token(self, token):
        key = await asyncio.to_thread(self.jwks.get_signing_key_from_jwt, token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=self.client_id, options={"require": ["exp", "iat", "sub", "iss", "aud", "owner"]})
        if claims["iss"] not in ("login.eveonline.com", "https://login.eveonline.com") or "EVE Online" not in claims["aud"] or claims.get("azp") != self.client_id or not claims["owner"]:
            raise ValueError("Invalid EVE token claims")
        if not claims["sub"].startswith("CHARACTER:EVE:"):
            raise ValueError("Invalid EVE subject")
        int(claims["sub"].rsplit(":", 1)[1])
        return claims

    async def exchange(self, code, verifier):
        data = {"grant_type": "authorization_code", "code": code, "redirect_uri": self.callback_url, "code_verifier": verifier, "client_id": self.client_id}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://login.eveonline.com/v2/oauth/token", data=data, auth=(self.client_id, self.client_secret) if self.client_secret else None)
            r.raise_for_status()
            return r.json()

    def merge_account(self, c, source_uid, destination_uid, authenticated_cid):
        """Merge a duplicate account only after its Main character has just passed EVE SSO."""
        source_uid, destination_uid, authenticated_cid = int(source_uid), int(destination_uid), int(authenticated_cid)
        if source_uid == destination_uid:
            return
        source = c.execute("SELECT primary_character_id,favorite_sites_json,last_site FROM users WHERE id=?", (source_uid,)).fetchone()
        destination = c.execute("SELECT primary_character_id,favorite_sites_json,last_site FROM users WHERE id=?", (destination_uid,)).fetchone()
        if not source or not destination:
            raise HTTPException(409, "Account connection changed; please try again")
        if int(source["primary_character_id"] or 0) != authenticated_cid:
            raise HTTPException(409, "This character belongs to another tracker account. Connect that account's Main character to merge it.")
        if not destination["primary_character_id"]:
            raise RuntimeError("Destination account has no Main character")
        owner_row = c.execute("SELECT user_id FROM characters WHERE character_id=?", (authenticated_cid,)).fetchone()
        if not owner_row or int(owner_row["user_id"]) != source_uid:
            raise HTTPException(409, "Account connection changed; please try again")

        # Preserve lightweight tracker preferences when two authenticated accounts merge.
        def _favorites(row):
            try:
                values=json.loads(row["favorite_sites_json"] or "[]")
            except Exception:
                values=[]
            return [str(x) for x in values if isinstance(x,str)]

        merged_favorites=[]
        for anomaly in _favorites(destination)+_favorites(source):
            if anomaly not in merged_favorites:
                merged_favorites.append(anomaly)
        merged_last_site=destination["last_site"] or source["last_site"]
        c.execute("UPDATE users SET favorite_sites_json=?,last_site=? WHERE id=?",
                  (json.dumps(merged_favorites,separators=(",",":")),merged_last_site,destination_uid))

        source_before = {table: c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=?", (source_uid,)).fetchone()["n"] for table in OWNED_TABLES}
        destination_before = {table: c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=?", (destination_uid,)).fetchone()["n"] for table in OWNED_TABLES}
        for table in OWNED_TABLES:
            c.execute(f"UPDATE {table} SET user_id=? WHERE user_id=?", (destination_uid, source_uid))

        # The destination account keeps its explicit Main. Source Main/alt roles become alts.
        destination_main = int(destination["primary_character_id"])
        c.execute("UPDATE characters SET character_role='alt' WHERE user_id=?", (destination_uid,))
        c.execute("UPDATE characters SET character_role='main' WHERE user_id=? AND character_id=?", (destination_uid, destination_main))
        main_count = c.execute("SELECT COUNT(*) AS n FROM characters WHERE user_id=? AND character_role='main'", (destination_uid,)).fetchone()["n"]
        if main_count != 1:
            raise RuntimeError("Account merge could not preserve destination Main")

        # Sync state is disposable metadata; keep whichever account attempted sync most recently.
        source_sync = c.execute("SELECT * FROM account_sync_state WHERE user_id=?", (source_uid,)).fetchone()
        destination_sync = c.execute("SELECT * FROM account_sync_state WHERE user_id=?", (destination_uid,)).fetchone()
        if source_sync:
            if destination_sync:
                if (source_sync["last_attempt"] or "") > (destination_sync["last_attempt"] or ""):
                    c.execute("UPDATE account_sync_state SET last_attempt=?,last_success=?,last_error=?,next_check=? WHERE user_id=?", (source_sync["last_attempt"],source_sync["last_success"],source_sync["last_error"],source_sync["next_check"],destination_uid))
                c.execute("DELETE FROM account_sync_state WHERE user_id=?", (source_uid,))
            else:
                c.execute("UPDATE account_sync_state SET user_id=? WHERE user_id=?", (destination_uid, source_uid))

        # Revoke every source-account browser and pending OAuth flow. Private ESI cache is safe to rebuild.
        c.execute("DELETE FROM auth_sessions WHERE user_id=?", (source_uid,))
        c.execute("DELETE FROM oauth_states WHERE user_id=?", (source_uid,))
        c.execute("DELETE FROM esi_cache WHERE cache_key LIKE ?", (f"user:{source_uid}:%",))

        for table in OWNED_TABLES:
            source_after = c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=?", (source_uid,)).fetchone()["n"]
            destination_after = c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=?", (destination_uid,)).fetchone()["n"]
            if source_after != 0 or destination_after != source_before[table] + destination_before[table]:
                raise RuntimeError(f"Account merge ownership verification failed for {table}")

        c.execute("DELETE FROM users WHERE id=?", (source_uid,))
        if c.execute("SELECT 1 FROM users WHERE id=?", (source_uid,)).fetchone():
            raise RuntimeError("Duplicate account could not be retired")
        print("Account merge verified: " + json.dumps({"source_user_id":source_uid,"destination_user_id":destination_uid,"moved_rows":source_before}), flush=True)

    async def callback(self, request, code, state):
        browser = request.cookies.get("tracker_oauth", "")
        with self.db() as c:
            # Atomic consume prevents concurrent replay, including across server processes.
            row = c.execute("DELETE FROM oauth_states WHERE state=? AND browser_hash=? AND created_at>? RETURNING *", (digest(state), digest(browser), int(time.time()) - 600)).fetchone()
        if not row or not browser or not code:
            raise HTTPException(400, "Invalid or expired OAuth state")
        session = self.session(request)
        if row["intent"] == "connect" and (not session or session["user_id"] != row["user_id"] or session["token_hash"] != row["session_hash"]):
            raise HTTPException(400, "Connection session expired; please start again")
        if row["intent"] == "login" and session:
            raise HTTPException(400, "Account changed; please start again")
        try:
            tokens = await self.exchange(code, row["code_verifier"])
            claims = await self.validate_token(tokens["access_token"])
            cid = int(claims["sub"].rsplit(":", 1)[1])
        except Exception:
            raise HTTPException(400, "EVE authentication failed; please try again") from None
        with self.db() as c:
            if hasattr(c, "conn"):
                c.execute("SELECT pg_advisory_xact_lock(684294032)")
            existing = c.execute("SELECT user_id,owner_hash,character_role FROM characters WHERE character_id=?", (cid,)).fetchone()
            reconnect_reserved = bool(existing and not existing["owner_hash"] and row["intent"] == "connect" and existing["user_id"] == row["user_id"])
            if existing and not reconnect_reserved and (not existing["owner_hash"] or not secrets.compare_digest(existing["owner_hash"], claims["owner"])):
                raise HTTPException(409, "This character cannot be used for this account")
            if row["intent"] == "connect":
                uid = int(row["user_id"])
                if existing and existing["user_id"] != uid:
                    self.merge_account(c, existing["user_id"], uid, cid)
            elif existing:
                uid = int(existing["user_id"])
            else:
                uid = c.execute("INSERT INTO users(created_at,primary_character_id) VALUES(?,?) RETURNING id", (int(time.time()), cid)).fetchone()["id"]
            main = c.execute("SELECT primary_character_id FROM users WHERE id=?", (uid,)).fetchone()["primary_character_id"]
            role = "main" if main == cid else "alt"
            now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            c.execute("INSERT INTO characters(user_id,character_id,owner_hash,name,access_token,refresh_token,expires_at,connected_at,character_role,connected) VALUES(?,?,?,?,?,?,?,?,?,1) ON CONFLICT(character_id) DO UPDATE SET name=excluded.name,owner_hash=excluded.owner_hash,access_token=excluded.access_token,refresh_token=excluded.refresh_token,expires_at=excluded.expires_at,connected=1,character_role=excluded.character_role WHERE characters.user_id=excluded.user_id AND (characters.owner_hash=excluded.owner_hash OR characters.owner_hash IS NULL)", (uid,cid,claims["owner"],claims.get("name",str(cid)),tokens["access_token"],tokens["refresh_token"],int(claims["exp"]),now,role))
            c.execute("INSERT INTO account_sync_state(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING", (uid,))
            if session:
                c.execute("DELETE FROM auth_sessions WHERE token_hash=?", (session["token_hash"],))
            raw, _ = create_session(c, uid)
        request.state.authenticated_user = uid
        request.state.authenticated_character = cid
        response = RedirectResponse("/", 303)
        response.set_cookie(COOKIE, raw, httponly=True, secure=self.secure, samesite="lax", max_age=SESSION_SECONDS, path="/")
        response.delete_cookie("tracker_oauth", path="/callback", secure=self.secure, httponly=True, samesite="lax")
        return response

    async def logout(self, request):
        with self.db() as c:
            c.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest(request.cookies.get(COOKIE, "")),))
            c.execute("DELETE FROM oauth_states WHERE session_hash=?", (digest(request.cookies.get(COOKIE, "")),))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/", secure=self.secure, httponly=True, samesite="lax")
        response.delete_cookie("tracker_access", path="/")
        response.headers["Clear-Site-Data"] = '"cache", "storage"'
        return response
