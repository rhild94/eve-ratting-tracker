
import os,time,json,base64,sqlite3,secrets,asyncio,re
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI,Request,Form
from fastapi.responses import HTMLResponse,RedirectResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR=Path(__file__).resolve().parent
APP_VERSION="8.0.0"
load_dotenv(BASE_DIR/".env")
CLIENT_ID=os.getenv("EVE_CLIENT_ID","").strip()
CLIENT_SECRET=os.getenv("EVE_CLIENT_SECRET","").strip()
CALLBACK_URL=os.getenv("EVE_CALLBACK_URL","http://localhost:8000/callback").strip()
HOST=os.getenv("TRACKER_HOST","127.0.0.1"); PORT=int(os.getenv("TRACKER_PORT","8000"))
AUTO_SYNC_INTERVAL_SECONDS=max(60,int(os.getenv("ESI_AUTO_SYNC_SECONDS","1800")))
AUTO_SYNC_INITIAL_DELAY_SECONDS=max(1,int(os.getenv("ESI_AUTO_SYNC_INITIAL_DELAY_SECONDS","10")))

SCOPES=["esi-skills.read_skills.v1","esi-skills.read_skillqueue.v1","esi-wallet.read_character_wallet.v1","esi-location.read_location.v1","esi-location.read_ship_type.v1"]
SSO_AUTHORIZE="https://login.eveonline.com/v2/oauth/authorize/"
SSO_TOKEN="https://login.eveonline.com/v2/oauth/token"
ESI="https://esi.evetech.net"; COMPAT_DATE="2025-09-16"

ANOMALIES=["Angel Hub","Angel Hidden Hub","Angel Forsaken Hub","Angel Forlorn Hub","Angel Haven","Angel Sanctum"]
ESCALATIONS={
"Angel Hub":["Cartel Prisoner Retention","Angel Capital Staging","Angel Shielded Starbase"],
"Angel Hidden Hub":["Angel Domination Fleet Staging Point"],
"Angel Forsaken Hub":["Angel Domination Fleet Staging Point","Angel Capital Staging","Angel Occupied Mine"],
"Angel Forlorn Hub":["Angel Domination Fleet Staging Point","Angel Shielded Starbase","Angel Occupied Mine"],
"Angel Haven":["Angel Cartel Naval Shipyard","Angel Capital Staging","Angel Shielded Starbase","Angel Occupied Mine"],
"Angel Sanctum":["Angel Shielded Starbase","Angel Capital Staging","Angel Naval Shipyard","Angel Occupied Mine"]}

app=FastAPI(title="EVE Ratting Tracker",version=APP_VERSION)
app.mount("/static",StaticFiles(directory=BASE_DIR/"static"),name="static")
templates=Jinja2Templates(directory=BASE_DIR/"templates")
DB=BASE_DIR/"ratting_tracker.db"

def db():
    c=sqlite3.connect(DB,timeout=30)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    return c
def col_exists(c,t,col): return any(r["name"]==col for r in c.execute(f"PRAGMA table_info({t})"))
def ensure_col(c,t,d):
    if not col_exists(c,t,d.split()[0]): c.execute(f"ALTER TABLE {t} ADD COLUMN {d}")
def init_db():
    with db() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS characters(character_id INTEGER PRIMARY KEY,name TEXT NOT NULL,access_token TEXT NOT NULL,refresh_token TEXT NOT NULL,expires_at INTEGER NOT NULL,connected_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS skill_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,character_id INTEGER NOT NULL,captured_at TEXT NOT NULL,total_sp INTEGER NOT NULL,skills_json TEXT NOT NULL,queue_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wallet_entries(entry_id INTEGER PRIMARY KEY,character_id INTEGER NOT NULL,date TEXT NOT NULL,amount REAL NOT NULL,balance REAL,ref_type TEXT,description TEXT,raw_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT,anomaly TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT,participants_json TEXT NOT NULL,notes TEXT,status TEXT NOT NULL DEFAULT 'active',combined_bounty REAL DEFAULT 0,system_name TEXT,ships_json TEXT);
CREATE TABLE IF NOT EXISTS type_names(type_id INTEGER PRIMARY KEY,name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,started_at TEXT NOT NULL,ended_at TEXT,status TEXT NOT NULL DEFAULT 'active',loot_value REAL DEFAULT 0,salvage_value REAL DEFAULT 0,notes TEXT);
CREATE TABLE IF NOT EXISTS ess_events(entry_id INTEGER PRIMARY KEY,character_id INTEGER NOT NULL,date TEXT NOT NULL,amount REAL NOT NULL,session_id INTEGER,match_status TEXT NOT NULL DEFAULT 'unassigned');
CREATE TABLE IF NOT EXISTS esi_cache(cache_key TEXT PRIMARY KEY,payload_json TEXT NOT NULL,expires_at TEXT,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS esi_sync_state(id INTEGER PRIMARY KEY CHECK(id=1),last_attempt TEXT,last_success TEXT,last_error TEXT,next_check TEXT);
INSERT OR IGNORE INTO esi_sync_state(id) VALUES(1);
""")
        for d in ["variant TEXT","session_id INTEGER","escalation_name TEXT","escalation_status TEXT","escalation_sale_value REAL DEFAULT 0","rare_spawn_type TEXT","rare_spawn_name TEXT","rare_spawn_value REAL DEFAULT 0","paused_at TEXT","paused_seconds REAL DEFAULT 0","esi_synced_at TEXT"]:
            ensure_col(c,"runs",d)
        for d in ["cache_system_name TEXT","cache_ship_name TEXT","last_esi_sync TEXT"]:
            ensure_col(c,"characters",d)
init_db()

def utcnow(): return datetime.now(timezone.utc)
def iso(d=None): return (d or utcnow()).isoformat()
def parse_iso(s): return datetime.fromisoformat(s.replace("Z","+00:00"))
def money(v): return float(v or 0)

def jwt_payload(t):
    try:
        p=t.split(".")[1]; p+="="*(-len(p)%4)
        return json.loads(base64.urlsafe_b64decode(p.encode()).decode())
    except: return {}
def charid(t):
    s=jwt_payload(t).get("sub","")
    return int(s.rsplit(":",1)[-1]) if s.startswith("CHARACTER:EVE:") else None

def esi_cache_expiry(headers):
    cc=headers.get("cache-control","")
    m=re.search(r"(?:^|,)\\s*max-age=(\\d+)",cc,re.I)
    if m:return utcnow()+timedelta(seconds=max(0,int(m.group(1))))
    ex=headers.get("expires")
    if ex:
        try:
            d=parsedate_to_datetime(ex)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except:pass
    return utcnow()

async def esi_get(path,token=None,params=None):
    cache_key=path+"?"+json.dumps(params or {},sort_keys=True,separators=(",",":"))
    with db() as c:
        cached=c.execute("SELECT payload_json,expires_at FROM esi_cache WHERE cache_key=?",(cache_key,)).fetchone()
    if cached and cached["expires_at"]:
        try:
            if parse_iso(cached["expires_at"])>utcnow():
                return json.loads(cached["payload_json"])
        except:pass
    h={"Accept":"application/json","User-Agent":"Rafael-EVE-Ratting-Tracker/8.0","X-Compatibility-Date":COMPAT_DATE}
    if token:h["Authorization"]=f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30) as cl:
        r=await cl.get(ESI+path,headers=h,params=params)
        r.raise_for_status()
        payload=r.json()
    expires=esi_cache_expiry(r.headers)
    with db() as c:
        c.execute("""INSERT INTO esi_cache(cache_key,payload_json,expires_at,updated_at) VALUES(?,?,?,?)
                     ON CONFLICT(cache_key) DO UPDATE SET payload_json=excluded.payload_json,expires_at=excluded.expires_at,updated_at=excluded.updated_at""",
                  (cache_key,json.dumps(payload),iso(expires),iso()))
    return payload

async def row_char(cid):
    with db() as c:return c.execute("SELECT * FROM characters WHERE character_id=?",(cid,)).fetchone()
async def refresh(row):
    if row["expires_at"]>int(time.time())+60:return row["access_token"]
    async with httpx.AsyncClient(timeout=30) as cl:
        r=await cl.post(SSO_TOKEN,auth=(CLIENT_ID,CLIENT_SECRET),data={"grant_type":"refresh_token","refresh_token":row["refresh_token"]})
        r.raise_for_status(); t=r.json()
    a=t["access_token"]; rr=t.get("refresh_token",row["refresh_token"]); ex=int(time.time())+int(t.get("expires_in",1200))
    with db() as c:c.execute("UPDATE characters SET access_token=?,refresh_token=?,expires_at=? WHERE character_id=?",(a,rr,ex,row["character_id"]))
    return a
async def type_name(tid):
    if not tid:return None
    with db() as c:r=c.execute("SELECT name FROM type_names WHERE type_id=?",(tid,)).fetchone()
    if r:return r["name"]
    try:
        n=(await esi_get(f"/universe/types/{tid}/")).get("name",str(tid))
        with db() as c:c.execute("INSERT OR REPLACE INTO type_names VALUES(?,?)",(tid,n))
        return n
    except:return str(tid)
async def sys_name(sid):
    try:return (await esi_get(f"/universe/systems/{sid}/")).get("name",str(sid))
    except:return str(sid) if sid else None

def auto_match_ess(c,eid,dt):
    cand=c.execute("SELECT id,ended_at FROM sessions WHERE status='complete' AND ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT 8").fetchall()
    p=[]
    for s in cand:
        x=(dt-parse_iso(s["ended_at"])).total_seconds()
        if 0<=x<=14400:p.append((x,s["id"]))
    if len(p)==1:c.execute("UPDATE ess_events SET session_id=?,match_status='auto' WHERE entry_id=?",(p[0][1],eid))

async def sync_character(cid):
    row=await row_char(cid)
    if not row:return
    tok=await refresh(row)
    skills=await esi_get(f"/characters/{cid}/skills/",tok)
    queue=await esi_get(f"/characters/{cid}/skillqueue/",tok)
    journal=await esi_get(f"/characters/{cid}/wallet/journal/",tok)
    cache_system=None; cache_ship=None
    try:
        loc=await esi_get(f"/characters/{cid}/location/",tok)
        cache_system=await sys_name(loc.get("solar_system_id"))
    except:pass
    try:
        sh=await esi_get(f"/characters/{cid}/ship/",tok)
        cache_ship=await type_name(sh.get("ship_type_id"))
    except:pass
    synced=iso()
    with db() as c:
        c.execute("INSERT INTO skill_snapshots(character_id,captured_at,total_sp,skills_json,queue_json) VALUES(?,?,?,?,?)",(cid,synced,int(skills.get("total_sp",0)),json.dumps(skills.get("skills",[])),json.dumps(queue)))
        c.execute("UPDATE characters SET cache_system_name=COALESCE(?,cache_system_name),cache_ship_name=COALESCE(?,cache_ship_name),last_esi_sync=? WHERE character_id=?",(cache_system,cache_ship,synced,cid))
        for j in journal:
            c.execute("INSERT OR IGNORE INTO wallet_entries(entry_id,character_id,date,amount,balance,ref_type,description,raw_json) VALUES(?,?,?,?,?,?,?,?)",(j.get("id"),cid,j.get("date"),money(j.get("amount")),j.get("balance"),j.get("ref_type"),j.get("description"),json.dumps(j)))
            if "ess" in (j.get("ref_type") or "").lower() and money(j.get("amount"))>0:
                c.execute("INSERT OR IGNORE INTO ess_events(entry_id,character_id,date,amount) VALUES(?,?,?,?)",(j.get("id"),cid,j.get("date"),money(j.get("amount"))))
                try:auto_match_ess(c,j.get("id"),parse_iso(j.get("date")))
                except:pass

async def status(cid):
    row=await row_char(cid); tok=await refresh(row); out={"character_id":cid,"name":row["name"]}
    try:
        loc=await esi_get(f"/characters/{cid}/location/",tok); out["system_name"]=await sys_name(loc.get("solar_system_id"))
    except:pass
    try:
        sh=await esi_get(f"/characters/{cid}/ship/",tok); out["ship_name"]=await type_name(sh.get("ship_type_id"))
    except:pass
    return out

def latest(cid):
    with db() as c:return c.execute("SELECT * FROM skill_snapshots WHERE character_id=? ORDER BY id DESC LIMIT 1",(cid,)).fetchone()

async def progression(cid,queue_limit=50):
    with db() as c:s=c.execute("SELECT * FROM skill_snapshots WHERE character_id=? ORDER BY id DESC LIMIT 2",(cid,)).fetchall()
    if not s:return {"total_sp":0,"queue":[],"changes":[]}
    q=[]
    for x in json.loads(s[0]["queue_json"])[:queue_limit]:
        q.append({"skill":await type_name(x.get("skill_id")),"level":x.get("finished_level"),"finish_date":x.get("finish_date"),"start_date":x.get("start_date")})
    ch=[]
    if len(s)>1:
        old={x["skill_id"]:x for x in json.loads(s[1]["skills_json"])}
        for cur in json.loads(s[0]["skills_json"]):
            a=int(old.get(cur["skill_id"],{}).get("trained_skill_level",0));b=int(cur.get("trained_skill_level",0))
            if b>a:ch.append({"skill":await type_name(cur["skill_id"]),"from":a,"to":b})
    return {"total_sp":s[0]["total_sp"],"queue":q,"changes":ch,"captured_at":s[0]["captured_at"]}

def active_session(c):return c.execute("SELECT * FROM sessions WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
def ensure_session(c,st):
    s=active_session(c)
    if s:return s["id"]
    return c.execute("INSERT INTO sessions(started_at,status) VALUES(?,'active')",(st,)).lastrowid

def cached_run_context(pids):
    with db() as c:
        rows=c.execute(f"SELECT character_id,name,cache_system_name,cache_ship_name FROM characters WHERE character_id IN ({','.join('?'*len(pids))})",pids).fetchall() if pids else []
    systems=[r["cache_system_name"] for r in rows if r["cache_system_name"]]
    system=systems[0] if systems and all(x==systems[0] for x in systems) else (", ".join(sorted(set(systems))) if systems else None)
    ships=[{"character":r["name"],"ship":r["cache_ship_name"]} for r in rows if r["cache_ship_name"]]
    return system,ships

def reconcile_bounty(rid):
    with db() as c:r=c.execute("SELECT * FROM runs WHERE id=?",(rid,)).fetchone()
    if not r or not r["ended_at"]:return
    pids=json.loads(r["participants_json"]); total=0
    rows=c.execute(f"SELECT * FROM wallet_entries WHERE character_id IN ({','.join('?'*len(pids))})",pids).fetchall()
    for j in rows:
        try:d=parse_iso(j["date"])
        except:continue
        if parse_iso(r["started_at"])<=d<=parse_iso(r["ended_at"]) and (j["ref_type"] or "").lower()=="bounty_prizes" and money(j["amount"])>0:
            total+=money(j["amount"])
    c.execute("UPDATE runs SET combined_bounty=? WHERE id=?",(total,rid))

def effective_run_seconds(r, now=None):
    start=parse_iso(r["started_at"])
    end=parse_iso(r["ended_at"]) if r["ended_at"] else (now or utcnow())
    paused=money(r["paused_seconds"])
    if r["paused_at"] and not r["ended_at"]:
        paused += max(0,(end-parse_iso(r["paused_at"])).total_seconds())
    return max(0,int((end-start).total_seconds()-paused))

def enrich(r):
    d=dict(r); dur=effective_run_seconds(r)
    d["duration_seconds"]=dur; d["duration_label"]=f"{dur//60}m {dur%60:02d}s" if (dur or r["ended_at"]) else "0m 00s"
    d["isk_hr"]=money(d.get("combined_bounty"))/dur*3600 if dur else 0
    d["participants"]=json.loads(d["participants_json"]); d["ships"]=json.loads(d["ships_json"]) if d.get("ships_json") else []
    d["is_paused"]=bool(d.get("paused_at"))
    return d

async def dashboard_payload():
    with db() as c:
        chars=c.execute("SELECT character_id,name FROM characters ORDER BY connected_at").fetchall()
        ar=c.execute("SELECT * FROM runs WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
        recent=c.execute("SELECT * FROM runs WHERE status='complete' ORDER BY id DESC LIMIT 12").fetchall()
        ses=active_session(c); sr=c.execute("SELECT * FROM runs WHERE session_id=? ORDER BY id",(ses["id"],)).fetchall() if ses else []
    characters=[{"id":x["character_id"],"name":x["name"],"portrait":f"https://images.evetech.net/characters/{x['character_id']}/portrait?size=64"} for x in chars]
    today=utcnow().date(); stats={"today_isk":0,"today_sites":0,"today_seconds":0,"today_ess":0}
    for r in recent:
        if r["ended_at"] and parse_iso(r["ended_at"]).date()==today:
            e=enrich(r);stats["today_isk"]+=money(r["combined_bounty"]);stats["today_sites"]+=1;stats["today_seconds"]+=e["duration_seconds"]
    with db() as c:
        for e in c.execute("SELECT * FROM ess_events"):
            if parse_iso(e["date"]).date()==today:stats["today_ess"]+=money(e["amount"])
    stats["avg_isk_hr"]=stats["today_isk"]/stats["today_seconds"]*3600 if stats["today_seconds"] else 0
    si=None
    if ses:
        done=[r for r in sr if r["status"]=="complete"]
        si={"id":ses["id"],"sites":len(done),"bounty":sum(money(r["combined_bounty"]) for r in done)}
    with db() as c:
        pending_esi=c.execute("SELECT COUNT(*) AS n FROM runs WHERE status='complete' AND esi_synced_at IS NULL").fetchone()["n"]
        last_sync=c.execute("SELECT MAX(last_esi_sync) AS t FROM characters").fetchone()["t"]
        sync_state=c.execute("SELECT * FROM esi_sync_state WHERE id=1").fetchone()
    esi_state={"pending_runs":pending_esi,"last_sync":last_sync,"interval_minutes":AUTO_SYNC_INTERVAL_SECONDS//60}
    if sync_state:esi_state.update({k:sync_state[k] for k in ["last_attempt","last_success","last_error","next_check"]})
    return {"characters":characters,"active":enrich(ar) if ar else None,"recent":[enrich(r) for r in recent],"stats":stats,"session":si,"anomalies":ANOMALIES,"esi":esi_state}

@app.get("/",response_class=HTMLResponse)
async def home(request:Request):
    payload=await dashboard_payload()
    return templates.TemplateResponse(request=request,name="index.html",context={"data":payload,"config_ok":bool(CLIENT_ID and CLIENT_SECRET)})

@app.get("/api/dashboard")
async def api_dashboard(): return JSONResponse(await dashboard_payload())

@app.get("/login")
async def login():
    st=secrets.token_urlsafe(32)
    with db() as c:c.execute("INSERT INTO oauth_states VALUES(?,?)",(st,int(time.time())))
    return RedirectResponse(SSO_AUTHORIZE+"?"+urlencode({"response_type":"code","redirect_uri":CALLBACK_URL,"client_id":CLIENT_ID,"scope":" ".join(SCOPES),"state":st}))
@app.get("/callback")
async def callback(code:str,state:str):
    with db() as c:
        if not c.execute("SELECT 1 FROM oauth_states WHERE state=?",(state,)).fetchone():return HTMLResponse("Invalid OAuth state",400)
        c.execute("DELETE FROM oauth_states WHERE state=?",(state,))
    async with httpx.AsyncClient(timeout=30) as cl:
        r=await cl.post(SSO_TOKEN,auth=(CLIENT_ID,CLIENT_SECRET),data={"grant_type":"authorization_code","code":code});r.raise_for_status();t=r.json()
    cid=charid(t["access_token"]);pub=await esi_get(f"/characters/{cid}/")
    with db() as c:c.execute("""INSERT INTO characters VALUES(?,?,?,?,?,?) ON CONFLICT(character_id) DO UPDATE SET name=excluded.name,access_token=excluded.access_token,refresh_token=excluded.refresh_token,expires_at=excluded.expires_at""",(cid,pub.get("name",str(cid)),t["access_token"],t["refresh_token"],int(time.time())+int(t.get("expires_in",1200)),iso()))
    await sync_character(cid)
    return RedirectResponse("/",302)

async def run_esi_sync(source="manual"):
    attempt=iso()
    next_check=iso(utcnow()+timedelta(seconds=AUTO_SYNC_INTERVAL_SECONDS))
    with db() as c:
        c.execute("UPDATE esi_sync_state SET last_attempt=?,next_check=? WHERE id=1",(attempt,next_check))
        ids=[x["character_id"] for x in c.execute("SELECT character_id FROM characters")]
    errors=[]
    for cid in ids:
        try:await sync_character(cid)
        except Exception as e:errors.append(f"{cid}: {type(e).__name__}: {e}")
    synced=iso()
    if not errors:
        with db() as c:rids=[r["id"] for r in c.execute("SELECT id FROM runs WHERE status='complete'")]
        for rid in rids:
            try:
                reconcile_bounty(rid)
                with db() as c:c.execute("UPDATE runs SET esi_synced_at=? WHERE id=?",(synced,rid))
            except Exception as e:errors.append(f"run {rid}: {type(e).__name__}: {e}")
    with db() as c:
        if errors:
            c.execute("UPDATE esi_sync_state SET last_error=? WHERE id=1",("; ".join(errors)[:1000],))
        else:
            c.execute("UPDATE esi_sync_state SET last_success=?,last_error=NULL WHERE id=1",(synced,))
    return {"ok":not errors,"errors":errors,"source":source}

async def auto_sync_loop():
    await asyncio.sleep(AUTO_SYNC_INITIAL_DELAY_SECONDS)
    while True:
        try:await run_esi_sync("auto")
        except Exception as e:
            with db() as c:
                c.execute("UPDATE esi_sync_state SET last_attempt=?,last_error=?,next_check=? WHERE id=1",
                          (iso(),f"{type(e).__name__}: {e}"[:1000],iso(utcnow()+timedelta(seconds=AUTO_SYNC_INTERVAL_SECONDS))))
        await asyncio.sleep(AUTO_SYNC_INTERVAL_SECONDS)

@app.on_event("startup")
async def start_auto_sync():
    app.state.esi_sync_task=asyncio.create_task(auto_sync_loop())

@app.on_event("shutdown")
async def stop_auto_sync():
    task=getattr(app.state,"esi_sync_task",None)
    if task:
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass

@app.post("/api/sync")
async def api_sync():
    result=await run_esi_sync("manual")
    return JSONResponse({**result,"dashboard":await dashboard_payload()})

@app.post("/api/run/start")
async def api_start_run(request:Request):
    body=await request.json(); anomaly=body.get("anomaly",""); variant=body.get("variant",""); pids=[int(x) for x in body.get("participants",[])]; notes=(body.get("notes") or "").strip()
    if anomaly not in ANOMALIES or not pids:return JSONResponse({"ok":False,"error":"Choose an anomaly and at least one participant."},400)
    st=iso(); system,ships=cached_run_context(pids)
    with db() as c:
        if c.execute("SELECT 1 FROM runs WHERE status='active'").fetchone():return JSONResponse({"ok":False,"error":"A site is already running."},409)
        sid=ensure_session(c,st)
        rid=c.execute("INSERT INTO runs(anomaly,variant,started_at,participants_json,notes,status,system_name,ships_json,session_id,esi_synced_at) VALUES(?,?,?,?,?,'active',?,?,?,NULL)",(anomaly,variant or None,st,json.dumps(pids),notes,system,json.dumps(ships),sid)).lastrowid
        run=c.execute("SELECT * FROM runs WHERE id=?",(rid,)).fetchone()
    return JSONResponse({"ok":True,"run":enrich(run),"session_id":sid})


@app.post("/api/run/{rid}/pause")
async def api_toggle_pause(rid:int):
    with db() as c:
        r=c.execute("SELECT * FROM runs WHERE id=? AND status='active'",(rid,)).fetchone()
        if not r:return JSONResponse({"ok":False,"error":"Active run not found."},404)
        if r["paused_at"]:
            added=max(0,(utcnow()-parse_iso(r["paused_at"])).total_seconds())
            c.execute("UPDATE runs SET paused_at=NULL,paused_seconds=COALESCE(paused_seconds,0)+? WHERE id=?",(added,rid))
        else:
            c.execute("UPDATE runs SET paused_at=? WHERE id=?",(iso(),rid))
        updated=c.execute("SELECT * FROM runs WHERE id=?",(rid,)).fetchone()
    return JSONResponse({"ok":True,"run":enrich(updated)})

@app.post("/api/run/{rid}/complete")
async def api_complete_run(rid:int):
    with db() as c:r=c.execute("SELECT * FROM runs WHERE id=? AND status='active'",(rid,)).fetchone()
    if not r:return JSONResponse({"ok":False,"error":"Active run not found."},404)
    end=utcnow()
    with db() as c:
        if r["paused_at"]:
            added=max(0,(end-parse_iso(r["paused_at"])).total_seconds())
            c.execute("UPDATE runs SET paused_at=NULL,paused_seconds=COALESCE(paused_seconds,0)+? WHERE id=?",(added,rid))
        c.execute("UPDATE runs SET ended_at=?,status='complete' WHERE id=?",(iso(end),rid))
        done=c.execute("SELECT * FROM runs WHERE id=?",(rid,)).fetchone()
    # Local-first: no ESI/wallet work here. Sync ESI will reconcile later.
    return JSONResponse({"ok":True,"run":enrich(done),"escalations":ESCALATIONS.get(done["anomaly"],[]),"bounty_pending":True})

@app.post("/api/run/{rid}/bonus")
async def api_save_bonus(rid:int,request:Request):
    try:
        b=await request.json()
        values=(
            b.get("escalation_name") or None,
            b.get("escalation_status") or None,
            max(0,money(b.get("escalation_sale_value"))),
            b.get("rare_spawn_type") or None,
            b.get("rare_spawn_name") or None,
            max(0,money(b.get("rare_spawn_value"))),
            (b.get("notes") or "").strip(),
            rid
        )
        last_error=None
        for _ in range(3):
            try:
                with db() as c:
                    exists=c.execute("SELECT id FROM runs WHERE id=?",(rid,)).fetchone()
                    if not exists:return JSONResponse({"ok":False,"error":"Run not found."},404)
                    c.execute("""UPDATE runs SET escalation_name=?,escalation_status=?,escalation_sale_value=?,rare_spawn_type=?,rare_spawn_name=?,rare_spawn_value=?,notes=? WHERE id=?""",values)
                return JSONResponse({"ok":True})
            except sqlite3.OperationalError as e:
                last_error=e
                if "locked" not in str(e).lower():raise
                time.sleep(.25)
        return JSONResponse({"ok":False,"error":f"Database was busy: {last_error}"},503)
    except Exception as e:
        return JSONResponse({"ok":False,"error":f"{type(e).__name__}: {e}"},500)


@app.get("/api/run/{rid}")
async def api_get_run(rid:int):
    with db() as c:r=c.execute("SELECT * FROM runs WHERE id=?",(rid,)).fetchone()
    if not r:return JSONResponse({"ok":False,"error":"Run not found."},404)
    return JSONResponse({"ok":True,"run":enrich(r),"escalations":ESCALATIONS.get(r["anomaly"],[])})

@app.delete("/api/run/{rid}")
async def api_delete_run(rid:int):
    with db() as c:
        r=c.execute("SELECT * FROM runs WHERE id=?",(rid,)).fetchone()
        if not r:return JSONResponse({"ok":False,"error":"Run not found."},404)
        c.execute("DELETE FROM runs WHERE id=?",(rid,))
    return JSONResponse({"ok":True})

@app.post("/api/session/end")
async def api_end_session(request:Request):
    b=await request.json()
    with db() as c:
        s=active_session(c)
        if not s:return JSONResponse({"ok":False,"error":"No active session."},404)
        last=c.execute("SELECT ended_at FROM runs WHERE session_id=? AND status='complete' ORDER BY ended_at DESC LIMIT 1",(s["id"],)).fetchone()
        end=last["ended_at"] if last else iso()
        c.execute("UPDATE sessions SET ended_at=?,status='complete',loot_value=?,salvage_value=?,notes=? WHERE id=?",(end,max(0,money(b.get("loot_value"))),max(0,money(b.get("salvage_value"))),(b.get("notes") or "").strip(),s["id"]))
        for e in c.execute("SELECT * FROM ess_events WHERE session_id IS NULL"):
            try:auto_match_ess(c,e["entry_id"],parse_iso(e["date"]))
            except:pass
    return JSONResponse({"ok":True})

@app.delete("/api/session/{sid}")
async def api_delete_session(sid:int):
    with db() as c:
        c.execute("UPDATE ess_events SET session_id=NULL,match_status='unassigned' WHERE session_id=?",(sid,))
        c.execute("DELETE FROM runs WHERE session_id=?",(sid,))
        c.execute("DELETE FROM sessions WHERE id=?",(sid,))
    return JSONResponse({"ok":True})

@app.get("/progression",response_class=HTMLResponse)
async def progression_page(request:Request):
    with db() as c:chars=c.execute("SELECT character_id,name FROM characters ORDER BY connected_at").fetchall()
    out=[]
    for x in chars:
        p=await progression(x["character_id"],50)
        out.append({"id":x["character_id"],"name":x["name"],"portrait":f"https://images.evetech.net/characters/{x['character_id']}/portrait?size=128",**p})
    return templates.TemplateResponse(request=request,name="progression.html",context={"characters":out})

@app.get("/history",response_class=HTMLResponse)
async def history(request:Request,days:int=7):
    days=30 if days==30 else 7; start=utcnow().date()-timedelta(days=days-1)
    with db() as c:
        rs=c.execute("SELECT * FROM runs WHERE status='complete' ORDER BY ended_at DESC").fetchall()
        ss=c.execute("SELECT * FROM sessions WHERE status='complete' ORDER BY ended_at DESC").fetchall()
        ess=c.execute("SELECT * FROM ess_events ORDER BY date DESC").fetchall()
        alls=c.execute("SELECT id FROM sessions WHERE status='complete' ORDER BY id DESC LIMIT 100").fetchall()
    buckets={(start+timedelta(days=i)).isoformat():{"date":(start+timedelta(days=i)).isoformat(),"bounty":0,"ess":0,"loot":0,"salvage":0,"bonus":0} for i in range(days)}
    for r in rs:
        if not r["ended_at"]:continue
        k=parse_iso(r["ended_at"]).date().isoformat()
        if k in buckets:
            buckets[k]["bounty"]+=money(r["combined_bounty"]);buckets[k]["bonus"]+=money(r["escalation_sale_value"])+money(r["rare_spawn_value"])
    sess=[]
    for s in ss:
        rr=[r for r in rs if r["session_id"]==s["id"]];d=dict(s);d["site_count"]=len(rr);d["bounty"]=sum(money(r["combined_bounty"]) for r in rr);d["bonus"]=sum(money(r["escalation_sale_value"])+money(r["rare_spawn_value"]) for r in rr);d["total"]=d["bounty"]+money(s["loot_value"])+money(s["salvage_value"])+d["bonus"];d["systems"]=", ".join(sorted(set(r["system_name"] or "Unknown" for r in rr))) if rr else "—";span=max(0,int((parse_iso(s["ended_at"])-parse_iso(s["started_at"])).total_seconds()));d["duration_label"]=f"{span//3600}h {(span%3600)//60}m" if span>=3600 else f"{span//60}m";sess.append(d)
        k=parse_iso(s["ended_at"]).date().isoformat()
        if k in buckets:buckets[k]["loot"]+=money(s["loot_value"]);buckets[k]["salvage"]+=money(s["salvage_value"])
    for e in ess:
        k=parse_iso(e["date"]).date().isoformat()
        if k in buckets:buckets[k]["ess"]+=money(e["amount"])
    return templates.TemplateResponse(request=request,name="history.html",context={"days":days,"runs":[enrich(r) for r in rs[:200]],"sessions":sess[:100],"ess":[dict(e) for e in ess[:100]],"all_sessions":[dict(s) for s in alls],"chart_data":json.dumps(list(buckets.values()))})

@app.post("/ess/{eid}/assign")
async def assign_ess(eid:int,session_id:str=Form("")):
    with db() as c:
        if session_id:c.execute("UPDATE ess_events SET session_id=?,match_status='manual' WHERE entry_id=?",(int(session_id),eid))
        else:c.execute("UPDATE ess_events SET session_id=NULL,match_status='unassigned' WHERE entry_id=?",(eid,))
    return RedirectResponse("/history",303)

if __name__=="__main__":
    import uvicorn; uvicorn.run("app:app",host=HOST,port=PORT,reload=False)
