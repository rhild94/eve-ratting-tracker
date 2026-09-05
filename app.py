
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
from fastapi.responses import HTMLResponse,RedirectResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR=Path(__file__).resolve().parent
APP_VERSION="8.3.0"
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
def init_db()
@app.middleware("http")
async def access_gate(request:Request,call_next):
    if not APP_ACCESS_KEY or request.url.path in {"/access","/health"} or request.url.path.startswith("/static/"):
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
            c.execute("INSERT INTO wallet_entries(entry_id,character_id,date,amount,balance,ref_type,description,raw_json) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(entry_id) DO NOTHING",(j.get("id"),cid,j.get("date"),money(j.get("amount")),j.get("balance"),j.get("ref_type"),j.get("description"),json.dumps(j))) if USE_POSTGRES else c.execute("INSERT OR IGNORE INTO wallet_entries(entry_id,character_id,date,amount,balance,ref_type,description,raw_json) VALUES(?,?,?,?,?,?,?,?)",(j.get("id"),cid,j.get("date"),money(j.get("amount")),j.get("balance"),j.get("ref_type"),j.get("description"),json.dumps(j)))
            if "ess" in (j.get("ref_type") or "").lower() and money(j.get("amount"))>0:
                c.execute("INSERT INTO ess_events(entry_id,character_id,date,amount) VALUES(?,?,?,?) ON CONFLICT(entry_id) DO NOTHING",(j.get("id"),cid,j.get("date"),money(j.get("amount")))) if USE_POSTGRES else c.execute("INSERT OR IGNORE INTO ess_events(entry_id,character_id,date,amount) VALUES(?,?,?,?)",(j.get("id"),cid,j.get("date"),money(j.get("amount"))))
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
    esi_state={"pending_runs":pending_esi,"last_sync":last_sync,"interval_minutes":AUTO_SYNC_INTERVAL_SECONDS//60,"configured":bool(CLIENT_ID),"connected_characters":len(characters)}
    if sync_state:esi_state.update({k:sync_state[k] for k in ["last_attempt","last_success","last_error","next_check"]})
    return {"characters":characters,"active":enrich(ar) if ar else None,"recent":[enrich(r) for r in recent],"stats":stats,"session":si,"anomalies":ANOMALIES,"esi":esi_state}

@app.get("/",response_class=HTMLResponse)
async def home(request:Request):
    payload=await dashboard_payload()
    return templates.TemplateResponse(request=request,name="index.html",context={"data":payload,"config_ok":bool(CLIENT_ID),"version":APP_VERSION})

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

@app.get("/api/dashboard")
async def api_dashboard(): return JSONResponse(await dashboard_payload())

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
    with db() as c:c.execute("""INSERT INTO characters(character_id,name,access_token,refresh_token,expires_at,connected_at) VALUES(?,?,?,?,?,?) ON CONFLICT(character_id) DO UPDATE SET name=excluded.name,access_token=excluded.access_token,refresh_token=excluded.refresh_token,expires_at=excluded.expires_at""",(cid,pub.get("name",str(cid)),t["access_token"],t["refresh_token"],int(time.time())+int(t.get("expires_in",1200)),iso()))
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
        rid=(c.execute("INSERT INTO runs(anomaly,variant,started_at,participants_json,notes,status,system_name,ships_json,session_id,esi_synced_at) VALUES(?,?,?,?,?,'active',?,?,?,NULL) RETURNING id",(anomaly,variant or None,st,json.dumps(pids),notes,system,json.dumps(ships),sid)).fetchone()["id"] if USE_POSTGRES else c.execute("INSERT INTO runs(anomaly,variant,started_at,participants_json,notes,status,system_name,ships_json,session_id,esi_synced_at) VALUES(?,?,?,?,?,'active',?,?,?,NULL)",(anomaly,variant or None,st,json.dumps(pids),notes,system,json.dumps(ships),sid)).lastrowid)
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
        last=c.execute("SELECT ended_at FROM runs WHERE session_id=? AND status='complete' ORDER BY ended_at DESC LIMIT 1",(s["id"],)).fetchone()
        end=last["ended_at"] if last else iso()
        c.execute("UPDATE sessions SET ended_at=?,status='complete',loot_value=?,salvage_value=?,notes=? WHERE id=?",(end,max(0,money(b.get("loot_value"))),max(0,money(b.get("salvage_value"))),(b.get("notes") or "").strip(),s["id"]))
        for e in c.execute("SELECT * FROM ess_events WHERE session_id IS NULL"):
            try:auto_match_ess(c,e["entry_id"],parse_iso(e["date"]))
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

@app.get("/progression",response_class=HTMLResponse)
async def progression_page(request:Request):
    with db() as c:chars=c.execute("SELECT character_id,name FROM characters ORDER BY connected_at").fetchall()
    out=[]
    for x in chars:
        try:
            p=await progression(x["character_id"],50)
        except Exception:
            p={"total_sp":0,"queue":[],"changes":[],"captured_at":None,"has_snapshot":False}
        out.append({"id":x["character_id"],"name":x["name"],"portrait":f"https://images.evetech.net/characters/{x['character_id']}/portrait?size=128",**p})
    return templates.TemplateResponse(request=request,name="progression.html",context={"characters":out})

@app.get("/history",response_class=HTMLResponse)
async def history(request:Request,days:int=7):
    days=30 if days==30 else 7; start=utcnow().date()-timedelta(days=days-1)
    with db() as c:
        rs=c.execute("SELECT * FROM runs WHERE status='complete' ORDER BY ended_at DESC").fetchall()
        ss=c.execute("SELECT * FROM sessions WHERE status='complete' ORDER BY ended_at DESC").fetchall()
        ess=c.execute("""SELECT e.*,COALESCE(ch.name,CAST(e.character_id AS TEXT)) AS character_name FROM ess_events e LEFT JOIN characters ch ON ch.character_id=e.character_id ORDER BY e.date DESC""").fetchall()
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
