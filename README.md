# EVE Ratting Tracker

**Current version: 9.1.0**

Private development repository for the EVE Online ratting tracker.

## Local-first architecture

Ratting actions are saved locally and do not wait for ESI. ESI synchronization runs automatically in the background and can also be triggered manually. Local ratting actions never wait for ESI.

## Windows / clean install

Extract the package and double-click `RUN_TRACKER.bat`. The launcher creates its own Python environment, installs dependencies, opens the browser, and attempts to import an existing tracker `.env` automatically.

The tracker can run completely without EVE configuration. Local timers, runs, history, sessions, and bonuses are available immediately. If an existing `.env` is found, the launcher imports it automatically; ESI features become available once an EVE Client ID is configured and a character is connected. EVE SSO uses PKCE, so a client secret is not required or stored.

Your runtime `.env`, `.venv`, and `ratting_tracker.db` stay local and are excluded from Git.

## Automated tests

```bash
python -m pip install -r requirements.txt -r requirements-test.txt
python -m playwright install chromium
python -m pytest tests -v
```

GitHub Actions runs the API and browser regression suite automatically for every push to `main` and for pull requests.


## Frontend architecture (v9)
The hosted UI is now a React + TypeScript application mounted by FastAPI. FastAPI/PostgreSQL remain the backend and persistence layer. The live tracker keeps a temporary compatibility adapter around the proven site/timer engine while Dashboard, History, Progression, shell/navigation, and edit modals are React components. This adapter will be removed incrementally after hosted parity testing.
