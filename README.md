# EVE Ratting Tracker

**Current version: 8.0.0**

Private development repository for the EVE Online ratting tracker.

## Local-first architecture

Ratting actions are saved locally and do not wait for ESI. ESI synchronization runs automatically in the background and can also be triggered manually. Local ratting actions never wait for ESI.

## Run locally

```bash
python -m pip install -r requirements.txt
python app.py
```

Keep your real `.env` and `ratting_tracker.db` local. They are excluded from Git.

## Automated tests

```bash
python -m pip install -r requirements.txt -r requirements-test.txt
python -m playwright install chromium
python -m pytest tests -v
```

GitHub Actions runs the API and browser regression suite automatically for every push to `main` and for pull requests.
