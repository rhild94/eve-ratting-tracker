
import os,time,json,base64,sqlite3,secrets,asyncio,re,hashlib,threading
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from fastapi import FastAPI,Request,Form
from fastapi.responses import HTMLResponse,RedirectResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR=Path(__file__).resolve().parent
APP_VERSION="9.2.0"
load_dotenv(BASE_DIR/".env")
CLIENT_ID=os.getenv("EVE_CLIENT_ID","").strip()
CLIENT_SECRET=os.getenv("EVE_CLIENT_SECRET","").strip()
_render_host=os.getenv("RENDER_EXTERNAL_HOSTNAME","").strip()
CALLBACK_URL=os.getenv("EVE_CALLBACK_URL",f"https://{_render_host}/callback" if _render_host else "http://localhost:8000/callback").strip()
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

_HD_BACKGROUND_BYTES=None
def load_hd_background():
    global _HD_BACKGROUND_BYTES
    if _HD_BACKGROUND_BYTES is None:
        encoded="".join(
            (BASE_DIR/"static"/f"hd_bg_compact_{i:02d}.txt").read_text(encoding="utf-8").strip()
            for i in range(1,7)
        )
        encoded="".join(encoded.split())
        encoded += "=" * (-len(encoded) % 4)
        raw=base64.b64decode(encoded,validate=True)
        if not (raw.startswith(b"RIFF") and raw[8:12]==b"WEBP"):
            raise ValueError("Invalid HD background image header.")
        declared=int.from_bytes(raw[4:8],"little")+8
        if declared!=len(raw):
            raise ValueError(f"Incomplete HD background image: expected {declared} bytes, got {len(raw)}.")
        _HD_BACKGROUND_BYTES=raw
    return _HD_BACKGROUND_BYTES

@app.get("/art/eve-bg.webp")
async def eve_hd_background():
    return Response(
        content=load_hd_background(),
        media_type="image/webp",
        headers={"Cache-Control":"public, max-age=31536000, immutable"}
    )
DB=Path(os.getenv("TRACKER_DB_PATH",str(BASE_DIR/"ratting_tracker.db")))
DB.parent.mkdir(parents=True,exist_ok=True)
DB_PROCESS_LOCK=threading.RLock()
DATABASE_URL=os.getenv("DATABASE_URL","").strip()
USE_POSTGRES=bool(DATABASE_URL)
APP_ACCESS_KEY=os.getenv("APP_ACCESS_KEY","").strip()
ACCESS_COOKIE_VALUE=hashlib.sha256(("eve-ratting-tracker:"+APP_ACCESS_KEY).encode()).hexdigest() if APP_ACCESS_KEY else ""

class CompatCursor:
    def __init__(self,cur,lastrowid=None): self.cur=cur; self.lastrowid=lastrowid
    def fetchone(self): return self.cur.fetchone()
    def fetchall(self): return self.cur.fetchall()
    def __iter__(self): return iter(self.cur)

class PostgresConn:
    def __init__(self,conn): self.conn=conn
    def execute(self,sql,params=()):
        q=sql.replace("?","%s")
        cur=self.conn.cursor();cur.execute(q,params);return CompatCursor(cur)
    def __enter__(self): self.conn.__enter__(); return self
    def __exit__(self,*args): return self.conn.__exit__(*args)

class LockedDB:
    def __enter__(self):
        DB_PROCESS_LOCK.acquire()
        try:
            if USE_POSTGRES:
                self.raw=psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=10)
                self.conn=PostgresConn(self.raw)
            else:
                self.raw=sqlite3.connect(DB,timeout=30);self.raw.row_factory=sqlite3.Row
                self.raw.execute("PRAGMA busy_timeout=5000");self.conn=self.raw
            self.conn.__enter__();return self.conn
        except Exception:
            DB_PROCESS_LOCK.release();raise
    def __exit__(self,exc_type,exc,tb):
        try:return self.conn.__exit__(exc_type,exc,tb)
        finally:self.raw.close();DB_PROCESS_LOCK.release()

def db(): return LockedDB()
def col_exists(c,t,col):
    if USE_POSTGRES:return bool(c.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=? AND column_name=?",(t,col)).fetchone())
    return any(r["name"]==col for r in c.execute(f"PRAGMA table_info({t})"))
def ensure_col(c,t,d):
    if not col_exists(c,t,d.split()[0]):c.execute(f"ALTER TABLE {t} ADD COLUMN {d}")
def ensure_character_entry_keys(c):
    """ESI journal IDs are scoped to a character, not globally unique."""
    tables={
        "wallet_entries": (
            "CREATE TABLE wallet_entries_new("
            "entry_id INTEGER NOT NULL,character_id INTEGER NOT NULL,date TEXT NOT NULL,"
            "amount REAL NOT NULL,balance REAL,ref_type TEXT,description TEXT,raw_json TEXT NOT NULL,"
            "PRIMARY KEY(character_id,entry_id))",
            "INSERT OR IGNORE INTO wallet_entries_new(entry_id,character_id,date,amount,balance,ref_type,description,raw_json) "
            "SELECT entry_id,character_id,date,amount,balance,ref_type,description,raw_json FROM wallet_entries"
        ),
        "ess_events": (
            "CREATE TABLE ess_events_new("
            "entry_id INTEGER NOT NULL,character_id INTEGER NOT NULL,date TEXT NOT NULL,amount REAL NOT NULL,"
            "session_id INTEGER,match_status TEXT NOT NULL DEFAULT 'unassigned',"
            "PRIMARY KEY(character_id,entry_id))",
            "INSERT OR IGNORE INTO ess_events_new(entry_id,character_id,date,amount,session_id,match_status) "
            "SELECT entry_id,character_id,date,amount,session_id,match_status FROM ess_events"
        ),
    }
    if USE_POSTGRES:
        for table in tables:
            rows=c.execute("""SELECT tc.constraint_name,kcu.column_name,kcu.ordinal_position
                              FROM information_schema.table_constraints tc
                              JOIN information_schema.key_column_usage kcu
                                ON tc.constraint_name=kcu.constraint_name
                               AND tc.table_schema=kcu.table_schema
                              WHERE tc.table_schema='public' AND tc.table_name=? AND tc.constraint_type='PRIMARY KEY'
                              ORDER BY kcu.ordinal_position""",(table,)).fetchall()
            cols=[r["column_name"] for r in rows]
            if cols==["character_id","entry_id"]:
                continue
            if rows:
                constraint=rows[0]["constraint_name"].replace('"','""')
                c.execute(f'ALTER TABLE {table} DROP CONSTRAINT "{constraint}"')
            c.execute(f"ALTER TABLE {table} ADD PRIMARY KEY(character_id,entry_id)")
        return

    for table,(create_sql,copy_sql) in tables.items():
        info=c.execute(f"PRAGMA table_info({table})").fetchall()
        pkcols=[r["name"] for r in sorted((r for r in info if int(r["pk"] or 0)>0),key=lambda r:int(r["pk"]))]
        if pkcols==["character_id","entry_id"]:
            continue
        c.execute(f"DROP TABLE IF EXISTS {table}_new")
        c.execute(create_sql)
        c.execute(copy_sql)
        c.execute(f"DROP TABLE {table}")
        c.execute(f"ALTER TABLE {table}_new RENAME TO {table}")

def init_db():
    with db() as c:
        stmts=[
            "CREATE TABLE IF NOT EXISTS characters(character_id BIGINT PRIMARY KEY,name TEXT NOT NULL,access_token TEXT NOT NULL,refresh_token TEXT NOT NULL,expires_at BIGINT NOT NULL,connected_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY,created_at BIGINT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS skill_snapshots(id BIGSERIAL PRIMARY KEY,character_id BIGINT NOT NULL,captured_at TEXT NOT NULL,total_sp BIGINT NOT NULL,skills_json TEXT NOT NULL,queue_json TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS wallet_entries(entry_id BIGINT PRIMARY KEY,character_id BIGINT NOT NULL,date TEXT NOT NULL,amount DOUBLE PRECISION NOT NULL,balance DOUBLE PRECISION,ref_type TEXT,description TEXT,raw_json TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS runs(id BIGSERIAL PRIMARY KEY,anomaly TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT,participants_json TEXT NOT NULL,notes TEXT,status TEXT NOT NULL DEFAULT 'active',combined_bounty DOUBLE PRECISION DEFAULT 0,system_name TEXT,ships_json TEXT)",
            "CREATE TABLE IF NOT EXISTS type_names(type_id BIGINT PRIMARY KEY,name TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS sessions(id BIGSERIAL PRIMARY KEY,started_at TEXT NOT NULL,ended_at TEXT,status TEXT NOT NULL DEFAULT 'active',loot_value DOUBLE PRECISION DEFAULT 0,salvage_value DOUBLE PRECISION DEFAULT 0,notes TEXT)",
            "CREATE TABLE IF NOT EXISTS ess_events(entry_id BIGINT PRIMARY KEY,character_id BIGINT NOT NULL,date TEXT NOT NULL,amount DOUBLE PRECISION NOT NULL,session_id BIGINT,match_status TEXT NOT NULL DEFAULT 'unassigned')",
            "CREATE TABLE IF NOT EXISTS esi_cache(cache_key TEXT PRIMARY KEY,payload_json TEXT NOT NULL,expires_at TEXT,updated_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS fits(id TEXT PRIMARY KEY,character_id BIGINT,character_name TEXT,ship TEXT NOT NULL,name TEXT NOT NULL,raw_text TEXT NOT NULL,groups_json TEXT NOT NULL,type_ids_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS esi_sync_state(id INTEGER PRIMARY KEY,last_attempt TEXT,last_success TEXT,last_error TEXT,next_check TEXT)"
        ]
        if not USE_POSTGRES:
            stmts=[x.replace("BIGSERIAL PRIMARY KEY","INTEGER PRIMARY KEY AUTOINCREMENT").replace("BIGINT","INTEGER").replace("DOUBLE PRECISION","REAL") for x in stmts]
        for q in stmts:c.execute(q)
        ensure_character_entry_keys(c)
        if USE_POSTGRES:c.execute("INSERT INTO esi_sync_state(id) VALUES(1) ON CONFLICT(id) DO NOTHING")
        else:
            c.execute("INSERT OR IGNORE INTO esi_sync_state(id) VALUES(1)")
        ensure_col(c,"oauth_states","code_verifier TEXT")
        for d in ["variant TEXT","session_id BIGINT","escalation_name TEXT","escalation_status TEXT","escalation_sale_value DOUBLE PRECISION DEFAULT 0","rare_spawn_type TEXT","rare_spawn_name TEXT","rare_spawn_value DOUBLE PRECISION DEFAULT 0","paused_at TEXT","paused_seconds DOUBLE PRECISION DEFAULT 0","esi_synced_at TEXT","fit_selection_json TEXT"]:
            ensure_col(c,"runs",d if USE_POSTGRES else d.replace("BIGINT","INTEGER").replace("DOUBLE PRECISION","REAL"))
        for d in ["cache_system_name TEXT","cache_ship_name TEXT","last_esi_sync TEXT","character_role TEXT DEFAULT 'alt'","connected INTEGER DEFAULT 1"]:
            ensure_col(c,"characters",d)
        # Preserve both realized escalation outcomes; pending and expired values are not income.
        c.execute("UPDATE runs SET escalation_sale_value=0 WHERE COALESCE(escalation_status,'') NOT IN ('Sold','Ran Myself') AND COALESCE(escalation_sale_value,0)<>0")
init_db()

@app.middleware("http")
async def access_gate(request:Request,call_next):
    if not APP_ACCESS_KEY or request.url.path in {"/access","/health"} or request.url.path.startswith("/static/") or request.url.path.startswith("/art/"):
        return await call_next(request)
    if secrets.compare_digest(request.cookies.get("tracker_access",""),ACCESS_COOKIE_VALUE):
        return await call_next(request)
    return HTMLResponse("""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EVE Ratting Tracker</title></head><body style="font-family:system-ui;background:#08111d;color:#e7edf7;display:grid;place-items:center;min-height:100vh"><form method="post" action="/access" style="width:min(420px,90vw);padding:28px;border:1px solid #27415c;border-radius:12px;background:#0d1928"><h2>EVE Ratting Tracker</h2><p>Enter the private access key.</p><input type="password" name="key" autofocus style="box-sizing:border-box;width:100%;padding:12px;margin:12px 0;background:#07111c;color:white;border:1px solid #34506e;border-radius:7px"><button style="padding:10px 16px">Open tracker</button></form></body></html>""",401)

@app.post("/access")
async def access_login(key:str=Form("")):
    if not APP_ACCESS_KEY or not secrets.compare_digest(key,APP_ACCESS_KEY):
        return HTMLResponse("Invalid access key.",401)
    r=RedirectResponse("/",303)
    r.set_cookie("tracker_access",ACCESS_COOKIE_VALUE,httponly=True,samesite="lax",secure=True,max_age=60*60*24*30)
    return r

@app.get("/health")
async def health(): return {"ok":True,"version":APP_VERSION}

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
    m=re.search(r"(?:^|,)\s*max-age=(\d+)",cc,re.I)
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
    data={"grant_type":"refresh_token","refresh_token":row["refresh_token"]}
    auth=None
    if CLIENT_SECRET:auth=(CLIENT_ID,CLIENT_SECRET)
    else:data["client_id"]=CLIENT_ID
    async with httpx.AsyncClient(timeout=30) as cl:
        r=await cl.post(SSO_TOKEN,auth=auth,data=data)
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
        with db() as c:
            if USE_POSTGRES:c.execute("INSERT INTO type_names(type_id,name) VALUES(?,?) ON CONFLICT(type_id) DO UPDATE SET name=EXCLUDED.name",(tid,n))
            else:c.execute("INSERT OR REPLACE INTO type_names VALUES(?,?)",(tid,n))
        return n
    except:return str(tid)
async def sys_name(sid):
    try:return (await esi_get(f"/universe/systems/{sid}/")).get("name",str(sid))
    except:return str(sid) if sid else None

async def resolve_type_names(type_ids):
    ids=sorted({int(x) for x in type_ids if x})
    if not ids:return {}
    out={}
    with db() as c:
        rows=c.execute(f"SELECT type_id,name FROM type_names WHERE type_id IN ({','.join('?'*len(ids))})",ids).fetchall()
        out.update({int(r["type_id"]):r["name"] for r in rows})
    missing=[x for x in ids if x not in out]
    if missing:
        try:
            h={"Accept":"application/json","Content-Type":"application/json","User-Agent":"Rafael-EVE-Ratting-Tracker/8.3","X-Compatibility-Date":COMPAT_DATE}
            async with httpx.AsyncClient(timeout=15) as cl:
                r=await cl.post(ESI+"/universe/names/",headers=h,json=missing)
                r.raise_for_status()
                data=r.json()
            with db() as c:
                for item in data:
                    tid=int(item.get("id",0));name=item.get("name")
                    if tid and name:
                        out[tid]=name
                        c.execute("INSERT INTO type_names(type_id,name) VALUES(?,?) ON CONFLICT(type_id) DO UPDATE SET name=EXCLUDED.name",(tid,name)) if USE_POSTGRES else c.execute("INSERT OR REPLACE INTO type_names(type_id,name) VALUES(?,?)",(tid,name))
        except Exception:
            pass
    for tid in ids:out.setdefault(tid,str(tid))
    return out


def auto_match_ess(c,cid,eid,dt):
    cand=c.execute("SELECT id,ended_at FROM sessions WHERE status='complete' AND ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT 8").fetchall()
    p=[]
    for s in cand:
        x=(dt-parse_iso(s["ended_at"])).total_seconds()
        if 0<=x<=14400:p.append((x,s["id"]))
    if len(p)==1:c.execute("UPDATE ess_events SET session_id=?,match_status='auto' WHERE character_id=? AND entry_id=?",(p[0][1],cid,eid))

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
            c.execute("INSERT INTO wallet_entries(entry_id,character_id,date,amount,balance,ref_type,description,raw_json) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(character_id,entry_id) DO NOTHING",(j.get("id"),cid,j.get("date"),money(j.get("amount")),j.get("balance"),j.get("ref_type"),j.get("description"),json.dumps(j))) if USE_POSTGRES else c.execute("INSERT OR IGNORE INTO wallet_entries(entry_id,character_id,date,amount,balance,ref_type,description,raw_json) VALUES(?,?,?,?,?,?,?,?)",(j.get("id"),cid,j.get("date"),money(j.get("amount")),j.get("balance"),j.get("ref_type"),j.get("description"),json.dumps(j)))
            if "ess" in (j.get("ref_type") or "").lower() and money(j.get("amount"))>0:
                c.execute("INSERT INTO ess_events(entry_id,character_id,date,amount) VALUES(?,?,?,?) ON CONFLICT(character_id,entry_id) DO NOTHING",(j.get("id"),cid,j.get("date"),money(j.get("amount")))) if USE_POSTGRES else c.execute("INSERT OR IGNORE INTO ess_events(entry_id,character_id,date,amount) VALUES(?,?,?,?)",(j.get("id"),cid,j.get("date"),money(j.get("amount"))))
                try:auto_match_ess(c,cid,j.get("id"),parse_iso(j.get("date")))
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
    if not s:return {"total_sp":0,"queue":[],"changes":[],"captured_at":None,"has_snapshot":False}
    queue_raw=json.loads(s[0]["queue_json"])[:queue_limit]
    changes_raw=[]
    if len(s)>1:
        old={x["skill_id"]:x for x in json.loads(s[1]["skills_json"])}
        for cur in json.loads(s[0]["skills_json"]):
            a=int(old.get(cur["skill_id"],{}).get("trained_skill_level",0));b=int(cur.get("trained_skill_level",0))
            if b>a:changes_raw.append((cur["skill_id"],a,b))
    names=await resolve_type_names([x.get("skill_id") for x in queue_raw]+[x[0] for x in changes_raw])
    q=[{"skill":names.get(int(x.get("skill_id") or 0),str(x.get("skill_id") or "")),"level":x.get("finished_level"),"finish_date":x.get("finish_date"),"start_date":x.get("start_date")} for x in queue_raw]
    ch=[{"skill":names.get(int(tid),str(tid)),"from":a,"to":b} for tid,a,b in changes_raw]
    return {"total_sp":s[0]["total_sp"],"queue":q,"changes":ch,"captured_at":s[0]["captured_at"],"has_snapshot":True}

def active_session(c):return c.execute("SELECT * FROM sessions WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
def ensure_session(c,st):
    s=active_session(c)
    if s:return s["id"]
    if USE_POSTGRES:return c.execute("INSERT INTO sessions(started_at,status) VALUES(?,'active') RETURNING id",(st,)).fetchone()["id"]
    return c.execute("INSERT INTO sessions(started_at,status) VALUES(?,'active')",(st,)).lastrowid

def cached_run_context(pids):
    with db() as c:
        rows=c.execute(f"SELECT character_id,name,cache_system_name,cache_ship_name FROM characters WHERE character_id IN ({','.join('?'*len(pids))})",pids).fetchall() if pids else []
    systems=[r["cache_system_name"] for r in rows if r["cache_system_name"]]
    system=systems[0] if systems and all(x==systems[0] for x in systems) else (", ".join(sorted(set(systems))) if systems else None)
    ships=[{"character":r["name"],"ship":r["cache_ship_name"]} for r in rows if r["cache_ship_name"]]
    return system,ships

def _overlap_seconds(a1,a2,b1,b2):
    return max(0.0,(min(a2,b2)-max(a1,b1)).total_seconds())

def reconcile_bounties():
    """Allocate real ESI bounty ticks across completed sites by time overlap.

    EVE wallet bounty_prizes entries are periodic aggregate payouts, not
    per-site records. A payout can arrive after a site ends and can span
    multiple sites. We therefore preserve the exact ESI payout total while
    distributing it proportionally across the completed runs that overlap
    the payout interval for each participating character.
    """
    with db() as c:
        runs=c.execute("SELECT * FROM runs WHERE status='complete' AND ended_at IS NOT NULL ORDER BY started_at").fetchall()
        chars=[x["character_id"] for x in c.execute("SELECT character_id FROM characters")]
        c.execute("UPDATE runs SET combined_bounty=0")
        latest_tick={}
        allocations={int(r["id"]):0.0 for r in runs}
        parsed_runs=[]
        for r in runs:
            try:
                parsed_runs.append((r,parse_iso(r["started_at"]),parse_iso(r["ended_at"]),set(json.loads(r["participants_json"]))))
            except Exception:
                continue

        for cid in chars:
            ticks=c.execute("""SELECT date,amount FROM wallet_entries
                               WHERE character_id=? AND LOWER(COALESCE(ref_type,''))='bounty_prizes' AND amount>0
                               ORDER BY date""",(cid,)).fetchall()
            prev_dt=None
            for tick in ticks:
                try: tick_dt=parse_iso(tick["date"])
                except Exception: continue
                latest_tick[cid]=tick_dt
                # Normally bounty payouts are periodic. If the prior tick is
                # missing/stale, use a conservative 20-minute earning window.
                if prev_dt and 0 < (tick_dt-prev_dt).total_seconds() <= 1800:
                    window_start=prev_dt
                else:
                    window_start=tick_dt-timedelta(minutes=20)
                prev_dt=tick_dt

                overlaps=[]
                for r,rs,re,pids in parsed_runs:
                    if cid not in pids: continue
                    sec=_overlap_seconds(window_start,tick_dt,rs,re)
                    if sec>0: overlaps.append((int(r["id"]),sec))
                total_sec=sum(x[1] for x in overlaps)
                if total_sec<=0: continue
                amount=money(tick["amount"])
                for rid,sec in overlaps:
                    allocations[rid]+=amount*(sec/total_sec)

        now=utcnow()
        for r,rs,re,pids in parsed_runs:
            rid=int(r["id"])
            c.execute("UPDATE runs SET combined_bounty=? WHERE id=?",(allocations.get(rid,0.0),rid))
            # A site remains visibly pending until every participant has a
            # bounty tick at/after site completion, or enough time has passed
            # that no additional tick should normally be expected.
            complete_ticks=bool(pids) and all(latest_tick.get(cid) and latest_tick[cid]>=re for cid in pids)
            aged=(now-re).total_seconds()>=1800
            c.execute("UPDATE runs SET esi_synced_at=? WHERE id=?",
                      (iso(now) if (complete_ticks or aged) else None,rid))


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
    try:d["fit_selection"]=json.loads(d.get("fit_selection_json") or "{}")
    except:d["fit_selection"]={}
    d["is_paused"]=bool(d.get("paused_at"))
    d["escalation_sales"]=money(d.get("escalation_sale_value")) if d.get("escalation_status")=="Sold" else 0
    d["escalation_loot"]=money(d.get("escalation_sale_value")) if d.get("escalation_status")=="Ran Myself" else 0
    d["bonus"]=d["escalation_sales"]+d["escalation_loot"]+money(d.get("rare_spawn_value"))
    d["total_isk"]=money(d.get("combined_bounty"))+d["bonus"]
    return d

def session_performance(days=30):
    days=30 if days==30 else 7 if days==7 else 30
    now=utcnow()
    cutoff=now-timedelta(days=days)
    with db() as c:
        sessions=c.execute("SELECT * FROM sessions WHERE status='complete' AND ended_at IS NOT NULL ORDER BY ended_at").fetchall()
        runs=c.execute("SELECT * FROM runs WHERE status='complete' AND ended_at IS NOT NULL ORDER BY ended_at").fetchall()
        ess=c.execute("SELECT * FROM ess_events WHERE session_id IS NOT NULL").fetchall()
    rows=[]
    total_income=total_ratting=total_seconds=0.0
    best=None
    total_sites=0
    for ses in sessions:
        try:end=parse_iso(ses["ended_at"])
        except:continue
        if end<cutoff or end>now:continue
        rr=[r for r in runs if r["session_id"]==ses["id"]]
        if not rr:continue
        bounty=sum(money(r["combined_bounty"]) for r in rr)
        bonus=sum((money(r["escalation_sale_value"]) if r["escalation_status"] in ("Sold", "Ran Myself") else 0)+money(r["rare_spawn_value"]) for r in rr)
        escalation_sales=sum(enrich(r)["escalation_sales"] for r in rr)
        escalation_loot=sum(enrich(r)["escalation_loot"] for r in rr)
        ess_total=sum(money(e["amount"]) for e in ess if e["session_id"]==ses["id"])
        loot=money(ses["loot_value"]);salvage=money(ses["salvage_value"])
        ratting=bounty+ess_total
        total=ratting+loot+salvage+bonus
        seconds=max(1,sum(effective_run_seconds(r) for r in rr))
        ratting_hr=ratting/seconds*3600
        total_hr=total/seconds*3600
        participants=set()
        for r in rr:
            try:
                participants.update(int(x) for x in json.loads(r["participants_json"] or "[]"))
            except Exception:
                pass
        row={"id":ses["id"],"date":end.strftime("%b %d"),"ended_at":ses["ended_at"],"duration_seconds":seconds,
             "sites":len(rr),"participants":len(participants),"bounty":bounty,"ess":ess_total,"loot":loot,"salvage":salvage,"bonus":bonus,
             "escalation_sales":escalation_sales,"escalation_loot":escalation_loot,
             "ratting_isk":ratting,"total_isk":total,"ratting_isk_hr":ratting_hr,"total_isk_hr":total_hr}
        rows.append(row)
        total_income+=total;total_ratting+=ratting;total_seconds+=seconds;total_sites+=len(rr)
        if best is None or ratting_hr>best["ratting_isk_hr"]:best=row
    avg_ratting_hr=total_ratting/total_seconds*3600 if total_seconds else 0
    avg_total_hr=total_income/total_seconds*3600 if total_seconds else 0
    return {"days":days,"rows":rows,"total_isk":total_income,"ratting_isk":total_ratting,
            "avg_ratting_isk_hr":avg_ratting_hr,"avg_total_isk_hr":avg_total_hr,
            "sessions":len(rows),"sites":total_sites,"total_seconds":total_seconds,"best":best}

async def dashboard_payload():
    with db() as c:
        chars=c.execute("SELECT character_id,name,COALESCE(character_role,'alt') AS character_role FROM characters WHERE COALESCE(connected,1)=1 ORDER BY CASE WHEN character_role='main' THEN 0 ELSE 1 END, connected_at").fetchall()
        ar=c.execute("SELECT * FROM runs WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
        recent=c.execute("SELECT * FROM runs WHERE status='complete' ORDER BY id DESC LIMIT 12").fetchall()
        ses=active_session(c); sr=c.execute("SELECT * FROM runs WHERE session_id=? ORDER BY id",(ses["id"],)).fetchall() if ses else []
    characters=[{"id":x["character_id"],"name":x["name"],"role":x["character_role"] or "alt","portrait":f"https://images.evetech.net/characters/{x['character_id']}/portrait?size=64"} for x in chars]
    today=utcnow().date()
    stats={"today_isk":0,"today_sites":0,"today_seconds":0,"today_ess":0}

    # "Today's" wallet cards are direct ESI day totals across every currently
    # connected character. They intentionally do not depend on tracker runs,
    # participant attribution, sessions, or ESS auto-matching.
    with db() as c:
        wallet_today=c.execute("""SELECT w.character_id,w.date,w.amount,w.ref_type
                                  FROM wallet_entries w
                                  INNER JOIN characters ch ON ch.character_id=w.character_id
                                  WHERE w.amount>0""").fetchall()
    for w in wallet_today:
        try:
            if parse_iso(w["date"]).date()!=today:continue
        except Exception:
            continue
        ref=(w["ref_type"] or "").lower()
        if ref=="bounty_prizes":
            stats["today_isk"]+=money(w["amount"])
        if "ess" in ref:
            stats["today_ess"]+=money(w["amount"])

    # Site count/time and Bounty ISK/hr remain tracker-performance metrics.
    # They use reconciled run bounty so unrelated wallet activity cannot
    # inflate the measured ratting efficiency.
    tracked_today_bounty=0.0
    with db() as c:
        completed=c.execute("SELECT * FROM runs WHERE status='complete' AND ended_at IS NOT NULL").fetchall()
    for r in completed:
        if r["ended_at"] and parse_iso(r["ended_at"]).date()==today:
            e=enrich(r)
            tracked_today_bounty+=money(r["combined_bounty"])
            stats["today_sites"]+=1
            stats["today_seconds"]+=e["duration_seconds"]
    stats["avg_isk_hr"]=tracked_today_bounty/stats["today_seconds"]*3600 if stats["today_seconds"] else 0
    si=None
    if ses:
        done=[r for r in sr if r["status"]=="complete"]
        si={"id":ses["id"],"sites":len(done),"bounty":sum(money(r["combined_bounty"]) for r in done)}
    with db() as c:
        pending_esi=c.execute("SELECT COUNT(*) AS n FROM runs WHERE status='complete' AND esi_synced_at IS NULL").fetchone()["n"]
        last_sync=c.execute("SELECT MAX(last_esi_sync) AS t FROM characters WHERE COALESCE(connected,1)=1").fetchone()["t"]
        sync_state=c.execute("SELECT * FROM esi_sync_state WHERE id=1").fetchone()
    esi_state={"pending_runs":pending_esi,"last_sync":last_sync,"interval_minutes":AUTO_SYNC_INTERVAL_SECONDS//60,"configured":bool(CLIENT_ID),"connected_characters":len(characters)}
    if sync_state:esi_state.update({k:sync_state[k] for k in ["last_attempt","last_success","last_error","next_check"]})
    return {"characters":characters,"active":enrich(ar) if ar else None,"recent":[enrich(r) for r in recent],"stats":stats,"session":si,"anomalies":ANOMALIES,"esi":esi_state}

@app.get("/",response_class=HTMLResponse)
async def home(request:Request):
    payload=await dashboard_payload()
    boot={"page":"tracker","data":payload,"config_ok":bool(CLIENT_ID),"version":APP_VERSION}
    return templates.TemplateResponse(request=request,name="react.html",context={"boot":boot,"title":"Tracker"})

@app.get("/dashboard",response_class=HTMLResponse)
async def dashboard_page(request:Request,days:int=30):
    perf=session_performance(days)
    boot={"page":"dashboard","perf":perf,"version":APP_VERSION}
    return templates.TemplateResponse(request=request,name="react.html",context={"boot":boot,"title":"Dashboard"})

@app.get("/setup",response_class=HTMLResponse)
async def setup_page(request:Request):
    return templates.TemplateResponse(request=request,name="setup.html",context={"configured":bool(CLIENT_ID),"version":APP_VERSION})

@app.post("/setup")
async def setup_save(client_id:str=Form("")):
    global CLIENT_ID
    cid=client_id.strip()
    if not cid:return HTMLResponse("Client ID is required.",400)
    env_path=BASE_DIR/".env"
    existing={}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k,v=line.split("=",1);existing[k.strip()]=v.strip()
    existing["EVE_CLIENT_ID"]=cid
    existing.setdefault("EVE_CALLBACK_URL",CALLBACK_URL)
    env_path.write_text("\n".join(f"{k}={v}" for k,v in existing.items())+"\n",encoding="utf-8")
    CLIENT_ID=cid
    return RedirectResponse("/",303)

@app.post("/api/character/{cid}/main")
async def api_set_main_character(cid:int):
    with db() as c:
        if not c.execute("SELECT 1 FROM characters WHERE character_id=? AND COALESCE(connected,1)=1",(cid,)).fetchone():
            return JSONResponse({"ok":False,"error":"Connected character not found."},404)
        c.execute("UPDATE characters SET character_role='alt' WHERE COALESCE(connected,1)=1")
        c.execute("UPDATE characters SET character_role='main' WHERE character_id=?",(cid,))
    return JSONResponse({"ok":True})

@app.delete("/api/character/{cid}")
async def api_remove_character(cid:int):
    """Disconnect a character while preserving every historical record."""
    with db() as c:
        row=c.execute("SELECT character_id,name,COALESCE(character_role,'alt') AS character_role FROM characters WHERE character_id=? AND COALESCE(connected,1)=1",(cid,)).fetchone()
        if not row:
            return JSONResponse({"ok":False,"error":"Connected character not found."},404)
        for active in c.execute("SELECT id,participants_json FROM runs WHERE status='active'").fetchall():
            try:pids=[int(x) for x in json.loads(active["participants_json"] or "[]")]
            except Exception:pids=[]
            if cid in pids:
                return JSONResponse({"ok":False,"error":"Complete or cancel the active site before removing this character."},409)
        others=c.execute("SELECT character_id,name FROM characters WHERE character_id<>? AND COALESCE(connected,1)=1 ORDER BY connected_at",(cid,)).fetchall()
        if row["character_role"]=="main" and others:
            return JSONResponse({"ok":False,"error":"Set another connected character as Main before removing the current Main character.","requires_new_main":True,"alternatives":[dict(x) for x in others]},409)
        c.execute("UPDATE characters SET connected=0,character_role='alt',access_token='',refresh_token='',expires_at=0 WHERE character_id=?",(cid,))
    return JSONResponse({"ok":True,"character_id":cid})

@app.get("/api/dashboard")
async def api_dashboard(): return JSONResponse(await dashboard_payload())

def fit_payload(row):
    d=dict(row)
    try:d["groups"]=json.loads(d.pop("groups_json") or "{}")
    except:d["groups"]={}
    try:
        tids=json.loads(d.pop("type_ids_json") or "{}")
        d.update(tids)
    except:pass
    return d

@app.get("/api/fits")
async def api_fits():
    with db() as c:rows=c.execute("SELECT * FROM fits ORDER BY updated_at DESC,name").fetchall()
    return JSONResponse({"ok":True,"fits":[fit_payload(r) for r in rows]})

@app.post("/api/fits/resolve")
async def api_resolve_fit_types(request:Request):
    body=await request.json();names=[str(x).strip() for x in body.get("names",[]) if str(x).strip()][:250]
    if not names:return JSONResponse({"ok":True,"types":{}})
    try:
        h={"Accept":"application/json","Content-Type":"application/json","User-Agent":"Rafael-EVE-Ratting-Tracker/Beta","X-Compatibility-Date":COMPAT_DATE}
        async with httpx.AsyncClient(timeout=20) as cl:
            r=await cl.post(ESI+"/universe/ids/",headers=h,json=names);r.raise_for_status();data=r.json()
        types={x.get("name"):x.get("id") for x in data.get("inventory_types",[]) if x.get("name") and x.get("id")}
        return JSONResponse({"ok":True,"types":types})
    except Exception as e:
        return JSONResponse({"ok":False,"types":{},"error":f"{type(e).__name__}: {e}"},502)

@app.post("/api/fits")
async def api_save_fit(request:Request):
    body=await request.json();fid=str(body.get("id") or secrets.token_hex(16));ship=str(body.get("ship") or '').strip();name=str(body.get("name") or '').strip()
    if not ship or not name:return JSONResponse({"ok":False,"error":"Ship and fit name are required."},400)
    now=iso();created=str(body.get("created_at") or now);cid=body.get("character_id")
    try:cid=int(cid) if cid not in (None,'') else None
    except:cid=None
    groups=body.get("groups") or {};type_ids={"ship_type_id":body.get("ship_type_id")}
    with db() as c:
        c.execute("""INSERT INTO fits(id,character_id,character_name,ship,name,raw_text,groups_json,type_ids_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(id) DO UPDATE SET character_id=excluded.character_id,character_name=excluded.character_name,ship=excluded.ship,name=excluded.name,raw_text=excluded.raw_text,groups_json=excluded.groups_json,type_ids_json=excluded.type_ids_json,updated_at=excluded.updated_at""",
                  (fid,cid,str(body.get("character_name") or "Unassigned"),ship,name,str(body.get("raw_text") or ""),json.dumps(groups),json.dumps(type_ids),created,now))
        row=c.execute("SELECT * FROM fits WHERE id=?",(fid,)).fetchone()
    return JSONResponse({"ok":True,"fit":fit_payload(row)})

@app.delete("/api/fits/{fit_id}")
async def api_delete_fit(fit_id:str):
    with db() as c:c.execute("DELETE FROM fits WHERE id=?",(fit_id,))
    return JSONResponse({"ok":True})

@app.get("/login")
async def login():
    if not CLIENT_ID:return HTMLResponse("EVE connection is not configured yet. The local tracker is fully available; add a Client ID in Settings when you want to connect ESI.",503)
    st=secrets.token_urlsafe(32)
    verifier=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    with db() as c:c.execute("INSERT INTO oauth_states(state,created_at,code_verifier) VALUES(?,?,?)",(st,int(time.time()),verifier))
    return RedirectResponse(SSO_AUTHORIZE+"?"+urlencode({"response_type":"code","redirect_uri":CALLBACK_URL,"client_id":CLIENT_ID,"scope":" ".join(SCOPES),"state":st,"code_challenge":challenge,"code_challenge_method":"S256"}))
@app.get("/callback")
async def callback(code:str,state:str):
    with db() as c:
        row=c.execute("SELECT * FROM oauth_states WHERE state=?",(state,)).fetchone()
        if not row:return HTMLResponse("Invalid OAuth state",400)
        verifier=row["code_verifier"]
        c.execute("DELETE FROM oauth_states WHERE state=?",(state,))
    data={"grant_type":"authorization_code","code":code,"redirect_uri":CALLBACK_URL}
    auth=None
    if verifier:
        data.update({"client_id":CLIENT_ID,"code_verifier":verifier})
    elif CLIENT_SECRET:
        auth=(CLIENT_ID,CLIENT_SECRET)
    async with httpx.AsyncClient(timeout=30) as cl:
        r=await cl.post(SSO_TOKEN,auth=auth,data=data);r.raise_for_status();t=r.json()
    cid=charid(t["access_token"]);pub=await esi_get(f"/characters/{cid}/")
    with db() as c:
        has_main=c.execute("SELECT 1 FROM characters WHERE character_role='main' AND COALESCE(connected,1)=1 LIMIT 1").fetchone()
        role="alt" if has_main else "main"
        c.execute("""INSERT INTO characters(character_id,name,access_token,refresh_token,expires_at,connected_at,character_role,connected) VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(character_id) DO UPDATE SET name=excluded.name,access_token=excluded.access_token,refresh_token=excluded.refresh_token,expires_at=excluded.expires_at,connected_at=excluded.connected_at,character_role=excluded.character_role,connected=1""",(cid,pub.get("name",str(cid)),t["access_token"],t["refresh_token"],int(time.time())+int(t.get("expires_in",1200)),iso(),role))
    await sync_character(cid)
    return RedirectResponse("/",302)

async def run_esi_sync(source="manual"):
    attempt=iso()
    next_check=iso(utcnow()+timedelta(seconds=AUTO_SYNC_INTERVAL_SECONDS))
    with db() as c:
        c.execute("UPDATE esi_sync_state SET last_attempt=?,next_check=? WHERE id=1",(attempt,next_check))
        ids=[x["character_id"] for x in c.execute("SELECT character_id FROM characters WHERE COALESCE(connected,1)=1")]
    errors=[]
    for cid in ids:
        try:await sync_character(cid)
        except Exception as e:errors.append(f"{cid}: {type(e).__name__}: {e}")
    synced=iso()
    if not errors:
        try:reconcile_bounties()
        except Exception as e:errors.append(f"bounty reconciliation: {type(e).__name__}: {e}")
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
    st=iso()
    client_started=body.get("client_started_at")
    if client_started:
        try:
            candidate=parse_iso(client_started)
            delta=abs((utcnow()-candidate).total_seconds())
            if delta<=180: st=iso(candidate)
        except: pass
    system,ships=cached_run_context(pids)
    with db() as c:
        if c.execute("SELECT 1 FROM runs WHERE status='active'").fetchone():return JSONResponse({"ok":False,"error":"A site is already running."},409)
        sid=ensure_session(c,st)
        rid=(c.execute("INSERT INTO runs(anomaly,variant,started_at,participants_json,notes,status,system_name,ships_json,session_id,esi_synced_at) VALUES(?,?,?,?,?,'active',?,?,?,NULL) RETURNING id",(anomaly,variant or None,st,json.dumps(pids),notes,system,json.dumps(ships),sid)).fetchone()["id"] if USE_POSTGRES else c.execute("INSERT INTO runs(anomaly,variant,started_at,participants_json,notes,status,system_name,ships_json,session_id,esi_synced_at) VALUES(?,?,?,?,?,'active',?,?,?,NULL)",(anomaly,variant or None,st,json.dumps(pids),notes,system,json.dumps(ships),sid)).lastrowid)
        c.execute("UPDATE runs SET fit_selection_json=? WHERE id=?",(json.dumps(body.get("fit_selection") or {}),rid))
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
        escalation_status=b.get("escalation_status") or None
        values=(
            b.get("escalation_name") or None,
            escalation_status,
            max(0,money(b.get("escalation_sale_value"))) if escalation_status in ("Sold", "Ran Myself") else 0,
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
            except (sqlite3.OperationalError,psycopg.OperationalError) as e:
                last_error=e
                if USE_POSTGRES or "locked" not in str(e).lower():raise
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
    for attempt in range(3):
        try:
            with db() as c:
                r=c.execute("SELECT id FROM runs WHERE id=?",(rid,)).fetchone()
                if not r:return JSONResponse({"ok":False,"error":"Run not found."},404)
                c.execute("DELETE FROM runs WHERE id=?",(rid,))
            return JSONResponse({"ok":True})
        except (sqlite3.OperationalError,psycopg.OperationalError) as e:
            if USE_POSTGRES or "locked" not in str(e).lower():raise
            if attempt==2:return JSONResponse({"ok":False,"error":"Database is busy with an ESI update. Try again in a moment."},503)
            await asyncio.sleep(.15)

@app.post("/api/session/end")
async def api_end_session(request:Request):
    b=await request.json()
    with db() as c:
        s=active_session(c)
        if not s:return JSONResponse({"ok":False,"error":"No active session."},404)
        if c.execute("SELECT 1 FROM runs WHERE session_id=? AND status='active'",(s["id"],)).fetchone():
            return JSONResponse({"ok":False,"error":"Complete the active site before ending this session."},409)
        last=c.execute("SELECT ended_at FROM runs WHERE session_id=? AND status='complete' ORDER BY ended_at DESC LIMIT 1",(s["id"],)).fetchone()
        end=last["ended_at"] if last else iso()
        c.execute("UPDATE sessions SET ended_at=?,status='complete',loot_value=?,salvage_value=?,notes=? WHERE id=?",(end,max(0,money(b.get("loot_value"))),max(0,money(b.get("salvage_value"))),(b.get("notes") or "").strip(),s["id"]))
        for e in c.execute("SELECT * FROM ess_events WHERE session_id IS NULL"):
            try:auto_match_ess(c,e["character_id"],e["entry_id"],parse_iso(e["date"]))
            except:pass
    return JSONResponse({"ok":True})

@app.get("/api/session/{sid}")
async def api_get_session(sid:int):
    with db() as c:s=c.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()
    if not s:return JSONResponse({"ok":False,"error":"Session not found."},404)
    return JSONResponse({"ok":True,"session":dict(s)})

@app.post("/api/session/{sid}")
async def api_update_session(sid:int,request:Request):
    b=await request.json()
    with db() as c:
        if not c.execute("SELECT id FROM sessions WHERE id=?",(sid,)).fetchone():
            return JSONResponse({"ok":False,"error":"Session not found."},404)
        c.execute("UPDATE sessions SET loot_value=?,salvage_value=?,notes=? WHERE id=?",
                  (max(0,money(b.get("loot_value"))),max(0,money(b.get("salvage_value"))),(b.get("notes") or "").strip(),sid))
    return JSONResponse({"ok":True})

@app.delete("/api/session/{sid}")
async def api_delete_session(sid:int):
    for attempt in range(3):
        try:
            with db() as c:
                c.execute("UPDATE ess_events SET session_id=NULL,match_status='unassigned' WHERE session_id=?",(sid,))
                c.execute("DELETE FROM runs WHERE session_id=?",(sid,))
                c.execute("DELETE FROM sessions WHERE id=?",(sid,))
            return JSONResponse({"ok":True})
        except (sqlite3.OperationalError,psycopg.OperationalError) as e:
            if USE_POSTGRES or "locked" not in str(e).lower():raise
            if attempt==2:return JSONResponse({"ok":False,"error":"Database is busy with an ESI update. Try again in a moment."},503)
            await asyncio.sleep(.15)

def progression_site_performance(days=30):
    days=30 if days==30 else 7 if days==7 else 30
    now=utcnow();cutoff=now-timedelta(days=days)
    with db() as c:
        rows=c.execute("SELECT * FROM runs WHERE status='complete' AND ended_at IS NOT NULL ORDER BY ended_at DESC").fetchall()
    groups={}
    for r in rows:
        try:end=parse_iso(r["ended_at"])
        except Exception:continue
        if not (cutoff<=end<=now):continue
        e=enrich(r);name=(r["anomaly"] or "Other").strip() or "Other"
        g=groups.setdefault(name,{"name":name,"runs":0,"income":0.0,"seconds":0.0,"isk_hr_sum":0.0,"best_run":0.0})
        realized=money(e.get("total_isk"));seconds=effective_run_seconds(r)
        g["runs"]+=1;g["income"]+=realized;g["seconds"]+=seconds;g["isk_hr_sum"]+=money(e.get("isk_hr"));g["best_run"]=max(g["best_run"],realized)
    out=[]
    for g in groups.values():
        n=max(1,g["runs"]);out.append({**g,"avg_isk":g["income"]/n,"avg_duration":g["seconds"]/n,"avg_isk_hr":g["isk_hr_sum"]/n})
    return sorted(out,key=lambda x:(-x["avg_isk_hr"],x["name"]))

def progression_luck_stats(days=30):
    days=30 if days==30 else 7 if days==7 else 30
    now=utcnow();cutoff=now-timedelta(days=days)
    with db() as c:
        rows=c.execute("SELECT anomaly,ended_at,escalation_name,rare_spawn_type,rare_spawn_value FROM runs WHERE status='complete' AND ended_at IS NOT NULL ORDER BY ended_at DESC").fetchall()
    active=[]
    for r in rows:
        try:end=parse_iso(r["ended_at"])
        except Exception:continue
        if cutoff<=end<=now:active.append(r)
    sites=len(active);escalations=[r for r in active if (r["escalation_name"] or "").strip()]
    esc_counts={}
    for r in escalations:
        n=(r["escalation_name"] or "Unknown").strip();esc_counts[n]=esc_counts.get(n,0)+1
    most_common=max(esc_counts.items(),key=lambda x:(x[1],x[0]))[0] if esc_counts else None
    rare=[r for r in active if (r["rare_spawn_type"] or "").strip()];breakdown={"Commander":0,"Dreadnought":0,"Titan":0,"Other":0}
    for r in rare:
        kind=(r["rare_spawn_type"] or "Other").strip();breakdown[kind if kind in breakdown else "Other"]+=1
    return {"days":days,"sites":sites,"escalations":{"total":len(escalations),"rate":(len(escalations)/sites*100 if sites else 0),"most_common":most_common},"rare_spawns":{"total":len(rare),"rate":(len(rare)/sites*100 if sites else 0),"breakdown":breakdown,"loot_value":sum(money(r["rare_spawn_value"]) for r in rare)}}

@app.get("/progression",response_class=HTMLResponse)
async def progression_page(request:Request,days:int=30):
    days=30 if days==30 else 7 if days==7 else 30
    with db() as c:chars=c.execute("SELECT character_id,name,COALESCE(character_role,'alt') AS character_role FROM characters WHERE COALESCE(connected,1)=1 ORDER BY connected_at").fetchall()
    out=[]
    for x in chars:
        try:
            p=await progression(x["character_id"],50)
        except Exception:
            p={"total_sp":0,"queue":[],"changes":[],"captured_at":None,"has_snapshot":False}
        out.append({"id":x["character_id"],"name":x["name"],"role":x["character_role"] or "alt","portrait":f"https://images.evetech.net/characters/{x['character_id']}/portrait?size=128",**p})
    boot={"page":"progression","characters":out,"luck_stats":progression_luck_stats(days),"site_performance":progression_site_performance(days),"version":APP_VERSION}
    return templates.TemplateResponse(request=request,name="react.html",context={"boot":boot,"title":"Progression"})

@app.get("/history",response_class=HTMLResponse)
async def history(request:Request,days:int=7,run_page:int=1,session_page:int=1,analytics:int=0):
    days=30 if days==30 else 7; start_day=utcnow().date()-timedelta(days=days-1)
    run_page=max(1,int(run_page or 1));session_page=max(1,int(session_page or 1));runs_per_page=30;sessions_per_page=20
    with db() as c:
        rs=c.execute("SELECT * FROM runs WHERE status='complete' ORDER BY ended_at DESC").fetchall()
        ss=c.execute("SELECT * FROM sessions WHERE status='complete' ORDER BY ended_at DESC").fetchall()
        ess=c.execute("""SELECT e.*,COALESCE(ch.name,CAST(e.character_id AS TEXT)) AS character_name FROM ess_events e LEFT JOIN characters ch ON ch.character_id=e.character_id ORDER BY e.date DESC""").fetchall()
        alls=c.execute("SELECT id FROM sessions WHERE status='complete' ORDER BY id DESC LIMIT 500").fetchall()
    buckets={(start_day+timedelta(days=i)).isoformat():{"date":(start_day+timedelta(days=i)).isoformat(),"bounty":0,"ess":0,"loot":0,"salvage":0,"bonus":0,"seconds":0,"sites":0,"isk_hr":0} for i in range(days)}
    for r in rs:
        if not r["ended_at"]:continue
        k=parse_iso(r["ended_at"]).date().isoformat()
        if k in buckets:
            buckets[k]["bounty"]+=money(r["combined_bounty"]);buckets[k]["bonus"]+=(money(r["escalation_sale_value"]) if r["escalation_status"] in ("Sold", "Ran Myself") else 0)+money(r["rare_spawn_value"]);buckets[k]["seconds"]+=effective_run_seconds(r);buckets[k]["sites"]+=1
    sess=[]
    for srow in ss:
        rr=[r for r in rs if r["session_id"]==srow["id"]];d=dict(srow);d["site_count"]=len(rr);d["bounty"]=sum(money(r["combined_bounty"]) for r in rr);d["bonus"]=sum((money(r["escalation_sale_value"]) if r["escalation_status"] in ("Sold", "Ran Myself") else 0)+money(r["rare_spawn_value"]) for r in rr);d["total"]=d["bounty"]+money(srow["loot_value"])+money(srow["salvage_value"])+d["bonus"];d["systems"]=", ".join(sorted(set(r["system_name"] or "Unknown" for r in rr))) if rr else "—";span=max(0,int((parse_iso(srow["ended_at"])-parse_iso(srow["started_at"])).total_seconds()));d["duration_label"]=f"{span//3600}h {(span%3600)//60}m" if span>=3600 else f"{span//60}m";sess.append(d)
        k=parse_iso(srow["ended_at"]).date().isoformat()
        if k in buckets:buckets[k]["loot"]+=money(srow["loot_value"]);buckets[k]["salvage"]+=money(srow["salvage_value"])
    for e in ess:
        k=parse_iso(e["date"]).date().isoformat()
        if k in buckets:buckets[k]["ess"]+=money(e["amount"])
    for b in buckets.values():
        total_income=sum(money(b[k]) for k in ["bounty","ess","loot","salvage","bonus"]);b["isk_hr"]=total_income/b["seconds"]*3600 if b["seconds"] else 0
    run_total=len(rs);session_total=len(sess);run_pages=max(1,(run_total+runs_per_page-1)//runs_per_page);session_pages=max(1,(session_total+sessions_per_page-1)//sessions_per_page)
    run_page=min(run_page,run_pages);session_page=min(session_page,session_pages)
    run_slice=rs[(run_page-1)*runs_per_page:run_page*runs_per_page];session_slice=sess[(session_page-1)*sessions_per_page:session_page*sessions_per_page]
    avg_duration=(sum(effective_run_seconds(r) for r in rs)/run_total if run_total else 0);total_bonus=sum((money(r["escalation_sale_value"]) if r["escalation_status"] in ("Sold","Ran Myself") else 0)+money(r["rare_spawn_value"]) for r in rs)
    recent_escalations=[enrich(r) for r in rs if (r["escalation_name"] or "").strip()][:8]
    analytics_cutoff=utcnow()-timedelta(days=days+2)
    analytics_runs=[enrich(r) for r in rs if r["ended_at"] and parse_iso(r["ended_at"])>=analytics_cutoff]
    analytics_sessions=[d for d in sess if d.get("ended_at") and parse_iso(d["ended_at"])>=analytics_cutoff]
    analytics_ess=[dict(e) for e in ess if e["date"] and parse_iso(e["date"])>=analytics_cutoff]
    history_data={"days":days,"runs":analytics_runs if analytics else [enrich(r) for r in run_slice],"sessions":analytics_sessions if analytics else session_slice,"ess":analytics_ess if analytics else [dict(e) for e in ess[:100]],"analytics_runs":analytics_runs,"analytics_sessions":analytics_sessions,"analytics_ess":analytics_ess,"all_sessions":[dict(x) for x in alls],"chart_data":list(buckets.values()),"recent_escalations":recent_escalations,"run_page":run_page,"run_pages":run_pages,"run_total":run_total,"runs_per_page":runs_per_page,"session_page":session_page,"session_pages":session_pages,"session_total":session_total,"sessions_per_page":sessions_per_page,"summary":{"avg_duration_seconds":avg_duration,"total_bonus":total_bonus}}
    boot={"page":"history","history":history_data,"version":APP_VERSION}
    return templates.TemplateResponse(request=request,name="react.html",context={"boot":boot,"title":"History"})

@app.post("/ess/{eid}/assign")
async def assign_ess(eid:int,session_id:str=Form("")):
    with db() as c:
        if session_id:c.execute("UPDATE ess_events SET session_id=?,match_status='manual' WHERE entry_id=?",(int(session_id),eid))
        else:c.execute("UPDATE ess_events SET session_id=NULL,match_status='unassigned' WHERE entry_id=?",(eid,))
    return RedirectResponse("/history",303)

if __name__=="__main__":
    import uvicorn; uvicorn.run("app:app",host=HOST,port=PORT,reload=False)
