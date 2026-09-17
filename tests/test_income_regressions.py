"""Income must survive saving, editing, reporting, and application restarts."""
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import httpx


def boot(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return json.loads(re.search(r'window\.__BOOTSTRAP__=(.*?);</script>', response.text, re.S)[1])


def completed_run(client):
    response = client.post('/api/run/start', json={
        'anomaly': 'Angel Haven', 'participants': [90000001]})
    assert response.status_code == 200
    rid = response.json()['run']['id']
    sid = response.json()['session_id']
    assert client.post(f'/api/run/{rid}/complete').status_code == 200
    return rid, sid


def test_realized_escalation_income_across_statuses_edits_and_reports(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app['base_url'], trust_env=False) as client:
        for status in ['Sold', 'Ran Myself']:
            rid, sid = completed_run(client)
            assert client.post('/api/session/end', json={'loot_value': 2000000, 'salvage_value': 3000000}).status_code == 200
            for amount in [30000000, 45000000, 0]:
                response = client.post(f'/api/run/{rid}/bonus', json={
                    'escalation_name': 'Angel Capital Staging', 'escalation_status': status,
                    'escalation_sale_value': amount, 'rare_spawn_value': 5000000})
                assert response.status_code == 200
                saved = client.get(f'/api/run/{rid}').json()['run']
                assert saved['escalation_sale_value'] == amount
                assert saved['escalation_loot'] == (amount if status == 'Ran Myself' else 0)
                assert saved['escalation_sales'] == (amount if status == 'Sold' else 0)
                history = boot(client, '/history')['history']
                session = next(s for s in history['sessions'] if s['id'] == sid)
                assert session['bonus'] == amount + 5000000
                assert session['total'] == amount + 10000000
                expected_bonus_total = sum(s['bonus'] for s in history['sessions'])
                assert sum(d['bonus'] for d in history['chart_data']) == expected_bonus_total
                perf = boot(client, '/dashboard?days=7')['perf']
                expected_total = sum(s['total'] for s in history['sessions'])
                assert perf['total_isk'] == expected_total
                perf_row = next(r for r in perf['rows'] if r['id'] == sid)
                assert perf_row['total_isk'] == amount + 10000000


def test_startup_preserves_ran_myself_income(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app['base_url'], trust_env=False) as client:
        rid, _ = completed_run(client)
    with sqlite3.connect(test_app['work'] / 'ratting_tracker.db') as conn:
        conn.execute("UPDATE runs SET escalation_status='Ran Myself', escalation_sale_value=42000000 WHERE id=?", (rid,))
    env = {**os.environ, 'DATABASE_URL': '', 'TRACKER_DB_PATH': str(test_app['work'] / 'ratting_tracker.db')}
    subprocess.run([sys.executable, '-c', 'import app; app.init_db()'], cwd=test_app['work'], env=env, check=True, capture_output=True)
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app['base_url'], trust_env=False) as client:
        assert client.get(f'/api/run/{rid}').json()['run']['escalation_sale_value'] == 42000000


def test_end_session_retries_ess_matching_with_character_key(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app['base_url'], trust_env=False) as client:
        _, sid = completed_run(client)
        with sqlite3.connect(test_app['work'] / 'ratting_tracker.db') as conn:
            conn.execute('INSERT INTO ess_events(user_id,entry_id,character_id,date,amount) VALUES(1,?,?,?,?)',
                         (987, 90000001, (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(), 6000000))
        assert client.post('/api/session/end', json={}).status_code == 200
        history = boot(client, '/history')['history']
        assert history['ess'][0]['session_id'] == sid


def test_session_cannot_end_while_site_is_active(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app['base_url'], trust_env=False) as client:
        assert client.post('/api/run/start', json={'anomaly': 'Angel Hub', 'participants': [90000001]}).status_code == 200
        assert client.post('/api/session/end', json={}).status_code == 409
        assert client.get('/api/dashboard').json()['session'] is not None


def test_today_site_count_includes_more_than_recent_twelve(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app['base_url'], trust_env=False) as client:
        for _ in range(13):
            completed_run(client)
        data = client.get('/api/dashboard').json()
        assert len(data['recent']) == 12
        assert data['stats']['today_sites'] == 13


def test_future_sessions_excluded_from_performance(test_app):
    with httpx.Client(cookies=test_app["cookies"], headers=test_app["headers"], base_url=test_app['base_url'], trust_env=False) as client:
        _, sid = completed_run(client)
        assert client.post('/api/session/end', json={}).status_code == 200
        with sqlite3.connect(test_app['work'] / 'ratting_tracker.db') as conn:
            conn.execute('UPDATE sessions SET ended_at=? WHERE id=?',
                         ((datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), sid))
        assert boot(client, '/dashboard')['perf']['sessions'] == 0


def test_cache_control_max_age_is_honored(test_app):
    env = {**os.environ, 'DATABASE_URL': '', 'TRACKER_DB_PATH': str(test_app['work'] / 'ratting_tracker.db')}
    code = """
import app
before = app.utcnow()
expiry = app.esi_cache_expiry({'cache-control': 'public, max-age=1800'})
assert 1799 <= (expiry - before).total_seconds() <= 1801
"""
    subprocess.run([sys.executable, '-c', code], cwd=test_app['work'], env=env, check=True, capture_output=True)
