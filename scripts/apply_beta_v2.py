from pathlib import Path


def replace_once(path, old, new):
    p=Path(path); s=p.read_text(encoding='utf-8')
    if old not in s:
        raise SystemExit(f'Patch anchor not found in {path}: {old[:100]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# Backend: PostgreSQL/SQLite persisted fitting library and run fit selection.
p=Path('app.py'); s=p.read_text(encoding='utf-8')
old='''            "CREATE TABLE IF NOT EXISTS esi_cache(cache_key TEXT PRIMARY KEY,payload_json TEXT NOT NULL,expires_at TEXT,updated_at TEXT NOT NULL)",\n            "CREATE TABLE IF NOT EXISTS esi_sync_state(id INTEGER PRIMARY KEY,last_attempt TEXT,last_success TEXT,last_error TEXT,next_check TEXT)"'''
new='''            "CREATE TABLE IF NOT EXISTS esi_cache(cache_key TEXT PRIMARY KEY,payload_json TEXT NOT NULL,expires_at TEXT,updated_at TEXT NOT NULL)",\n            "CREATE TABLE IF NOT EXISTS fits(id TEXT PRIMARY KEY,character_id BIGINT,character_name TEXT,ship TEXT NOT NULL,name TEXT NOT NULL,raw_text TEXT NOT NULL,groups_json TEXT NOT NULL,type_ids_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",\n            "CREATE TABLE IF NOT EXISTS esi_sync_state(id INTEGER PRIMARY KEY,last_attempt TEXT,last_success TEXT,last_error TEXT,next_check TEXT)"'''
if old not in s: raise SystemExit('fits table anchor missing')
s=s.replace(old,new,1)
old='''        for d in ["variant TEXT","session_id BIGINT","escalation_name TEXT","escalation_status TEXT","escalation_sale_value DOUBLE PRECISION DEFAULT 0","rare_spawn_type TEXT","rare_spawn_name TEXT","rare_spawn_value DOUBLE PRECISION DEFAULT 0","paused_at TEXT","paused_seconds DOUBLE PRECISION DEFAULT 0","esi_synced_at TEXT"]:'''
new='''        for d in ["variant TEXT","session_id BIGINT","escalation_name TEXT","escalation_status TEXT","escalation_sale_value DOUBLE PRECISION DEFAULT 0","rare_spawn_type TEXT","rare_spawn_name TEXT","rare_spawn_value DOUBLE PRECISION DEFAULT 0","paused_at TEXT","paused_seconds DOUBLE PRECISION DEFAULT 0","esi_synced_at TEXT","fit_selection_json TEXT"]:'''
if old not in s: raise SystemExit('runs ensure_col anchor missing')
s=s.replace(old,new,1)
old='''        for d in ["cache_system_name TEXT","cache_ship_name TEXT","last_esi_sync TEXT","character_role TEXT DEFAULT 'alt'"]:\n            ensure_col(c,"characters",d)\ninit_db()'''
new='''        for d in ["cache_system_name TEXT","cache_ship_name TEXT","last_esi_sync TEXT","character_role TEXT DEFAULT 'alt'"]:\n            ensure_col(c,"characters",d)\n        # Reconcile stale Beta data: only Sold escalations are realized income.\n        c.execute("UPDATE runs SET escalation_sale_value=0 WHERE COALESCE(escalation_status,'')<>'Sold' AND COALESCE(escalation_sale_value,0)<>0")\ninit_db()'''
if old not in s: raise SystemExit('stale repair anchor missing')
s=s.replace(old,new,1)
old='''    d["participants"]=json.loads(d["participants_json"]); d["ships"]=json.loads(d["ships_json"]) if d.get("ships_json") else []\n    d["is_paused"]=bool(d.get("paused_at"))'''
new='''    d["participants"]=json.loads(d["participants_json"]); d["ships"]=json.loads(d["ships_json"]) if d.get("ships_json") else []\n    try:d["fit_selection"]=json.loads(d.get("fit_selection_json") or "{}")\n    except:d["fit_selection"]={}\n    d["is_paused"]=bool(d.get("paused_at"))'''
if old not in s: raise SystemExit('enrich anchor missing')
s=s.replace(old,new,1)
# Every aggregate must treat non-Sold escalation value as zero.
s=s.replace('money(r["escalation_sale_value"])+money(r["rare_spawn_value"])','(money(r["escalation_sale_value"]) if r["escalation_status"]=="Sold" else 0)+money(r["rare_spawn_value"])')
old='''        b=await request.json()\n        values=(\n            b.get("escalation_name") or None,\n            b.get("escalation_status") or None,\n            max(0,money(b.get("escalation_sale_value"))),'''
new='''        b=await request.json()\n        escalation_status=b.get("escalation_status") or None\n        values=(\n            b.get("escalation_name") or None,\n            escalation_status,\n            max(0,money(b.get("escalation_sale_value"))) if escalation_status=="Sold" else 0,'''
if old not in s: raise SystemExit('bonus enforcement anchor missing')
s=s.replace(old,new,1)
old='''        run=c.execute("SELECT * FROM runs WHERE id=?",(rid,)).fetchone()\n    return JSONResponse({"ok":True,"run":enrich(run),"session_id":sid})'''
new='''        c.execute("UPDATE runs SET fit_selection_json=? WHERE id=?",(json.dumps(body.get("fit_selection") or {}),rid))\n        run=c.execute("SELECT * FROM runs WHERE id=?",(rid,)).fetchone()\n    return JSONResponse({"ok":True,"run":enrich(run),"session_id":sid})'''
if old not in s: raise SystemExit('run fit-selection anchor missing')
s=s.replace(old,new,1)
old='''@app.get("/api/dashboard")\nasync def api_dashboard(): return JSONResponse(await dashboard_payload())\n\n@app.get("/login")'''
new='''@app.get("/api/dashboard")\nasync def api_dashboard(): return JSONResponse(await dashboard_payload())\n\ndef fit_payload(row):\n    d=dict(row)\n    try:d["groups"]=json.loads(d.pop("groups_json") or "{}")\n    except:d["groups"]={}\n    try:\n        tids=json.loads(d.pop("type_ids_json") or "{}")\n        d.update(tids)\n    except:pass\n    return d\n\n@app.get("/api/fits")\nasync def api_fits():\n    with db() as c:rows=c.execute("SELECT * FROM fits ORDER BY updated_at DESC,name").fetchall()\n    return JSONResponse({"ok":True,"fits":[fit_payload(r) for r in rows]})\n\n@app.post("/api/fits/resolve")\nasync def api_resolve_fit_types(request:Request):\n    body=await request.json();names=[str(x).strip() for x in body.get("names",[]) if str(x).strip()][:250]\n    if not names:return JSONResponse({"ok":True,"types":{}})\n    try:\n        h={"Accept":"application/json","Content-Type":"application/json","User-Agent":"Rafael-EVE-Ratting-Tracker/Beta","X-Compatibility-Date":COMPAT_DATE}\n        async with httpx.AsyncClient(timeout=20) as cl:\n            r=await cl.post(ESI+"/universe/ids/",headers=h,json=names);r.raise_for_status();data=r.json()\n        types={x.get("name"):x.get("id") for x in data.get("inventory_types",[]) if x.get("name") and x.get("id")}\n        return JSONResponse({"ok":True,"types":types})\n    except Exception as e:\n        return JSONResponse({"ok":False,"types":{},"error":f"{type(e).__name__}: {e}"},502)\n\n@app.post("/api/fits")\nasync def api_save_fit(request:Request):\n    body=await request.json();fid=str(body.get("id") or secrets.token_hex(16));ship=str(body.get("ship") or '').strip();name=str(body.get("name") or '').strip()\n    if not ship or not name:return JSONResponse({"ok":False,"error":"Ship and fit name are required."},400)\n    now=iso();created=str(body.get("created_at") or now);cid=body.get("character_id")\n    try:cid=int(cid) if cid not in (None,'') else None\n    except:cid=None\n    groups=body.get("groups") or {};type_ids={"ship_type_id":body.get("ship_type_id")}\n    with db() as c:\n        c.execute("""INSERT INTO fits(id,character_id,character_name,ship,name,raw_text,groups_json,type_ids_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)\n                     ON CONFLICT(id) DO UPDATE SET character_id=excluded.character_id,character_name=excluded.character_name,ship=excluded.ship,name=excluded.name,raw_text=excluded.raw_text,groups_json=excluded.groups_json,type_ids_json=excluded.type_ids_json,updated_at=excluded.updated_at""",\n                  (fid,cid,str(body.get("character_name") or "Unassigned"),ship,name,str(body.get("raw_text") or ""),json.dumps(groups),json.dumps(type_ids),created,now))\n        row=c.execute("SELECT * FROM fits WHERE id=?",(fid,)).fetchone()\n    return JSONResponse({"ok":True,"fit":fit_payload(row)})\n\n@app.delete("/api/fits/{fit_id}")\nasync def api_delete_fit(fit_id:str):\n    with db() as c:c.execute("DELETE FROM fits WHERE id=?",(fit_id,))\n    return JSONResponse({"ok":True})\n\n@app.get("/login")'''
if old not in s: raise SystemExit('fits API anchor missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

# React dashboard loads the new dual-purpose graph renderer.
replace_once('static/react/main.tsx','loadScript("/static/dashboard.js?v=approved-v10","dashboard-chart-js")','loadScript("/static/dashboard_beta.js?v=beta-2","dashboard-chart-js")')

# Load the v2 enhancement CSS/JS after the existing compatibility layer.
replace_once('templates/react.html','<link rel="stylesheet" href="/static/beta_features.css?v=beta-1">','<link rel="stylesheet" href="/static/beta_features.css?v=beta-1">\n<link rel="stylesheet" href="/static/beta_features_v2.css?v=beta-2">')
replace_once('templates/react.html','<script src="/static/beta_features.js?v=beta-1"></script>','<script src="/static/beta_features.js?v=beta-1"></script>\n<script src="/static/beta_features_v2.js?v=beta-2"></script>')

# Regression tests for persisted fits, run fit selections, and backend Sold-only enforcement.
t=Path('tests/test_tracker_api.py'); ts=t.read_text(encoding='utf-8')
marker='def test_beta_v2_fits_are_persisted'
if marker not in ts:
    ts += '''\n\ndef test_beta_v2_fits_are_persisted(test_app):\n    base = test_app["base_url"]\n    with httpx.Client(base_url=base, timeout=5) as c:\n        payload={"id":"fit-test-1","character_id":90000001,"character_name":"Playwright Pilot","ship":"Raven","name":"Angel Cruise","raw_text":"[Raven, Angel Cruise]","groups":{"high":[{"name":"Cruise Missile Launcher II","quantity":6}]},"ship_type_id":638}\n        r=c.post("/api/fits",json=payload);assert r.status_code==200,r.text\n        data=c.get("/api/fits").json()["fits"];assert len(data)==1\n        assert data[0]["ship"]=="Raven" and data[0]["groups"]["high"][0]["quantity"]==6\n        assert c.delete("/api/fits/fit-test-1").status_code==200\n        assert c.get("/api/fits").json()["fits"]==[]\n\ndef test_beta_v2_run_stores_fit_selection(test_app):\n    base=test_app["base_url"]\n    with httpx.Client(base_url=base,timeout=5) as c:\n        selection={"90000001":{"id":"fit-1","ship":"Raven","name":"Angel Cruise"}}\n        r=c.post("/api/run/start",json={"anomaly":"Angel Haven","variant":"Default","participants":[90000001],"notes":"","fit_selection":selection})\n        assert r.status_code==200,r.text\n        rid=r.json()["run"]["id"]\n        saved=c.get(f"/api/run/{rid}").json()["run"]\n        assert saved["fit_selection"]["90000001"]["ship"]=="Raven"\n\ndef test_non_sold_escalation_value_is_cleared_by_backend(test_app):\n    base=test_app["base_url"]\n    with httpx.Client(base_url=base,timeout=5) as c:\n        r=c.post("/api/run/start",json={"anomaly":"Angel Hub","variant":"Default","participants":[90000001],"notes":""});rid=r.json()["run"]["id"]\n        assert c.post(f"/api/run/{rid}/complete").status_code==200\n        assert c.post(f"/api/run/{rid}/bonus",json={"escalation_name":"Angel Capital Staging","escalation_status":"Sold","escalation_sale_value":30000000}).status_code==200\n        assert c.post(f"/api/run/{rid}/bonus",json={"escalation_name":"Angel Capital Staging","escalation_status":"Pending","escalation_sale_value":30000000}).status_code==200\n        saved=c.get(f"/api/run/{rid}").json()["run"]\n        assert saved["escalation_status"]=="Pending" and saved["escalation_sale_value"]==0\n'''
    t.write_text(ts,encoding='utf-8')

print('Beta v2 integration patch applied.')
