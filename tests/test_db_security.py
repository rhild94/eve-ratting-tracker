"""Regression coverage for Supabase/PostgreSQL API-surface hardening."""
import importlib
import os
import uuid

import pytest


API_ROLES = ("anon", "authenticated", "service_role")


@pytest.mark.skipif(not os.getenv("ACCOUNT_TEST_POSTGRES_URL"), reason="PostgreSQL test server not configured")
def test_postgres_schema_stays_private_and_backend_keeps_owner_access(monkeypatch, tmp_path):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    base_dsn = os.environ["ACCOUNT_TEST_POSTGRES_URL"]
    admin = psycopg.connect(base_dsn, autocommit=True)
    database = "db_security_test_" + uuid.uuid4().hex

    # Supabase has these cluster roles. Create them on the disposable CI cluster
    # when needed so the regression test exercises the same grant paths.
    for role in API_ROLES:
        exists = admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
        if not exists:
            admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))

    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    target_dsn = make_conninfo(base_dsn, dbname=database)

    try:
        setup = psycopg.connect(target_dsn, autocommit=True)
        try:
            # Simulate permissive Supabase-style defaults before the tracker boots.
            for role in API_ROLES:
                ident = sql.Identifier(role)
                setup.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {}").format(ident))
                setup.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {}").format(ident))
                setup.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO {}").format(ident))
            setup.execute("CREATE TABLE public.preexisting_security_probe_table(id INTEGER PRIMARY KEY)")
            setup.execute("CREATE SEQUENCE public.preexisting_security_probe_seq")
            setup.execute("CREATE FUNCTION public.preexisting_security_probe() RETURNS INTEGER LANGUAGE SQL AS $$ SELECT 1 $$")
        finally:
            setup.close()

        monkeypatch.setenv("TRACKER_DB_PATH", str(tmp_path / "unused.db"))
        monkeypatch.setenv("DATABASE_URL", target_dsn)
        monkeypatch.setenv("EVE_CALLBACK_URL", "https://testserver/callback")
        monkeypatch.setenv("EVE_CLIENT_ID", "test-client")

        import app
        app = importlib.reload(app)

        expected_tables = {
            "account_migrations", "account_sync_state", "auth_sessions", "characters",
            "esi_cache", "esi_sync_state", "ess_events", "oauth_states", "runs",
            "sessions", "skill_snapshots", "type_names", "users", "wallet_entries",
            "preexisting_security_probe_table",
        }

        with app.db() as db:
            table_rows = db.execute(
                """SELECT cls.relname,cls.relrowsecurity
                     FROM pg_class cls
                     JOIN pg_namespace ns ON ns.oid=cls.relnamespace
                    WHERE ns.nspname='public'
                      AND cls.relkind IN ('r','p')
                      AND cls.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)"""
            ).fetchall()
            table_state = {r["relname"]: r["relrowsecurity"] for r in table_rows}
            assert expected_tables <= set(table_state)
            assert all(table_state[name] for name in expected_tables)

            grants = db.execute(
                """SELECT table_name,grantee,privilege_type
                     FROM information_schema.role_table_grants
                    WHERE table_schema='public'
                      AND grantee IN ('anon','authenticated','service_role')"""
            ).fetchall()
            assert grants == []

            sequence_grants = db.execute(
                """SELECT object_name,grantee,privilege_type
                     FROM information_schema.role_usage_grants
                    WHERE object_schema='public'
                      AND object_type='SEQUENCE'
                      AND grantee IN ('anon','authenticated','service_role')"""
            ).fetchall()
            assert sequence_grants == []

            for role in API_ROLES:
                allowed = db.execute(
                    "SELECT has_function_privilege(?, 'public.preexisting_security_probe()', 'EXECUTE') AS allowed",
                    (role,),
                ).fetchone()["allowed"]
                assert allowed is False

            # Objects created by a later migration inherit safe defaults immediately.
            db.execute("CREATE TABLE public.future_security_probe(id INTEGER PRIMARY KEY)")
            db.execute("CREATE SEQUENCE public.future_security_probe_seq")
            db.execute("CREATE FUNCTION public.future_security_probe() RETURNS INTEGER LANGUAGE SQL AS $$ SELECT 1 $$")
            for role in API_ROLES:
                assert db.execute(
                    "SELECT has_table_privilege(?, 'public.future_security_probe', 'SELECT') AS allowed",
                    (role,),
                ).fetchone()["allowed"] is False
                assert db.execute(
                    "SELECT has_sequence_privilege(?, 'public.future_security_probe_seq', 'USAGE') AS allowed",
                    (role,),
                ).fetchone()["allowed"] is False
                assert db.execute(
                    "SELECT has_function_privilege(?, 'public.future_security_probe()', 'EXECUTE') AS allowed",
                    (role,),
                ).fetchone()["allowed"] is False

            # RLS is intentionally not FORCEd. The backend's direct owning role can
            # continue to use PostgreSQL normally while client API roles stay locked out.
            db.execute("INSERT INTO type_names(type_id,name) VALUES(987654321,'Security Probe')")
            assert db.execute("SELECT name FROM type_names WHERE type_id=987654321").fetchone()["name"] == "Security Probe"

    finally:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))
        admin.close()
