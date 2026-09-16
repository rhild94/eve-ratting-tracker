# EVE Ratting Tracker

**Current version: 10.0.0**

Private development repository for the EVE Online ratting tracker.

## Local-first architecture

Ratting actions are saved locally and do not wait for ESI. ESI synchronization runs automatically in the background and can also be triggered manually. Local ratting actions never wait for ESI.

## Windows / clean install

Extract the package and double-click `RUN_TRACKER.bat`. The launcher creates its own Python environment, installs dependencies, opens the browser, and attempts to import an existing tracker `.env` automatically.

Configure `EVE_CLIENT_ID` and the registered `EVE_CALLBACK_URL` before starting. Set `EVE_CLIENT_SECRET` for a confidential EVE application; public applications use PKCE. Login uses EVE SSO. Each account owns its characters, runs, sessions, wallet/ESS events, progression, and sync state. Use **Connect Another Character** while logged in to attach an alt; select Main explicitly in Characters. The HUD uses only that Main's ESI location and affiliation. Ratting timers and saving remain independent of ESI availability.

The shared access key and web-based global configuration editor are retired. `APP_ACCESS_KEY` no longer grants access. Sessions are opaque, stored hashed in the database, expire after 14 days, and are revoked on logout. Cookies are HttpOnly, SameSite=Lax, and Secure for HTTPS/Render. Writes require a session-bound CSRF header. OAuth uses browser-bound, expiring, single-use state, PKCE, and signature/issuer/audience/expiry/character-owner validation.

## Existing production data

Schema initialization runs the account migration in one transaction. Before any login, all existing private rows are assigned to initial account 1 and the existing explicit Main is recorded. Existing server-held EVE token owner identities are pinned to prevent a subsequently transferred character from claiming history. Disconnected characters without tokens remain reserved to the initial account and can only be reconnected from that authenticated account. Ambiguous Main selection or missing identity for a connected character stops startup instead of assigning data to the first visitor. Row counts and ownership are checked, and `account_migrations` stores the audit. No tracked records or income fields are deleted or rewritten. Keep a database backup before upgrading; rollback after migration must use account-aware code, because older releases do not enforce ownership.

## Production database security

The hosted tracker uses a direct PostgreSQL `DATABASE_URL`; the browser never connects to Supabase directly. Keep the Supabase **Data API disabled** for this project and do not add Supabase client/service-role keys to the frontend.

On every PostgreSQL startup/migration the tracker now applies defense-in-depth hardening to the app-owned `public` schema: Row Level Security is enabled on every app-owned public table, all table/sequence privileges are revoked from Supabase client API roles (`anon`, `authenticated`, and `service_role`) when those roles exist, public-schema function execution is revoked from those roles and `PUBLIC`, and safe default privileges are installed for future tables, sequences, and functions. RLS is deliberately not forced, so the direct owning backend connection continues to work while client API roles remain unable to access tracker data.

This startup hardening is idempotent and runs after schema creation, so future application migrations are secured automatically. PostgreSQL regression tests simulate permissive Supabase defaults and verify the lockdown as well as continued backend read/write access.

Public `/health` returns only health and version. Private responses use `Cache-Control: no-store`. There are no corporation/group sharing features or administrative login bypasses.

Your runtime `.env`, `.venv`, and `ratting_tracker.db` stay local and are excluded from Git.

## Automated tests

```bash
python -m pip install -r requirements.txt -r requirements-test.txt
python -m playwright install chromium
python -m pytest tests -v
```

GitHub Actions runs the API and browser regression suite automatically for every push to `main` and for pull requests.
CI also runs the account security and migration tests against PostgreSQL 16. To run those locally, set `ACCOUNT_TEST_POSTGRES_URL` to a **disposable test server** with database creation and role-creation privileges; the tests create and delete isolated databases and may create the Supabase-compatible `anon`, `authenticated`, and `service_role` test roles. Never point it at production. Merge only after the complete suite is green. Render deploys automatically after main checks pass; do not manually trigger a second deploy.


## Frontend architecture (v9)
The hosted UI is now a React + TypeScript application mounted by FastAPI. FastAPI/PostgreSQL remain the backend and persistence layer. The live tracker keeps a temporary compatibility adapter around the proven site/timer engine while Dashboard, History, Progression, shell/navigation, and edit modals are React components. This adapter will be removed incrementally after hosted parity testing.