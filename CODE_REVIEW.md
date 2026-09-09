# Tracker review — 2026-09-09

Reviewed upstream commit `db0b782a14c9c2fd09e0922749c68112e496a762` (version 9.1.1).
This change is for review and the next update; it has not been deployed.
Fitting removal and layout changes remain deferred as requested.

## Fixed and verified

- **Ran Myself income:** the backend previously discarded the value, aggregation accepted only Sold, a browser fetch wrapper cleared it, and startup cleanup erased it. Both realized outcomes now persist and contribute to the existing bonus and total-income calculations. Pending/Expired remain excluded. The run/performance payloads distinguish escalation sales from escalation loot without introducing a second amount that could double count income.
- **Native editing:** Tracking and React History now own their Ran Myself inputs. Removed the shell workaround that temporarily changed the status to Sold and injected a separate field into React's DOM.
- **ESS matching at session completion:** supplied the missing character ID to the matching function. Previously the resulting exception was swallowed and the payment stayed unassigned.
- **Session lifecycle:** reject ending a session while it contains an active site, preventing inconsistent run/session state.
- **Daily site count:** count all completed sites for the day, rather than only the 12 rows in Recent Runs.
- **Future sessions:** exclude future-dated sessions from dashboard performance calculations.
- **ESI cache expiry:** corrected the escaped regular expression so Cache-Control max-age is recognized.
- **Test isolation:** explicitly use a temporary SQLite database, no production DATABASE_URL, and no inherited application access key for the test server.

## Evidence

- Original API suite: 21 passed after configuring the local test process to avoid the workspace proxy.
- New regression cases against unchanged application code: 7 failed, 1 passed. Failures reproduced Ran Myself saving, startup erasure, ESS matching, ending an active session, counting more than 12 sites, future sessions, and max-age parsing. Sold was the passing control.
- Final suite: **60 passed, 1 skipped** in 27.55 seconds using local Chromium 152.
- The skipped case is the repository's already-retired Beta Fits DOM assertion; no additional tests were skipped.
- Browser coverage includes Sold and Ran Myself completion flows, formatted inputs, dashboard and history totals, and history edit/reopen persistence.
- API coverage checks edited amounts including zero, mixed rare/loot/salvage totals, and rerunning startup initialization against saved income.
- React compilation succeeded. The generated bundle is included so the served code matches the tested source.

## Remaining findings and limits

These are not covered by an assertion that the whole live application is correct:

1. **History period scope:** `/history?days=7/30` changes chart buckets, but the returned run/session lists are not filtered to that period. Lists are capped at 200 runs and 100 sessions/ESS payments. Progression and daily Total ISK read those lists, so their data can be misleading for larger histories. Resolve the API period/pagination contract together with its consumers.
2. **Time boundaries:** backend daily cards/history buckets use UTC dates while the daily Total ISK chart uses browser-local dates. This can disagree around midnight in Curitiba. The session performance window is rolling elapsed time. Define a common period contract before changing the related labels and totals.
3. **Duration semantics:** run duration excludes pauses; session performance uses elapsed session start/end time. Session and run ISK/hour therefore use different denominators. Confirm whether session efficiency should include downtime before changing it.
4. **ESS attribution:** matching still uses the existing single-candidate time-window heuristic; ambiguous payments stay unassigned. This fix repairs the broken call, not the entire attribution policy.
5. **Live integrations:** authenticated EVE SSO, real wallet/ESS responses, Render deployment state, and PostgreSQL execution were not verified. Tests use isolated SQLite data, mock/seeded integration inputs, and abort remote portrait requests.

Previously erased escalation amounts cannot be reconstructed from this code. After deployment, any already-zeroed value must be entered again unless another source retains it.
