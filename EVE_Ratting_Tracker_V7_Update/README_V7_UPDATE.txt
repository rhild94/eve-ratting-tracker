EVE Ratting Tracker V7 - LOCAL-FIRST UPDATE

INSTALL
1. Stop the tracker.
2. Extract this ZIP directly into your EXISTING tracker folder.
3. Choose Replace.
4. Keep your existing .env and ratting_tracker.db.
5. Start normally with START_TRACKER.bat.

V7 ARCHITECTURE
All ratting actions are now LOCAL ONLY:
- Start Site
- Pause / Resume
- Complete Site
- Save escalation / rare spawn
- Edit saved result
- End Session
- Loot / Salvage
- Delete Run / Session

These actions do NOT contact ESI.

ESI is now only contacted when:
- You explicitly click Sync ESI
- You initially connect/authorize a character

Sync ESI handles:
- wallet/bounty reconciliation
- ESS import
- skills / skill queue
- current system / ship cache

SYSTEM / SHIP
Sync ESI stores each character's last known system and ship locally.
Starting a site uses that cached information instantly, without contacting ESI.
If you move systems or change ships, press Sync ESI once when convenient to refresh the cache.

STATUS
The tracker now shows:
- Local data saved ✓ · ESI pending
- ESI updated ✓
- Local data safe ✓ · ESI unavailable (if ESI fails)

Completed runs are marked pending until the next successful ESI sync.

All V6/V5/V4 features remain included:
- Pause/resume
- corrected triggers
- rare spawn separators
- ISK masks
- edit/delete history
- week/month graph
