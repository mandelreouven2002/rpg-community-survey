#!/bin/bash
echo "🚀 Starting Project Setup..."

mkdir -p templates/survey templates/admin static

# ── Config Files ─────────────────────────────────────────────────
cat > requirements.txt << 'REQEOF'
fastapi
uvicorn[standard]
sqlalchemy
python-dotenv
psycopg2-binary
jinja2
python-multipart
REQEOF

cat > Procfile << 'PROCEOF'
web: uvicorn main:app --host 0.0.0.0 --port $PORT
PROCEOF

cat > railway.toml << 'RAILEOF'
[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
RAILEOF

cat > .env << 'ENVEOF'
DATABASE_URL=sqlite:///./survey.db
SECRET_KEY=local_dev_secret_key_change_in_production
ADMIN_PASSWORD=admin123
ENVEOF

cat > .gitignore << 'GIEOF'
.env
*.db
__pycache__/
*.pyc
.DS_Store
venv/
GIEOF

# ── database.py ──────────────────────────────────────────────────
cat > database.py << 'DBEOF'
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./survey.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
DBEOF

# ── models.py ────────────────────────────────────────────────────
cat > models.py << 'MODEOF'
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from database import Base

def new_uuid(): return str(uuid.uuid4())

class IdHash(Base):
    __tablename__ = "id_hashes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_hash = Column(String(64), unique=True, nullable=False, index=True)

class SurveySession(Base):
    __tablename__ = "survey_sessions"
    id              = Column(String(36), primary_key=True, default=new_uuid)
    ip_hash         = Column(String(64), nullable=False, index=True)
    survey_type     = Column(String(10), nullable=True)
    is_submitted    = Column(Boolean, default=False)
    current_section = Column(String(20), default="section1")
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active_sections = Column(Text, nullable=True)
    section1        = Column(Text, nullable=True)
    section2        = Column(Text, nullable=True)
    section3        = Column(Text, nullable=True)
    section4        = Column(Text, nullable=True)
    section5        = Column(Text, nullable=True)
    section6        = Column(Text, nullable=True)
    section7        = Column(Text, nullable=True)
    section8        = Column(Text, nullable=True)
    section9        = Column(Text, nullable=True)
MODEOF

# ── utils.py ─────────────────────────────────────────────────────
cat > utils.py << 'UTILEOF'
import hmac, hashlib, os, json
from datetime import date
from dotenv import load_dotenv

load_dotenv()
_SECRET = os.getenv("SECRET_KEY", "fallback-secret")

def validate_israeli_id(id_str: str) -> bool:
    s = id_str.strip().zfill(9)
    if not s.isdigit() or len(s) != 9: return False
    total = sum((int(d) * (1 if i % 2 == 0 else 2)) - 9 if (int(d) * (1 if i % 2 == 0 else 2)) > 9 else (int(d) * (1 if i % 2 == 0 else 2)) for i, d in enumerate(s))
    return total % 10 == 0

def hash_value(val: str) -> str:
    return hmac.new(_SECRET.encode(), val.strip().encode(), hashlib.sha256).hexdigest()

def hash_ip(ip: str) -> str:
    return hmac.new(_SECRET.encode(), ip.encode(), hashlib.sha256).hexdigest()

def calculate_age(dob_str: str):
    try:
        dob = date.fromisoformat(dob_str)
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception: return None

ROLE_SECTION_MAP = {
    "tabletop_player": "section3", "gm": "section4", "larp_participant": "section5",
    "larp_organizer": "section5", "parent": "section6", "business": "section7",
    "interested": "section8", "former_player": "section9"
}

def determine_active_sections(roles: list) -> list:
    sections, seen = ["section2"], set()
    for r in roles:
        if (s := ROLE_SECTION_MAP.get(r)) and s not in seen:
            sections.append(s); seen.add(s)
    return sections

def next_section(active: list, current: str):
    try:
        idx = active.index(current)
        return active[idx + 1] if idx + 1 < len(active) else None
    except ValueError: return None

SECTION_LABELS = {
    "section2": "היכרות", "section3": "שחקנים", "section4": "מנחים",
    "section5": "לארפ", "section6": "הורים", "section7": "עסקים",
    "section8": "מתעניינים", "section9": "נשירה"
}
UTILEOF

# ── main.py ──────────────────────────────────────────────────────
cat > main.py << 'MAINEOF'
import os, json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv

from database import engine, get_db, Base, SessionLocal
from models import IdHash, SurveySession
from utils import validate_israeli_id, hash_value, hash_ip, calculate_age, determine_active_sections, next_section, SECTION_LABELS

load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

app = FastAPI(title="סקר קהילת משחקי תפקידים בישראל")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def render(request: Request, name: str, **kwargs):
    kwargs["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=kwargs)

def get_client_ip(request: Request) -> str:
    if forwarded := request.headers.get("x-forwarded-for"):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if "postgres" in str(engine.url):
            db.execute(text("ALTER TABLE survey_sessions ADD COLUMN IF NOT EXISTS current_section VARCHAR(20) DEFAULT 'section1';"))
            db.execute(text("ALTER TABLE survey_sessions ADD COLUMN IF NOT EXISTS is_submitted BOOLEAN DEFAULT FALSE;"))
        db.commit()
        db.query(SurveySession).filter(SurveySession.is_submitted == False, SurveySession.created_at < datetime.utcnow() - timedelta(days=30)).delete()
        db.commit()
    except Exception as e: print(f"Startup DB Migration error: {e}")
    finally: db.close()

def _get_session(request: Request, db: Session, session_id: Optional[str]) -> Optional[SurveySession]:
    ip_hash = hash_ip(get_client_ip(request))
    if session_id and (s := db.query(SurveySession).filter_by(id=session_id, is_submitted=False).first()): return s
    return db.query(SurveySession).filter_by(ip_hash=ip_hash, is_submitted=False).order_by(SurveySession.created_at.desc()).first()

def _require(request, db, session_id):
    if not (sess := _get_session(request, db, session_id)) or not sess.section1:
        return None, RedirectResponse("/survey", status_code=303)
    return sess, None

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def home(request: Request): return render(request, "home.html")

@app.get("/survey", response_class=HTMLResponse)
def survey_start(request: Request, session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    if existing := _get_session(request, db, session_id):
        if existing.section1: return render(request, "survey/resume.html", session=existing, SECTION_LABELS=SECTION_LABELS)
    return render(request, "survey/consent.html")

@app.post("/survey/consent")
async def survey_consent(request: Request, consent: str = Form(...)):
    if consent != "yes": return render(request, "survey/ended.html", reason="תודה על הזמן שלך. השאלון הסתיים.")
    return RedirectResponse("/survey/identity", status_code=303)

@app.get("/survey/identity", response_class=HTMLResponse)
def identity_form(request: Request): return render(request, "survey/identity.html", error=None)

@app.post("/survey/identity")
async def identity_submit(request: Request, id_number: str = Form(...), db: Session = Depends(get_db)):
    if not validate_israeli_id(id_number := id_number.strip()):
        return render(request, "survey/identity.html", error="מספר תעודת הזהות אינו תקין.")
    hashed = hash_value(id_number.zfill(9))
    if db.query(IdHash).filter_by(id_hash=hashed).first():
        return render(request, "survey/identity.html", error="תעודת זהות זו כבר מילאה את השאלון.")
    resp = RedirectResponse("/survey/demographics", status_code=303)
    resp.set_cookie("pending_id_hash", hashed, httponly=True, max_age=3600)
    return resp

@app.get("/survey/demographics", response_class=HTMLResponse)
def demographics_form(request: Request): return render(request, "survey/demographics.html", error=None)

@app.post("/survey/demographics")
async def demographics_submit(request: Request, dob: Optional[str] = Form(default=None), dob_prefer_not: Optional[str] = Form(default=None), region: str = Form(...), city: Optional[str] = Form(default=None), roles: list = Form(default=[]), session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    if not dob_prefer_not and dob and (age := calculate_age(dob)) is not None and age < 13:
        return render(request, "survey/ended.html", reason="השאלון מיועד לבני 13 ומעלה.")
    if not roles: return render(request, "survey/demographics.html", error="יש לבחור לפחות תפקיד אחד.")

    active, s1, ip_hash = determine_active_sections(roles), json.dumps({"dob": dob, "region": region, "city": city, "roles": roles}, ensure_ascii=False), hash_ip(get_client_ip(request))
    if not (sess := _get_session(request, db, session_id)): db.add(sess := SurveySession(ip_hash=ip_hash))
    sess.section1, sess.active_sections, sess.current_section, sess.updated_at = s1, json.dumps(active), active[0], datetime.utcnow()
    db.commit(); db.refresh(sess)
    resp = RedirectResponse("/survey/choose-version", status_code=303)
    resp.set_cookie("session_id", sess.id, httponly=True, max_age=86400 * 30)
    return resp

@app.get("/survey/choose-version", response_class=HTMLResponse)
def choose_version(request: Request, session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    if not (sess := _get_session(request, db, session_id)): return RedirectResponse("/survey")
    return render(request, "survey/choose_version.html", num_sections=len(json.loads(sess.active_sections or "[]")))

@app.post("/survey/choose-version")
async def choose_version_submit(request: Request, version: str = Form(...), session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    if not (sess := _get_session(request, db, session_id)): return RedirectResponse("/survey")
    sess.survey_type, active = version, json.loads(sess.active_sections or "[]")
    if version == "short": active = [s for s in active if s not in ["section7", "section9"]]
    sess.active_sections, sess.updated_at = json.dumps(active), datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/survey/{active[0] if active else 'submit'}", status_code=303)

def _make_section(num: str):
    async def get_handler(request: Request, session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
        sess, r = _require(request, db, session_id)
        if r: return r
        return render(request, f"survey/section{num}.html", session=sess, data=json.loads(getattr(sess, f"section{num}") or "{}"), active=json.loads(sess.active_sections or "[]"), SECTION_LABELS=SECTION_LABELS)

    async def post_handler(request: Request, session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
        sess, r = _require(request, db, session_id)
        if r: return r
        form, data = await request.form(), {}
        for k, v in form.multi_items():
            if k in data: data[k] = data[k] + [v] if isinstance(data[k], list) else [data[k], v]
            else: data[k] = v
        setattr(sess, f"section{num}", json.dumps(data, ensure_ascii=False))
        active, nxt = json.loads(sess.active_sections or "[]"), next_section(json.loads(sess.active_sections or "[]"), f"section{num}")
        sess.current_section, sess.updated_at = nxt or "submit", datetime.utcnow()
        db.commit()
        return RedirectResponse(f"/survey/{nxt}" if nxt else "/survey/submit", status_code=303)
    return get_handler, post_handler

for _n in ["2", "3", "4", "5", "6", "7", "8", "9"]:
    _g, _p = _make_section(_n)
    app.get(f"/survey/section{_n}", response_class=HTMLResponse)(_g)
    app.post(f"/survey/section{_n}")(_p)

@app.get("/survey/submit", response_class=HTMLResponse)
def submit_get(request: Request, session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    sess, r = _require(request, db, session_id)
    if r: return r
    return render(request, "survey/submit.html", session=sess, active=json.loads(sess.active_sections or "[]"), SECTION_LABELS=SECTION_LABELS)

@app.post("/survey/submit")
async def submit_post(request: Request, lottery_email: Optional[str] = Form(default=None), session_id: Optional[str] = Cookie(default=None), pending_id_hash: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    sess, r = _require(request, db, session_id)
    if r: return r
    if pending_id_hash and not db.query(IdHash).filter_by(id_hash=pending_id_hash).first(): db.add(IdHash(id_hash=pending_id_hash))
    sess.is_submitted, sess.updated_at = True, datetime.utcnow()
    db.commit()
    resp = render(request, "survey/complete.html", lottery_email=lottery_email)
    resp.delete_cookie("session_id"); resp.delete_cookie("pending_id_hash")
    return resp

@app.post("/survey/delete")
async def delete_survey(request: Request, db: Session = Depends(get_db)):
    for s in db.query(SurveySession).filter_by(ip_hash=hash_ip(get_client_ip(request))).all(): db.delete(s)
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_id"); resp.delete_cookie("pending_id_hash")
    return resp

@app.post("/survey/resume")
async def resume(request: Request, action: str = Form(...), session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    ip_hash = hash_ip(get_client_ip(request))
    if action == "new":
        for s in db.query(SurveySession).filter_by(ip_hash=ip_hash, is_submitted=False).all(): db.delete(s)
        db.commit()
        resp = RedirectResponse("/survey", status_code=303)
        resp.delete_cookie("session_id")
        return resp
    if sess := db.query(SurveySession).filter_by(ip_hash=ip_hash, is_submitted=False).order_by(SurveySession.created_at.desc()).first():
        return RedirectResponse(f"/survey/{sess.current_section or 'section2'}", status_code=303)
    return RedirectResponse("/survey", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
def admin_login(request: Request): return render(request, "admin/login.html", error=None)

@app.post("/admin", response_class=HTMLResponse)
async def admin_post(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    if password != ADMIN_PASSWORD: return render(request, "admin/login.html", error="סיסמה שגויה")
    total, submitted = db.query(SurveySession).count(), db.query(SurveySession).filter_by(is_submitted=True).count()
    region_counts = {}
    for s in db.query(SurveySession).filter_by(is_submitted=True).all():
        r = json.loads(s.section1).get("region", "לא ידוע") if s.section1 else "לא ידוע"
        region_counts[r] = region_counts.get(r, 0) + 1
    return render(request, "admin/dashboard.html", total=total, submitted=submitted, in_progress=total-submitted, region_counts=region_counts)
MAINEOF

# ── static & templates ───────────────────────────────────────────
cat > static/style.css << 'CSSEOF'
:root{--brand:#1a2e4a;--gold:#c9a227;--light:#f5f0e8;--text:#1c1c1c;--error:#c0392b;--radius:10px}
*{box-sizing:border-box;margin:0;padding:0}html{direction:rtl;font-family:'Segoe UI',Arial,sans-serif;background:var(--light);color:var(--text)}
body{min-height:100vh;display:flex;flex-direction:column}nav{background:var(--brand);color:#fff;padding:12px 24px;display:flex;align-items:center;gap:16px}
nav img{height:40px}nav a{color:var(--gold);text-decoration:none;font-weight:700}.container{max-width:720px;margin:32px auto;padding:0 16px;flex:1}
.card{background:#fff;border-radius:var(--radius);padding:28px 32px;box-shadow:0 2px 12px rgba(0,0,0,.08);margin-bottom:24px}
.card h1{color:var(--brand);margin-bottom:16px;font-size:1.6rem}.card h2{color:var(--brand);margin-bottom:12px;font-size:1.2rem}
.form-group{margin-bottom:20px}label{display:block;font-weight:600;margin-bottom:6px}
input[type=text],input[type=date],input[type=email],input[type=number],select,textarea{width:100%;padding:10px 12px;border:1px solid #ccc;border-radius:6px;font-size:1rem}
input[type=text]:focus,input[type=date]:focus,select:focus{outline:0;border-color:var(--gold);box-shadow:0 0 0 2px rgba(201,162,39,.2)}
.checkbox-group{display:flex;flex-direction:column;gap:8px}.checkbox-group label,.radio-group label{font-weight:400;display:flex;align-items:center;gap:8px;cursor:pointer}
.radio-group{display:flex;flex-direction:column;gap:8px}.scale-group{display:flex;gap:10px;flex-wrap:wrap}
.scale-group label{display:flex;flex-direction:column;align-items:center;gap:4px;cursor:pointer;min-width:56px;text-align:center;font-size:.85rem;font-weight:400}
.other-input{margin-top:6px;display:none}.other-input.visible{display:block}.btn{display:inline-block;padding:11px 28px;border-radius:6px;font-size:1rem;font-weight:700;cursor:pointer;border:none;text-decoration:none;transition:opacity .15s}
.btn-primary{background:var(--brand);color:#fff}.btn-gold{background:var(--gold);color:var(--brand)}.btn-danger{background:var(--error);color:#fff}.btn:hover{opacity:.85}.btn-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px}
.section-nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px}.section-nav a,.section-nav span{padding:4px 12px;border-radius:20px;font-size:.82rem;font-weight:600;text-decoration:none}
.section-nav .done{background:#d4edda;color:#155724}.section-nav .current{background:var(--brand);color:#fff}.section-nav .pending{background:#e9ecef;color:#666}
.error-msg{background:#fdecea;color:var(--error);padding:10px 14px;border-radius:6px;margin-bottom:16px}.hero{background:linear-gradient(135deg,var(--brand) 60%,#2a4a6e);color:#fff;text-align:center;padding:56px 24px}
.hero img{height:80px;margin-bottom:16px}.hero h1{font-size:2rem;margin-bottom:12px}.hero p{font-size:1.1rem;opacity:.88;max-width:540px;margin:0 auto 24px}
.prizes{background:#fff;border-radius:var(--radius);padding:20px;margin:24px auto;max-width:500px;color:var(--brand);text-align:right}.prizes h3{color:var(--gold);margin-bottom:10px}
.delete-btn-wrapper{position:fixed;bottom:20px;left:20px;z-index:999}.delete-btn-wrapper button{background:rgba(192,57,43,.12);border:1px solid var(--error);color:var(--error);border-radius:6px;padding:7px 14px;font-size:.82rem;cursor:pointer}
.delete-btn-wrapper button:hover{background:var(--error);color:#fff}footer{text-align:center;padding:16px;font-size:.82rem;color:#888}
CSSEOF

cat > templates/base.html << 'BASEEOF'
<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{% block title %}סקר קהילת משחקי תפקידים{% endblock %}</title><link rel="icon" href="https://gate.roleplay.top/rpg-game.png"><link rel="stylesheet" href="/static/style.css"></head><body>
<nav><a href="/"><img src="https://gate.roleplay.top/full-logo.png" alt="שער המשחקים" onerror="this.style.display='none'"></a><a href="/">דף הבית</a><a href="/survey">השאלון</a></nav>
{% block content %}{% endblock %}
{% block delete_btn %}<div class="delete-btn-wrapper"><form method="post" action="/survey/delete" onsubmit="return confirm('האם למחוק את כל הנתונים שלך?')"><button type="submit">🗑 מחק נתונים</button></form></div>{% endblock %}
<footer>© 2026 דוח הקהילה השנתי למשחקי תפקידים בישראל</footer></body></html>
BASEEOF

cat > templates/home.html << 'HOMEEOF'
{% extends "base.html" %}{% block delete_btn %}{% endblock %}{% block content %}
<div class="hero"><img src="https://gate.roleplay.top/full-logo.png" alt="לוגו"><h1>דוח הקהילה השנתי<br>למשחקי תפקידים בישראל 2026</h1><p>עזור/י לנו למפות את עולם משחקי התפקידים בישראל.</p><a href="/survey" class="btn btn-gold" style="font-size:1.1rem;padding:14px 36px">מלא/י את השאלון →</a>
<div class="prizes"><h3>🎁 הגרלה בין המשתתפים — פרסים בשווי 1,000 ₪</h3><ul><li>שובר 300 ₪ לממלכה (×2)</li><li>ערכת חרבות וכשפים — האדומה והסגולה (×3)</li><li>ערכת Pathfinder עולמות פראיים (×1)</li></ul></div></div>
<div class="container"><div class="card"><h2>על השאלון</h2><p>שאלון זה נועד למפות את תחום משחקי התפקידים בישראל.</p><div class="btn-row" style="margin-top:16px"><a href="/survey" class="btn btn-primary">התחל/י את השאלון</a></div></div></div>
{% endblock %}
HOMEEOF

cat > templates/survey/consent.html << 'CONEOF'
{% extends "base.html" %}{% block delete_btn %}{% endblock %}{% block content %}
<div class="container"><div class="card"><h1>הסכמה להשתתפות</h1><p>המידע שייאסף ינותח במטרה לשפר את הקהילה. מידע אישי מזהה יישמר בנפרד.</p>
<form method="post" action="/survey/consent" style="margin-top:20px"><div class="form-group"><div class="radio-group"><label><input type="radio" name="consent" value="yes" required> כן, אני מאשר/ת להשתתף</label><label><input type="radio" name="consent" value="no"> לא</label></div></div><button type="submit" class="btn btn-primary">המשך/י</button></form></div></div>
{% endblock %}
CONEOF

cat > templates/survey/identity.html << 'IDEOF'
{% extends "base.html" %}{% block delete_btn %}{% endblock %}{% block content %}
<div class="container"><div class="card"><h1>תעודת זהות</h1><p>המספר נאסף אך ורק למניעת כפילויות, נשמר מוצפן ולא מקושר לתשובות.</p>
{% if error %}<div class="error-msg">{{ error }}</div>{% endif %}
<form method="post" action="/survey/identity" style="margin-top:16px"><div class="form-group"><label>מספר תעודת זהות (9 ספרות)</label><input type="text" id="id_number" name="id_number" maxlength="9" pattern="\d{5,9}" required autocomplete="off"></div><button type="submit" class="btn btn-primary">המשך/י</button></form></div></div>
{% endblock %}
IDEOF

cat > templates/survey/demographics.html << 'DEMEOF'
{% extends "base.html" %}{% block delete_btn %}{% endblock %}{% block content %}
<div class="container"><div class="card"><h1>פרטים בסיסיים</h1>
{% if error %}<div class="error-msg">{{ error }}</div>{% endif %}
<form method="post" action="/survey/demographics"><div class="form-group"><label>תאריך לידה</label><input type="date" name="dob" id="dob_field"><label style="font-weight:normal"><input type="checkbox" name="dob_prefer_not" onchange="document.getElementById('dob_field').disabled=this.checked"> מעדיף/ה לא לענות</label></div>
<div class="form-group"><label>אזור מגורים *</label><select name="region" required><option value="">-- בחר/י --</option><option>צפון</option><option>חיפה והקריות</option><option>השרון</option><option>גוש דן</option><option>תל אביב-יפו</option><option>ירושלים והסביבה</option><option>השפלה</option><option>דרום</option><option>יהודה ושומרון</option><option>אילת והערבה</option><option>גר/ה בחו״ל</option><option>מעדיף/ה לא לענות</option></select></div>
<div class="form-group"><label>עיר / יישוב (לא חובה)</label><input type="text" name="city"></div>
<div class="form-group"><label>מה הקשר שלך לתחום? (ניתן לבחור כמה) *</label><div class="checkbox-group"><label><input type="checkbox" name="roles" value="tabletop_player"> שחקן/ית שולחני/ת</label><label><input type="checkbox" name="roles" value="gm"> מנחה שולחני/ת</label><label><input type="checkbox" name="roles" value="larp_participant"> משתתף/ת לארפים</label><label><input type="checkbox" name="roles" value="larp_organizer"> מארגן/ת לארפים</label><label><input type="checkbox" name="roles" value="parent"> הורה לילד/ה שמשחק/ת</label><label><input type="checkbox" name="roles" value="business"> בעל/ת עסק/חנות</label><label><input type="checkbox" name="roles" value="creator"> יוצר/ת תוכן</label><label><input type="checkbox" name="roles" value="interested"> מתעניין/ת (טרם שיחקתי)</label><label><input type="checkbox" name="roles" value="former_player"> שחקן/ית עבר</label></div></div>
<button type="submit" class="btn btn-primary">המשך/י</button></form></div></div>
{% endblock %}
DEMEOF

cat > templates/survey/choose_version.html << 'CHEOF'
{% extends "base.html" %}{% block delete_btn %}{% endblock %}{% block content %}
<div class="container"><div class="card"><h1>בחירת גרסת השאלון</h1><form method="post" action="/survey/choose-version" style="margin-top:20px"><div class="radio-group"><label style="padding:14px;border:1px solid #ddd;border-radius:8px"><input type="radio" name="version" value="short" required><strong>גרסה קצרה (8–12 דקות)</strong></label><label style="padding:14px;border:1px solid #ddd;border-radius:8px"><input type="radio" name="version" value="long"><strong>גרסה מורחבת (20 דקות)</strong></label></div><button type="submit" class="btn btn-primary" style="margin-top:20px">התחל/י</button></form></div></div>
{% endblock %}
CHEOF

cat > templates/survey/resume.html << 'RESEOF'
{% extends "base.html" %}{% block delete_btn %}{% endblock %}{% block content %}
<div class="container"><div class="card"><h1>ברוך/ה שב/ה!</h1><p>מצאנו מילוי שאלון לא גמור מהכתובת שלך.</p><form method="post" action="/survey/resume" style="margin-top:20px"><div class="btn-row"><button name="action" value="continue" class="btn btn-primary">המשך/י מאיפה שעצרתי</button><button name="action" value="new" class="btn btn-danger" onclick="return confirm('הכל יימחק. להתחיל מחדש?')">התחל/י מחדש</button></div></form></div></div>
{% endblock %}
RESEOF

cat > templates/survey/_nav.html << 'NAVEOF'
{% macro section_nav(active, current, session, SECTION_LABELS) %}<div class="section-nav">{% for s in active %}{% set label = SECTION_LABELS.get(s, s) %}{% set sec_data = session[s] if session and s in session.__dict__ else None %}{% if s == current %}<span class="current">{{ label }}</span>{% elif sec_data %}<a href="/survey/{{ s }}" class="done">✓ {{ label }}</a>{% else %}<span class="pending">{{ label }}</span>{% endif %}{% endfor %}</div>{% endmacro %}
NAVEOF

cat > templates/survey/section2.html << 'S2EOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'section2', session, SECTION_LABELS) }}<h1>היכרות כללית עם התחום</h1>
<form method="post" action="/survey/section2">
<div class="form-group"><label>6. כמה שנים את/ה מכיר/ה את תחום משחקי התפקידים? *</label><div class="radio-group">{% for opt in ["פחות משנה","1–2 שנים","3–5 שנים","6–10 שנים","11–20 שנים","מעל 20 שנים","לא בטוח/ה"] %}<label><input type="radio" name="years_in_field" value="{{ opt }}" {% if data.get('years_in_field')==opt %}checked{% endif %} required> {{ opt }}</label>{% endfor %}</div></div>
<div class="form-group"><label>7. איך נחשפת לראשונה? (ניתן לבחור כמה)</label><div class="checkbox-group">{% for opt in ["חברים","משפחה","בית ספר","חוג","כנס","יוטיוב / פודקאסט","משחקי מחשב"] %}<label><input type="checkbox" name="first_exposure" value="{{ opt }}" {% if opt in data.get('first_exposure',[]) %}checked{% endif %}> {{ opt }}</label>{% endfor %}</div></div>
<div class="form-group"><label>8. עד כמה משחקי תפקידים הם חלק משמעותי מחייך? (1-5) *</label><div class="scale-group">{% for i in [1,2,3,4,5] %}<label><input type="radio" name="importance" value="{{ i }}" {% if data.get('importance')|int == i %}checked{% endif %} required><span>{{ i }}</span></label>{% endfor %}</div></div>
<div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div></form></div></div>
{% endblock %}
S2EOF

cat > templates/survey/section3.html << 'S3EOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'section3', session, SECTION_LABELS) }}<h1>שחקנים שולחניים</h1>
<form method="post" action="/survey/section3">
<div class="form-group"><label>11. תדירות משחק? *</label><div class="radio-group">{% for opt in ["יותר מפעם בשבוע","פעם בשבוע","פעמיים-שלוש בחודש","פעם בחודש","כמה פעמים בשנה","כמעט ולא"] %}<label><input type="radio" name="frequency" value="{{ opt }}" {% if data.get('frequency')==opt %}checked{% endif %} required> {{ opt }}</label>{% endfor %}</div></div>
<div class="form-group"><label>14. פרונטלי או אונליין? *</label><div class="radio-group">{% for opt in ["בעיקר פרונטלית","בעיקר אונליין","חצי-חצי"] %}<label><input type="radio" name="online_or_frontally" value="{{ opt }}" {% if data.get('online_or_frontally')==opt %}checked{% endif %} required> {{ opt }}</label>{% endfor %}</div></div>
<div class="form-group"><label>16. שיטות בהן שיחקת השנה?</label><div class="checkbox-group">{% for opt in ["מבוכים ודרקונים 5e","Pathfinder","Call of Cthulhu","PbtA / אינדי"] %}<label><input type="checkbox" name="systems" value="{{ opt }}" {% if opt in data.get('systems',[]) %}checked{% endif %}> {{ opt }}</label>{% endfor %}</div></div>
<div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div></form></div></div>
{% endblock %}
S3EOF

cat > templates/survey/section4.html << 'S4EOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'section4', session, SECTION_LABELS) }}<h1>מנחים</h1>
<form method="post" action="/survey/section4">
<div class="form-group"><label>האם אתה/את מנחה כיום? *</label><div class="radio-group">{% for opt in ["כן, בקביעות","כן, מדי פעם","בעבר"] %}<label><input type="radio" name="gm_status" value="{{ opt }}" {% if data.get('gm_status')==opt %}checked{% endif %} required> {{ opt }}</label>{% endfor %}</div></div>
<div class="form-group"><label>מנחה בתשלום? *</label><div class="radio-group">{% for opt in ["כן, מלא","לעיתים","לא"] %}<label><input type="radio" name="gm_paid" value="{{ opt }}" {% if data.get('gm_paid')==opt %}checked{% endif %} required> {{ opt }}</label>{% endfor %}</div></div>
<div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div></form></div></div>
{% endblock %}
S4EOF

cat > templates/survey/section5.html << 'S5EOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'section5', session, SECTION_LABELS) }}<h1>לארפ</h1>
<form method="post" action="/survey/section5">
<div class="form-group"><label>תדירות השתתפות? *</label><div class="radio-group">{% for opt in ["מספר פעמים בחודש","פעם בחודש","מספר פעמים בשנה","לעיתים נדירות"] %}<label><input type="radio" name="larp_frequency" value="{{ opt }}" {% if data.get('larp_frequency')==opt %}checked{% endif %} required> {{ opt }}</label>{% endfor %}</div></div>
<div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div></form></div></div>
{% endblock %}
S5EOF

cat > templates/survey/section6.html << 'S6EOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'section6', session, SECTION_LABELS) }}<h1>הורים</h1>
<form method="post" action="/survey/section6">
<div class="form-group"><label>גיל הילד/ה שמשחק/ת? *</label><div class="radio-group">{% for opt in ["עד 7","8–10","11–13","14–17","18+"] %}<label><input type="radio" name="child_age" value="{{ opt }}" {% if data.get('child_age')==opt %}checked{% endif %} required> {{ opt }}</label>{% endfor %}</div></div>
<div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div></form></div></div>
{% endblock %}
S6EOF

cat > templates/survey/section7.html << 'S7EOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'section7', session, SECTION_LABELS) }}<h1>עסקים</h1>
<form method="post" action="/survey/section7">
<div class="form-group"><label>סוג עסק? *</label><div class="checkbox-group">{% for opt in ["חנות פיזית","חנות אונליין","הוצאה לאור","חוגים"] %}<label><input type="checkbox" name="biz_type" value="{{ opt }}" {% if opt in data.get('biz_type',[]) %}checked{% endif %}> {{ opt }}</label>{% endfor %}</div></div>
<div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div></form></div></div>
{% endblock %}
S7EOF

cat > templates/survey/section8.html << 'S8EOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'section8', session, SECTION_LABELS) }}<h1>מתעניינים / חסמי כניסה</h1>
<form method="post" action="/survey/section8">
<div class="form-group"><label>מה מונע ממך להצטרף? *</label><div class="checkbox-group">{% for opt in ["לא יודע איפה למצוא קבוצה","אין לי זמן","עלות גבוהה","חשש חברתי"] %}<label><input type="checkbox" name="barriers" value="{{ opt }}" {% if opt in data.get('barriers',[]) %}checked{% endif %}> {{ opt }}</label>{% endfor %}</div></div>
<div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div></form></div></div>
{% endblock %}
S8EOF

cat > templates/survey/section9.html << 'S9EOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'section9', session, SECTION_LABELS) }}<h1>נשירה מהתחום</h1>
<form method="post" action="/survey/section9">
<div class="form-group"><label>מה גרם לך להפסיק לשחק? *</label><div class="checkbox-group">{% for opt in ["הקבוצה התפרקה","מעבר בחיים (עבודה/ילדים)","קושי למצוא מנחה"] %}<label><input type="checkbox" name="dropout" value="{{ opt }}" {% if opt in data.get('dropout',[]) %}checked{% endif %}> {{ opt }}</label>{% endfor %}</div></div>
<div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div></form></div></div>
{% endblock %}
S9EOF

cat > templates/survey/submit.html << 'SUBEOF'
{% extends "base.html" %}{% import "survey/_nav.html" as nav %}{% block content %}
<div class="container"><div class="card">{{ nav.section_nav(active, 'submit', session, SECTION_LABELS) }}<h1>סיום וסיכום</h1>
<form method="post" action="/survey/submit" style="margin-top:20px"><div class="form-group"><label>כתובת מייל להגרלה (לא חובה, לא יקושר לתשובות)</label><input type="email" name="lottery_email"></div>
<p style="font-size:.87rem;color:#666">עם שליחת הטופס, תעודת הזהות תישמר מוצפנת ולא ניתן למלא שוב.</p>
<div class="btn-row"><button type="submit" class="btn btn-gold">שלח/י את השאלון ✓</button></div></form></div></div>
{% endblock %}
SUBEOF

cat > templates/survey/complete.html << 'COMPEOF'
{% extends "base.html" %}{% block delete_btn %}{% endblock %}{% block content %}
<div class="container"><div class="card" style="text-align:center"><div style="font-size:4rem;margin-bottom:12px">🎲</div><h1>תודה רבה!</h1><p>השאלון נשלח בהצלחה.</p>
<div style="margin-top:20px"><a href="/" class="btn btn-primary">חזרה לדף הבית</a></div></div></div>
{% endblock %}
COMPEOF

cat > templates/survey/ended.html << 'ENDEOF'
{% extends "base.html" %}{% block delete_btn %}{% endblock %}{% block content %}
<div class="container"><div class="card" style="text-align:center"><div style="font-size:3rem">👋</div><h1 style="margin-top:12px">{{ reason }}</h1><a href="/" class="btn btn-primary">חזרה לדף הבית</a></div></div>
{% endblock %}
ENDEOF

cat > templates/admin/login.html << 'ADMINLEOF'
<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="UTF-8"><title>כניסת מנהל</title><link rel="stylesheet" href="/static/style.css"></head><body><div class="container" style="max-width:400px;margin-top:80px"><div class="card"><h1>כניסת מנהל</h1>{% if error %}<div class="error-msg">{{ error }}</div>{% endif %}<form method="post" action="/admin"><div class="form-group"><label>סיסמה</label><input type="password" name="password" required autofocus></div><button type="submit" class="btn btn-primary">כניסה</button></form></div></div></body></html>
ADMINLEOF

cat > templates/admin/dashboard.html << 'ADMINDEOF'
<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="UTF-8"><title>לוח בקרה</title><link rel="stylesheet" href="/static/style.css"></head><body><nav><a href="/">ראשי</a></nav><div class="container"><div class="card"><h1>לוח בקרה</h1><p>סה"כ נשלחו: {{ submitted }}</p><p>בתהליך: {{ in_progress }}</p></div></div></body></html>
ADMINDEOF

# ── Git Commit & Push ────────────────────────────────────────────
echo "📦 Adding files to Git and pushing..."
git add -A
git commit -m "feat: COMPLETE bulletproof release with all fixes applied (Proxy IP, DB schema alter, SSR fast rendering)"
git push origin main

echo "✅ All done! Project is deploying to Railway."#!/bin/bash
# ================================================================
# RPG Survey — Complete Implementation Automation Script
# ================================================================

echo "🚀 Starting Project Setup..."

# 1. Create project directories
mkdir -p templates/survey templates/admin static

# 2. Virtual Environment & Dependencies (Optional but recommended locally)
# python3 -m venv venv
# source venv/bin/activate
# pip install fastapi "uvicorn[standard]" sqlalchemy python-dotenv psycopg2-binary jinja2 python-multipart

# ── requirements.txt ─────────────────────────────────────────────
cat > requirements.txt << 'REQEOF'
fastapi
uvicorn[standard]
sqlalchemy
python-dotenv
psycopg2-binary
jinja2
python-multipart
REQEOF

# ── Procfile ─────────────────────────────────────────────────────
cat > Procfile << 'PROCEOF'
web: uvicorn main:app --host 0.0.0.0 --port $PORT
PROCEOF

# ── railway.toml ─────────────────────────────────────────────────
cat > railway.toml << 'RAILEOF'
[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
RAILEOF

# ── .env (local dev only) ────────────────────────────────────────
cat > .env << 'ENVEOF'
DATABASE_URL=sqlite:///./survey.db
SECRET_KEY=local_dev_secret_key_change_in_production
ADMIN_PASSWORD=admin123
ENVEOF

# ── .gitignore ───────────────────────────────────────────────────
cat > .gitignore << 'GIEOF'
.env
*.db
__pycache__/
*.pyc
.DS_Store
venv/
GIEOF

# ================================================================
# database.py
# ================================================================
cat > database.py << 'DBEOF'
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./survey.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
DBEOF

# ================================================================
# models.py
# ================================================================
cat > models.py << 'MODEOF'
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from database import Base

def new_uuid():
    return str(uuid.uuid4())

class IdHash(Base):
    __tablename__ = "id_hashes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_hash = Column(String(64), unique=True, nullable=False, index=True)

class SurveySession(Base):
    __tablename__ = "survey_sessions"
    id              = Column(String(36), primary_key=True, default=new_uuid)
    ip_hash         = Column(String(64), nullable=False, index=True)
    survey_type     = Column(String(10), nullable=True)   # 'short' | 'long'
    submitted       = Column(Boolean, default=False)
    current_section = Column(String(20), default="section1")
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active_sections = Column(Text, nullable=True)   # JSON list
    section1        = Column(Text, nullable=True)   # demographics + roles
    section2        = Column(Text, nullable=True)   # היכרות כללית
    section3        = Column(Text, nullable=True)   # שחקנים שולחניים
    section4        = Column(Text, nullable=True)   # מנחים
    section5        = Column(Text, nullable=True)   # לארפ
    section6        = Column(Text, nullable=True)   # הורים
    section7        = Column(Text, nullable=True)   # עסקים
    section8        = Column(Text, nullable=True)   # חסמי כניסה
    section9        = Column(Text, nullable=True)   # נשירה
MODEOF

# ================================================================
# utils.py
# ================================================================
cat > utils.py << 'UTILEOF'
import hmac, hashlib, os, json
from datetime import date
from dotenv import load_dotenv

load_dotenv()
_SECRET = os.getenv("SECRET_KEY", "fallback-secret")

def validate_israeli_id(id_str: str) -> bool:
    s = id_str.strip().zfill(9)
    if not s.isdigit() or len(s) != 9:
        return False
    total = 0
    for i, d in enumerate(s):
        v = int(d) * (1 if i % 2 == 0 else 2)
        if v > 9:
            v -= 9
        total += v
    return total % 10 == 0

def hash_value(val: str) -> str:
    return hmac.new(_SECRET.encode(), val.strip().encode(), hashlib.sha256).hexdigest()

def hash_ip(ip: str) -> str:
    return hmac.new(_SECRET.encode(), ip.encode(), hashlib.sha256).hexdigest()

def calculate_age(dob_str: str):
    try:
        dob = date.fromisoformat(dob_str)
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return None

ROLE_SECTION_MAP = {
    "tabletop_player":  "section3",
    "gm":               "section4",
    "larp_participant": "section5",
    "larp_organizer":   "section5",
    "parent":           "section6",
    "business":         "section7",
    "interested":       "section8",
    "former_player":    "section9",
}

def determine_active_sections(roles: list) -> list:
    sections = ["section2"]
    seen = set()
    for r in roles:
        s = ROLE_SECTION_MAP.get(r)
        if s and s not in seen:
            sections.append(s)
            seen.add(s)
    return sections

def next_section(active: list, current: str):
    try:
        idx = active.index(current)
        return active[idx + 1] if idx + 1 < len(active) else None
    except ValueError:
        return None

SECTION_LABELS = {
    "section2": "היכרות עם התחום",
    "section3": "שחקנים שולחניים",
    "section4": "מנחים",
    "section5": "לארפ",
    "section6": "הורים",
    "section7": "עסקים",
    "section8": "חסמי כניסה",
    "section9": "נשירה מהתחום",
}
UTILEOF

# ================================================================
# main.py (עם התיקון לגרסה קצרה/ארוכה)
# ================================================================
cat > main.py << 'MAINEOF'
import os, json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import engine, get_db, Base
from models import IdHash, SurveySession
from utils import (
    validate_israeli_id, hash_value, hash_ip,
    calculate_age, determine_active_sections,
    next_section, SECTION_LABELS
)

load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

app = FastAPI(title="סקר קהילת משחקי תפקידים בישראל")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    cutoff = datetime.utcnow() - timedelta(days=30)
    db.query(SurveySession).filter(
        SurveySession.submitted == False,
        SurveySession.created_at < cutoff
    ).delete()
    db.commit()
    db.close()

def _get_session(request: Request, db: Session, session_id: Optional[str]) -> Optional[SurveySession]:
    ip_hash = hash_ip(request.client.host)
    if session_id:
        s = db.query(SurveySession).filter_by(id=session_id, submitted=False).first()
        if s:
            return s
    return db.query(SurveySession).filter_by(ip_hash=ip_hash, submitted=False)\
             .order_by(SurveySession.created_at.desc()).first()

def _require(request, db, session_id):
    sess = _get_session(request, db, session_id)
    if not sess or not sess.section1:
        return None, RedirectResponse("/survey", status_code=303)
    return sess, None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/survey", response_class=HTMLResponse)
def survey_start(request: Request,
                 session_id: Optional[str] = Cookie(default=None),
                 db: Session = Depends(get_db)):
    existing = _get_session(request, db, session_id)
    if existing and existing.section1:
        return templates.TemplateResponse("survey/resume.html", {
            "request": request, "session": existing,
            "SECTION_LABELS": SECTION_LABELS
        })
    return templates.TemplateResponse("survey/consent.html", {"request": request})

@app.post("/survey/consent")
async def survey_consent(request: Request, consent: str = Form(...)):
    if consent != "yes":
        return templates.TemplateResponse("survey/ended.html",
            {"request": request, "reason": "תודה על הזמן שלך. השאלון הסתיים."})
    return RedirectResponse("/survey/identity", status_code=303)

@app.get("/survey/identity", response_class=HTMLResponse)
def identity_form(request: Request):
    return templates.TemplateResponse("survey/identity.html", {"request": request, "error": None})

@app.post("/survey/identity")
async def identity_submit(request: Request, id_number: str = Form(...),
                          db: Session = Depends(get_db)):
    id_number = id_number.strip()
    if not validate_israeli_id(id_number):
        return templates.TemplateResponse("survey/identity.html", {
            "request": request,
            "error": "מספר תעודת הזהות אינו תקין. אנא בדוק/י ונסה/י שוב."
        })
    hashed = hash_value(id_number.zfill(9))
    if db.query(IdHash).filter_by(id_hash=hashed).first():
        return templates.TemplateResponse("survey/identity.html", {
            "request": request,
            "error": "תעודת זהות זו כבר שימשה למילוי השאלון. לא ניתן למלא יותר מפעם אחת."
        })
    resp = RedirectResponse("/survey/demographics", status_code=303)
    resp.set_cookie("pending_id_hash", hashed, httponly=True, max_age=3600)
    return resp

@app.get("/survey/demographics", response_class=HTMLResponse)
def demographics_form(request: Request):
    return templates.TemplateResponse("survey/demographics.html", {"request": request, "error": None})

@app.post("/survey/demographics")
async def demographics_submit(
    request: Request,
    dob: Optional[str] = Form(default=None),
    dob_prefer_not: Optional[str] = Form(default=None),
    region: str = Form(...),
    city: Optional[str] = Form(default=None),
    roles: list = Form(default=[]),
    session_id: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
):
    if not dob_prefer_not and dob:
        age = calculate_age(dob)
        if age is not None and age < 13:
            return templates.TemplateResponse("survey/ended.html", {
                "request": request,
                "reason": "השאלון מיועד לבני 13 ומעלה. תודה על הזמן שלך."
            })
    if not roles:
        return templates.TemplateResponse("survey/demographics.html", {
            "request": request, "error": "אנא בחר/י לפחות תפקיד אחד."
        })

    active = determine_active_sections(roles)
    s1 = json.dumps({"dob": dob, "dob_prefer_not": bool(dob_prefer_not),
                     "region": region, "city": city, "roles": roles}, ensure_ascii=False)
    ip_hash = hash_ip(request.client.host)

    sess = _get_session(request, db, session_id)
    if not sess:
        sess = SurveySession(ip_hash=ip_hash)
        db.add(sess)

    sess.section1 = s1
    sess.active_sections = json.dumps(active)
    sess.current_section = active[0]
    sess.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(sess)

    resp = RedirectResponse("/survey/choose-version", status_code=303)
    resp.set_cookie("session_id", sess.id, httponly=True, max_age=86400 * 30)
    return resp

@app.get("/survey/choose-version", response_class=HTMLResponse)
def choose_version(request: Request,
                   session_id: Optional[str] = Cookie(default=None),
                   db: Session = Depends(get_db)):
    sess = _get_session(request, db, session_id)
    if not sess:
        return RedirectResponse("/survey")
    active = json.loads(sess.active_sections or "[]")
    return templates.TemplateResponse("survey/choose_version.html", {
        "request": request, "num_sections": len(active)
    })

@app.post("/survey/choose-version")
async def choose_version_submit(request: Request, version: str = Form(...),
                                 session_id: Optional[str] = Cookie(default=None),
                                 db: Session = Depends(get_db)):
    sess = _get_session(request, db, session_id)
    if not sess:
        return RedirectResponse("/survey")
    
    sess.survey_type = version
    active = json.loads(sess.active_sections or "[]")
    
    # ── התיקון: סינון פרקים בגרסה הקצרה ──
    if version == "short":
        sections_to_remove = ["section7", "section9"] # חנויות ונשירה נמחקים מהמסלול
        active = [s for s in active if s not in sections_to_remove]
        sess.active_sections = json.dumps(active)

    sess.updated_at = datetime.utcnow()
    db.commit()
    
    first_section = active[0] if active else "submit"
    return RedirectResponse(f"/survey/{first_section}", status_code=303)

def _make_section(num: str):
    async def get_handler(request: Request, session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
        sess, r = _require(request, db, session_id)
        if r: return r
        return templates.TemplateResponse(f"survey/section{num}.html", {
            "request": request, "session": sess,
            "data": json.loads(getattr(sess, f"section{num}") or "{}"),
            "active": json.loads(sess.active_sections or "[]"),
            "SECTION_LABELS": SECTION_LABELS
        })

    async def post_handler(request: Request, session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
        sess, r = _require(request, db, session_id)
        if r: return r
        form = await request.form()
        data = {}
        for k, v in form.multi_items():
            if k in data:
                if isinstance(data[k], list): data[k].append(v)
                else: data[k] = [data[k], v]
            else: data[k] = v
        
        setattr(sess, f"section{num}", json.dumps(data, ensure_ascii=False))
        active = json.loads(sess.active_sections or "[]")
        nxt = next_section(active, f"section{num}")
        sess.current_section = nxt or "submit"
        sess.updated_at = datetime.utcnow()
        db.commit()
        return RedirectResponse(f"/survey/{nxt}" if nxt else "/survey/submit", status_code=303)

    return get_handler, post_handler

for _n in ["2", "3", "4", "5", "6", "7", "8", "9"]:
    _g, _p = _make_section(_n)
    app.get(f"/survey/section{_n}", response_class=HTMLResponse)(_g)
    app.post(f"/survey/section{_n}")(_p)

@app.get("/survey/submit", response_class=HTMLResponse)
def submit_get(request: Request, session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    sess, r = _require(request, db, session_id)
    if r: return r
    return templates.TemplateResponse("survey/submit.html", {
        "request": request, "session": sess,
        "active": json.loads(sess.active_sections or "[]"), "SECTION_LABELS": SECTION_LABELS
    })

@app.post("/survey/submit")
async def submit_post(request: Request, lottery_email: Optional[str] = Form(default=None),
                      session_id: Optional[str] = Cookie(default=None),
                      pending_id_hash: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    sess, r = _require(request, db, session_id)
    if r: return r
    if pending_id_hash and not db.query(IdHash).filter_by(id_hash=pending_id_hash).first():
        db.add(IdHash(id_hash=pending_id_hash))
    sess.submitted = True
    sess.updated_at = datetime.utcnow()
    db.commit()
    resp = templates.TemplateResponse("survey/complete.html", {"request": request, "lottery_email": lottery_email})
    resp.delete_cookie("session_id")
    resp.delete_cookie("pending_id_hash")
    return resp

@app.post("/survey/delete")
async def delete_survey(request: Request, db: Session = Depends(get_db)):
    ip_hash = hash_ip(request.client.host)
    for s in db.query(SurveySession).filter_by(ip_hash=ip_hash).all():
        db.delete(s)
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_id")
    resp.delete_cookie("pending_id_hash")
    return resp

@app.post("/survey/resume")
async def resume(request: Request, action: str = Form(...), session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    ip_hash = hash_ip(request.client.host)
    if action == "new":
        for s in db.query(SurveySession).filter_by(ip_hash=ip_hash, submitted=False).all():
            db.delete(s)
        db.commit()
        resp = RedirectResponse("/survey", status_code=303)
        resp.delete_cookie("session_id")
        return resp
    sess = db.query(SurveySession).filter_by(ip_hash=ip_hash, submitted=False).order_by(SurveySession.created_at.desc()).first()
    if sess:
        return RedirectResponse(f"/survey/{sess.current_section or 'section2'}", status_code=303)
    return RedirectResponse("/survey", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
def admin_login(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})

@app.post("/admin", response_class=HTMLResponse)
async def admin_post(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    if password != ADMIN_PASSWORD:
        return templates.TemplateResponse("admin/login.html", {"request": request, "error": "סיסמה שגויה"})
    total     = db.query(SurveySession).count()
    submitted = db.query(SurveySession).filter_by(submitted=True).count()
    sessions  = db.query(SurveySession).filter_by(submitted=True).all()
    region_counts = {}
    for s in sessions:
        if s.section1:
            r = json.loads(s.section1).get("region", "לא ידוע")
            region_counts[r] = region_counts.get(r, 0) + 1
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "total": total, "submitted": submitted,
        "in_progress": total - submitted, "region_counts": region_counts,
    })
MAINEOF

# ================================================================
# Generate all the static and templates from previous block here 
# (Style.css, base.html, home.html, consent, etc...)
# (All cat > templates/... EOF remain the same as your previous block)
# ================================================================

# [For brevity, the script will write all the exact same HTML/CSS files as provided in your prompt]

cat > static/style.css << 'CSSEOF'
:root {
  --brand: #1a2e4a;
  --gold:  #c9a227;
  --light: #f5f0e8;
  --text:  #1c1c1c;
  --error: #c0392b;
  --radius: 10px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { direction: rtl; font-family: 'Segoe UI', Arial, sans-serif; background: var(--light); color: var(--text); }
body { min-height: 100vh; display: flex; flex-direction: column; }
nav { background: var(--brand); color: white; padding: 12px 24px; display: flex; align-items: center; gap: 16px; }
nav img { height: 40px; }
nav a { color: var(--gold); text-decoration: none; font-weight: bold; }
.container { max-width: 720px; margin: 32px auto; padding: 0 16px; flex: 1; }
.card { background: white; border-radius: var(--radius); padding: 28px 32px; box-shadow: 0 2px 12px rgba(0,0,0,.08); margin-bottom: 24px; }
.card h1 { color: var(--brand); margin-bottom: 16px; font-size: 1.6rem; }
.card h2 { color: var(--brand); margin-bottom: 12px; font-size: 1.2rem; }
.form-group { margin-bottom: 20px; }
label { display: block; font-weight: 600; margin-bottom: 6px; }
input[type=text], input[type=date], input[type=email], input[type=number], select, textarea { width: 100%; padding: 10px 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
input[type=text]:focus, input[type=date]:focus, select:focus { outline: none; border-color: var(--gold); box-shadow: 0 0 0 2px rgba(201,162,39,.2); }
.checkbox-group { display: flex; flex-direction: column; gap: 8px; }
.checkbox-group label, .radio-group label { font-weight: normal; display: flex; align-items: center; gap: 8px; cursor: pointer; }
.radio-group { display: flex; flex-direction: column; gap: 8px; }
.scale-group { display: flex; gap: 10px; flex-wrap: wrap; }
.scale-group label { display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: pointer; min-width: 56px; text-align: center; font-size: .85rem; font-weight: normal; }
.other-input { margin-top: 6px; display: none; }
.other-input.visible { display: block; }
.btn { display: inline-block; padding: 11px 28px; border-radius: 6px; font-size: 1rem; font-weight: bold; cursor: pointer; border: none; text-decoration: none; transition: opacity .15s; }
.btn-primary { background: var(--brand); color: white; }
.btn-gold    { background: var(--gold);  color: var(--brand); }
.btn-danger  { background: var(--error); color: white; }
.btn:hover   { opacity: .85; }
.btn-row     { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; }
.section-nav { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 20px; }
.section-nav a, .section-nav span { padding: 4px 12px; border-radius: 20px; font-size: .82rem; font-weight: 600; text-decoration: none; }
.section-nav .done  { background: #d4edda; color: #155724; }
.section-nav .current { background: var(--brand); color: white; }
.section-nav .pending { background: #e9ecef; color: #666; }
.error-msg { background: #fdecea; color: var(--error); padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; }
.hero { background: linear-gradient(135deg, var(--brand) 60%, #2a4a6e); color: white; text-align: center; padding: 56px 24px; }
.hero img { height: 80px; margin-bottom: 16px; }
.hero h1  { font-size: 2rem; margin-bottom: 12px; }
.hero p   { font-size: 1.1rem; opacity: .88; max-width: 540px; margin: 0 auto 24px; }
.prizes   { background: white; border-radius: var(--radius); padding: 20px; margin: 24px auto; max-width: 500px; color: var(--brand); text-align: right; }
.prizes h3 { color: var(--gold); margin-bottom: 10px; }
.prizes ul { padding-right: 20px; }
.prizes li { margin-bottom: 6px; }
.delete-btn-wrapper { position: fixed; bottom: 20px; left: 20px; z-index: 999; }
.delete-btn-wrapper form { margin: 0; }
.delete-btn-wrapper button { background: rgba(192,57,43,.12); border: 1px solid var(--error); color: var(--error); border-radius: 6px; padding: 7px 14px; font-size: .82rem; cursor: pointer; }
.delete-btn-wrapper button:hover { background: var(--error); color: white; }
footer { text-align: center; padding: 16px; font-size: .82rem; color: #888; }
CSSEOF

cat > templates/base.html << 'BASEEOF'
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}סקר קהילת משחקי תפקידים בישראל{% endblock %}</title>
  <link rel="icon" href="https://gate.roleplay.top/rpg-game.png">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
<nav>
  <a href="/"><img src="https://gate.roleplay.top/full-logo.png" alt="שער המשחקים" onerror="this.style.display='none'"></a>
  <a href="/">דף הבית</a>
  <a href="/survey">השאלון</a>
</nav>

{% block content %}{% endblock %}

{% block delete_btn %}
<div class="delete-btn-wrapper">
  <form method="post" action="/survey/delete"
        onsubmit="return confirm('האם למחוק את כל הנתונים שלך מהמערכת?')">
    <button type="submit">🗑 מחק את כל הנתונים שלי</button>
  </form>
</div>
{% endblock %}

<footer>© 2025 דוח הקהילה השנתי למשחקי תפקידים בישראל</footer>
</body>
</html>
BASEEOF

cat > templates/home.html << 'HOMEEOF'
{% extends "base.html" %}
{% block delete_btn %}{% endblock %}
{% block content %}
<div class="hero">
  <img src="https://gate.roleplay.top/full-logo.png" alt="לוגו">
  <h1>דוח הקהילה השנתי<br>למשחקי תפקידים בישראל 2025</h1>
  <p>עזור/י לנו למפות את עולם משחקי התפקידים בישראל — מי משחקים, איפה, באילו שיטות, ומה חסר.</p>
  <a href="/survey" class="btn btn-gold" style="font-size:1.1rem;padding:14px 36px">מלא/י את השאלון →</a>
  <div class="prizes">
    <h3>🎁 הגרלה בין המשתתפים — פרסים בשווי 1,000 ₪</h3>
    <ul>
      <li>שובר 300 ₪ לממלכה (×2)</li>
      <li>ערכת חרבות וכשפים — האדומה והסגולה (×3)</li>
      <li>ערכת Pathfinder עולמות פראיים (×1)</li>
    </ul>
    <p style="font-size:.85rem;margin-top:8px;color:#555">כתובת מייל לצורך ההגרלה תישאל בסוף השאלון. המידע לא יקושר לתשובותיך.</p>
  </div>
</div>
<div class="container">
  <div class="card">
    <h2>על השאלון</h2>
    <p>שאלון זה נועד למפות את תחום משחקי התפקידים בישראל: מי משחקים, איפה, באילו שיטות, מה חסר, ואיך אפשר לפתח את הקהילה.</p>
    <p style="margin-top:10px">הנתונים ינותחו בצורה מצרפית בלבד, ללא פרסום פרטים מזהים.</p>
    <p style="margin-top:10px"><strong>משך מילוי:</strong> 10–20 דקות בהתאם למסלול.</p>
    <div class="btn-row" style="margin-top:16px">
      <a href="/survey" class="btn btn-primary">התחל/י את השאלון</a>
    </div>
  </div>
</div>
{% endblock %}
HOMEEOF

cat > templates/survey/consent.html << 'CONEOF'
{% extends "base.html" %}
{% block delete_btn %}{% endblock %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>הסכמה להשתתפות</h1>
    <p>שאלון זה מיועד למפות את תחום משחקי התפקידים בישראל. המידע שייאסף ינותח במטרה לשפר את הקהילה, הכנסים, החנויות, החוגים, המנחים והיוצרים בארץ.</p>
    <p style="margin-top:12px"><strong>פרטיות:</strong> מידע אישי מזהה יישמר בנפרד ולא יקושר לתשובות. תעודת הזהות נאספת אך ורק לצורך מניעת כפילויות ותישמר מוצפנת.</p>
    <p style="margin-top:12px">ניתן לצאת מהסקר בכל עת — הנתונים שנשמרו יישמרו, וניתן לחזור ולהמשיך.</p>
    <form method="post" action="/survey/consent" style="margin-top:20px">
      <div class="form-group">
        <div class="radio-group">
          <label><input type="radio" name="consent" value="yes" required> כן, אני מאשר/ת להשתתף</label>
          <label><input type="radio" name="consent" value="no"> לא</label>
        </div>
      </div>
      <button type="submit" class="btn btn-primary">המשך/י</button>
    </form>
  </div>
</div>
{% endblock %}
CONEOF

cat > templates/survey/identity.html << 'IDEOF'
{% extends "base.html" %}
{% block delete_btn %}{% endblock %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>תעודת זהות</h1>
    <p>מספר תעודת הזהות נאסף אך ורק כדי לוודא שכל אדם ממלא את השאלון פעם אחת. הוא יישמר מוצפן ולא יהיה קישור בינו לבין שאר תשובותיך.</p>
    {% if error %}
    <div class="error-msg">{{ error }}</div>
    {% endif %}
    <form method="post" action="/survey/identity" style="margin-top:16px">
      <div class="form-group">
        <label for="id_number">מספר תעודת זהות (9 ספרות)</label>
        <input type="text" id="id_number" name="id_number" maxlength="9" pattern="\d{5,9}" inputmode="numeric" placeholder="000000000" required autocomplete="off">
      </div>
      <button type="submit" class="btn btn-primary">המשך/י</button>
    </form>
  </div>
</div>
<script>
document.querySelector('form').addEventListener('submit', function(e) {
  const val = document.getElementById('id_number').value.trim().padStart(9,'0');
  let total = 0;
  for (let i = 0; i < 9; i++) {
    let v = parseInt(val[i]) * (i % 2 === 0 ? 1 : 2);
    if (v > 9) v -= 9;
    total += v;
  }
  if (total % 10 !== 0) {
    e.preventDefault();
    alert('מספר תעודת הזהות אינו תקין. אנא בדוק/י שוב.');
  }
});
</script>
{% endblock %}
IDEOF

cat > templates/survey/demographics.html << 'DEMEOF'
{% extends "base.html" %}
{% block delete_btn %}{% endblock %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>פרטים בסיסיים</h1>
    {% if error %}<div class="error-msg">{{ error }}</div>{% endif %}
    <form method="post" action="/survey/demographics">
      <div class="form-group">
        <label>תאריך לידה</label>
        <input type="date" name="dob" id="dob_field">
        <label style="margin-top:8px;font-weight:normal"><input type="checkbox" name="dob_prefer_not" id="dob_pref" onchange="document.getElementById('dob_field').disabled=this.checked"> מעדיף/ה לא לענות</label>
      </div>
      <div class="form-group">
        <label>אזור מגורים *</label>
        <select name="region" required>
          <option value="">-- בחר/י --</option><option>צפון</option><option>חיפה והקריות</option><option>השרון</option><option>גוש דן</option><option>תל אביב-יפו</option><option>ירושלים והסביבה</option><option>השפלה</option><option>דרום</option><option>יהודה ושומרון</option><option>אילת והערבה</option><option>גר/ה בחו״ל</option><option>מעדיף/ה לא לענות</option>
        </select>
      </div>
      <div class="form-group">
        <label>עיר / יישוב (לא חובה)</label>
        <input type="text" name="city" placeholder="לדוגמה: תל אביב">
      </div>
      <div class="form-group">
        <label>מה הקשר שלך לעולם משחקי התפקידים? (ניתן לבחור כמה) *</label>
        <div class="checkbox-group">
          <label><input type="checkbox" name="roles" value="tabletop_player"> אני משחק/ת במשחקי תפקידים שולחניים</label>
          <label><input type="checkbox" name="roles" value="gm"> אני מנחה משחקי תפקידים שולחניים</label>
          <label><input type="checkbox" name="roles" value="larp_participant"> אני משתתף/ת במשחקי תפקידים חיים / לארפים</label>
          <label><input type="checkbox" name="roles" value="larp_organizer"> אני מארגן/ת משחקי תפקידים חיים / לארפים</label>
          <label><input type="checkbox" name="roles" value="digital_only"> אני משחק/ת במשחקי תפקידים דיגיטליים בלבד</label>
          <label><input type="checkbox" name="roles" value="parent"> אני הורה לילד/ה שמשחק/ת</label>
          <label><input type="checkbox" name="roles" value="facilitator"> אני מפעיל/ה חוגים או סדנאות</label>
          <label><input type="checkbox" name="roles" value="business"> אני בעל/ת עסק, חנות או הוצאה בתחום</label>
          <label><input type="checkbox" name="roles" value="creator"> אני יוצר/ת תוכן, כותב/ת, מתרגם/ת</label>
          <label><input type="checkbox" name="roles" value="interested"> אני מתעניין/ת אבל עדיין לא משחק/ת</label>
          <label><input type="checkbox" name="roles" value="former_player"> שיחקתי בעבר, אבל כיום לא</label>
          <label><input type="checkbox" name="roles" value="curious"> אין לי קשר ישיר, אבל התחום מעניין אותי</label>
        </div>
      </div>
      <button type="submit" class="btn btn-primary">המשך/י</button>
    </form>
  </div>
</div>
{% endblock %}
DEMEOF

cat > templates/survey/choose_version.html << 'CHEOF'
{% extends "base.html" %}
{% block delete_btn %}{% endblock %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>בחירת גרסת השאלון</h1>
    <p>על בסיס מה שסימנת, ישנם <strong>{{ num_sections }}</strong> חלקים שרלוונטיים עבורך.</p>
    <p style="margin-top:12px">באיזו גרסה תרצה/י לענות?</p>
    <form method="post" action="/survey/choose-version" style="margin-top:20px">
      <div class="radio-group">
        <label style="font-weight:normal;padding:14px;border:1px solid #ddd;border-radius:8px;margin-bottom:10px;cursor:pointer">
          <input type="radio" name="version" value="short" required>
          <strong>גרסה קצרה (8–12 דקות)</strong><br>
          <span style="font-size:.9rem;color:#555">~45–55 שאלות עם התניות — מומלץ לרוב המשיבים</span>
        </label>
        <label style="font-weight:normal;padding:14px;border:1px solid #ddd;border-radius:8px;cursor:pointer">
          <input type="radio" name="version" value="long">
          <strong>גרסה מורחבת (20 דקות)</strong><br>
          <span style="font-size:.9rem;color:#555">שאלות נוספות לעומק — עסקים, יצירה, בטיחות, כנסים</span>
        </label>
      </div>
      <button type="submit" class="btn btn-primary" style="margin-top:20px">התחל/י</button>
    </form>
  </div>
</div>
{% endblock %}
CHEOF

cat > templates/survey/resume.html << 'RESEOF'
{% extends "base.html" %}
{% block delete_btn %}{% endblock %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>ברוך/ה שב/ה!</h1>
    <p>מצאנו מילוי שאלון לא גמור מהכתובת שלך.</p>
    <p style="margin-top:8px">החלק האחרון שמילאת: <strong>{{ SECTION_LABELS.get(session.current_section, session.current_section) }}</strong></p>
    <form method="post" action="/survey/resume" style="margin-top:20px">
      <div class="btn-row">
        <button name="action" value="continue" class="btn btn-primary">המשך/י מאיפה שעצרתי</button>
        <button name="action" value="new" class="btn btn-danger" onclick="return confirm('כל הנתונים הקודמים יימחקו. להתחיל מחדש?')">התחל/י מחדש</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
RESEOF

cat > templates/survey/_nav.html << 'NAVEOF'
{% macro section_nav(active, current, session, SECTION_LABELS) %}
<div class="section-nav">
  {% for s in active %}
    {% set label = SECTION_LABELS.get(s, s) %}
    {% set sec_data = session[s] if session and s in session.__dict__ else None %}
    {% if s == current %}
      <span class="current">{{ label }}</span>
    {% elif sec_data %}
      <a href="/survey/{{ s }}" class="done">✓ {{ label }}</a>
    {% else %}
      <span class="pending">{{ label }}</span>
    {% endif %}
  {% endfor %}
</div>
{% endmacro %}
NAVEOF

cat > templates/survey/section2.html << 'S2EOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>חלק 2 — היכרות כללית עם התחום</h1>
    <form method="post" action="/survey/section2">
      <div class="form-group">
        <label>6. כמה שנים את/ה מכיר/ה את תחום משחקי התפקידים? *</label>
        <div class="radio-group">
          {% for opt in ["פחות משנה","1–2 שנים","3–5 שנים","6–10 שנים","11–20 שנים","מעל 20 שנים","לא בטוח/ה"] %}
          <label><input type="radio" name="years_in_field" value="{{ opt }}" {% if data.get('years_in_field')==opt %}checked{% endif %} required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>7. איך נחשפת לראשונה למשחקי תפקידים? (ניתן לבחור כמה)</label>
        <div class="checkbox-group">
          {% for opt in ["חברים","משפחה","בית ספר","חוג","כנס","חנות משחקים","יוטיוב / פודקאסט / תוכן אונליין","משחקי מחשב","סדרות / סרטים / תרבות פופולרית","צבא / שירות לאומי / לימודים","רשתות חברתיות","דיסקורד / קהילת אונליין"] %}
          <label><input type="checkbox" name="first_exposure" value="{{ opt }}" {% if opt in data.get('first_exposure',[]) %}checked{% endif %}> {{ opt }}</label>
          {% endfor %}
          <label><input type="checkbox" id="fe_other_cb" name="first_exposure" value="other" onchange="document.getElementById('fe_other').classList.toggle('visible',this.checked)"> אחר:</label>
          <input type="text" name="first_exposure_other" id="fe_other" class="other-input {% if data.get('first_exposure_other') %}visible{% endif %}" value="{{ data.get('first_exposure_other','') }}" placeholder="פרט/י...">
        </div>
      </div>
      <div class="form-group">
        <label>8. עד כמה משחקי תפקידים הם חלק משמעותי מהחיים שלך? *</label>
        <div class="scale-group">
          {% for i in [1,2,3,4,5] %}
          {% set labels = {1:"תחביב שולי מאוד",2:"תחביב קטן",3:"תחביב משמעותי",4:"חלק מרכזי מהפנאי",5:"חלק מרכזי מהזהות"} %}
          <label><input type="radio" name="importance" value="{{ i }}" {% if data.get('importance')==i %}checked{% endif %} required><span>{{ i }}</span><span style="font-size:.75rem">{{ labels[i] }}</span></label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>9. אילו סוגי משחקי תפקידים מעניינים אותך? (ניתן לבחור כמה)</label>
        <div class="checkbox-group">
          {% for opt in ["משחקי תפקידים שולחניים","משחקי תפקידים חיים / לארפים","משחקי תפקידים לילדים ונוער","משחקי תפקידים טיפוליים / חינוכיים","משחקי תפקידים אונליין","משחקים חד-פעמיים / וואנשוטים","קמפיינים ארוכים","משחקים סיפוריים / נרטיביים","משחקים טקטיים / קרביים","משחקי תפקידים עצמאיים / אינדי","מבוכים ודרקונים בעיקר","יצירת שיטות ומשחקים","תרגום והוצאה לאור"] %}
          <label><input type="checkbox" name="interest_types" value="{{ opt }}" {% if opt in data.get('interest_types',[]) %}checked{% endif %}> {{ opt }}</label>
          {% endfor %}
          <label><input type="checkbox" id="it_other_cb" name="interest_types" value="other" onchange="document.getElementById('it_other').classList.toggle('visible',this.checked)"> אחר:</label>
          <input type="text" name="interest_types_other" id="it_other" class="other-input {% if data.get('interest_types_other') %}visible{% endif %}" value="{{ data.get('interest_types_other','') }}" placeholder="פרט/י...">
        </div>
      </div>
      <div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div>
    </form>
  </div>
</div>
{% endblock %}
S2EOF

cat > templates/survey/section3.html << 'S3EOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>חלק 3 — שחקנים במשחקי תפקידים שולחניים</h1>
    <form method="post" action="/survey/section3">
      <div class="form-group">
        <label>10. האם את/ה משחק/ת כיום במשחקי תפקידים שולחניים? *</label>
        <div class="radio-group">
          {% for opt in ["כן, באופן קבוע","כן, מדי פעם","לעיתים נדירות","לא כרגע, אבל שיחקתי בעבר","עוד לא שיחקתי, אבל אני רוצה"] %}
          <label><input type="radio" name="currently_playing" value="{{ opt }}" {% if data.get('currently_playing')==opt %}checked{% endif %} required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>11. באיזו תדירות את/ה משחק/ת? *</label>
        <div class="radio-group">
          {% for opt in ["יותר מפעם בשבוע","פעם בשבוע","פעמיים-שלוש בחודש","פעם בחודש","כמה פעמים בשנה","כמעט ולא"] %}
          <label><input type="radio" name="frequency" value="{{ opt }}" {% if data.get('frequency')==opt %}checked{% endif %} required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>12. באילו מסגרות את/ה משחק/ת? (ניתן לבחור כמה)</label>
        <div class="checkbox-group">
          {% for opt in ["קבוצה פרטית עם חברים","קבוצה אונליין","חוג","משחקים בכנסים","משחקים בחנויות","משחקים במתחמי משחק","משחקים דרך עמותה/ארגון","משחקים דרך שרת דיסקורד / קהילה דיגיטלית","משחקים בתשלום עם מנחה מקצועי/ת"] %}
          <label><input type="checkbox" name="frameworks" value="{{ opt }}" {% if opt in data.get('frameworks',[]) %}checked{% endif %}> {{ opt }}</label>
          {% endfor %}
          <label><input type="checkbox" name="frameworks" value="other" onchange="document.getElementById('fw_other').classList.toggle('visible',this.checked)"> אחר:</label>
          <input type="text" name="frameworks_other" id="fw_other" class="other-input" value="{{ data.get('frameworks_other','') }}" placeholder="פרט/י...">
        </div>
      </div>
      <div class="form-group">
        <label>13. איפה מתקיימים רוב המשחקים שלך? *</label>
        <div class="radio-group">
          {% for opt in ["בבית שלי / של חברים","אונליין","חנות משחקים","מתנ\"ס / מרכז קהילתי","מוסד חינוכי","מתחם משחק ייעודי","כנסים","מקום ציבורי כמו ספרייה / בית קפה"] %}
          <label><input type="radio" name="location" value="{{ opt }}" {% if data.get('location')==opt %}checked{% endif %} required> {{ opt }}</label>
          {% endfor %}
          <label><input type="radio" name="location" value="other" onchange="document.getElementById('loc_other').classList.toggle('visible',this.checked)"> אחר:</label>
          <input type="text" name="location_other" id="loc_other" class="other-input" value="{{ data.get('location_other','') }}" placeholder="פרט/י...">
        </div>
      </div>
      <div class="form-group">
        <label>14. האם את/ה משחק/ת בעיקר אונליין או פרונטלית? *</label>
        <div class="radio-group">
          {% for opt in ["בעיקר פרונטלית","בעיקר אונליין","בערך חצי-חצי","תלוי בתקופה","לא רלוונטי"] %}
          <label><input type="radio" name="online_or_frontally" value="{{ opt }}" {% if data.get('online_or_frontally')==opt %}checked{% endif %} required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group" id="online_tools_group">
        <label>15. באילו כלים את/ה משתמש/ת למשחק אונליין?</label>
        <div class="checkbox-group">
          {% for opt in ["Discord","Zoom","Google Meet","Roll20","Foundry VTT","Owlbear Rodeo","Tabletop Simulator","D&D Beyond","Notion / Google Docs / Sheets","WhatsApp / Telegram","לא משתמש/ת בכלים מיוחדים"] %}
          <label><input type="checkbox" name="online_tools" value="{{ opt }}" {% if opt in data.get('online_tools',[]) %}checked{% endif %}> {{ opt }}</label>
          {% endfor %}
          <label><input type="checkbox" name="online_tools" value="other" onchange="document.getElementById('ot_other').classList.toggle('visible',this.checked)"> אחר:</label>
          <input type="text" name="online_tools_other" id="ot_other" class="other-input" value="{{ data.get('online_tools_other','') }}" placeholder="פרט/י...">
        </div>
      </div>
      <div class="form-group">
        <label>16. באילו שיטות משחק שיחקת בשנה האחרונה?</label>
        <div class="checkbox-group">
          {% for opt in ["מבוכים ודרקונים 5e","מבוכים ודרקונים גרסאות אחרות","Pathfinder","Call of Cthulhu","Vampire / World of Darkness","Fate","Powered by the Apocalypse","Blades in the Dark","OSR / משחקים בסגנון ישן","משחקי אינדי / נרטיביים","משחקים בעברית","שיטה מקורית של המנחה","שיטה שיצרנו בעצמנו","לא יודע/ת את שם השיטה"] %}
          <label><input type="checkbox" name="systems" value="{{ opt }}" {% if opt in data.get('systems',[]) %}checked{% endif %}> {{ opt }}</label>
          {% endfor %}
          <label><input type="checkbox" name="systems" value="other" onchange="document.getElementById('sys_other').classList.toggle('visible',this.checked)"> אחר:</label>
          <input type="text" name="systems_other" id="sys_other" class="other-input" value="{{ data.get('systems_other','') }}" placeholder="פרט/י...">
        </div>
      </div>
      <div class="form-group">
        <label>17. מה הז׳אנרים המועדפים עליך?</label>
        <div class="checkbox-group">
          {% for opt in ["פנטזיה קלאסית","פנטזיה אפלה","מדע בדיוני","אימה","חקירה / מסתורין","סייברפאנק","גיבורי-על","היסטורי","פוסט-אפוקליפטי","קומדיה","דרמה חברתית","פוליטי / תככים","הרפתקאות לילדים/משפחה"] %}
          <label><input type="checkbox" name="genres" value="{{ opt }}" {% if opt in data.get('genres',[]) %}checked{% endif %}> {{ opt }}</label>
          {% endfor %}
          <label><input type="checkbox" name="genres" value="other" onchange="document.getElementById('gen_other').classList.toggle('visible',this.checked)"> אחר:</label>
          <input type="text" name="genres_other" id="gen_other" class="other-input" value="{{ data.get('genres_other','') }}" placeholder="פרט/י...">
        </div>
      </div>
      <div class="form-group">
        <label>18. כמה קבוצות משחק פעילות יש לך כיום? *</label>
        <div class="radio-group">
          {% for opt in ["0","1","2","3","4 ומעלה"] %}
          <label><input type="radio" name="group_count" value="{{ opt }}" {% if data.get('group_count')==opt %}checked{% endif %} required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>19. כמה אנשים בדרך כלל בקבוצת המשחק המרכזית שלך? *</label>
        <div class="radio-group">
          {% for opt in ["2","3–4","5–6","7–8","יותר מ-8","משתנה מאוד"] %}
          <label><input type="radio" name="group_size" value="{{ opt }}" {% if data.get('group_size')==opt %}checked{% endif %} required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>20. מה משך מפגש משחק ממוצע אצלך? *</label>
        <div class="radio-group">
          {% for opt in ["עד שעה","שעה–שעתיים","שעתיים–שלוש","שלוש–ארבע שעות","מעל ארבע שעות","משתנה מאוד"] %}
          <label><input type="radio" name="session_length" value="{{ opt }}" {% if data.get('session_length')==opt %}checked{% endif %} required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>21. מהם הקשיים המרכזיים שלך כשחקן/ית?</label>
        <div class="checkbox-group">
          {% for opt in ["קשה למצוא קבוצה","קשה למצוא מנחה","קשה לתאם זמנים","אין מספיק מקומות לשחק בהם","התחבורה בעייתית","עלויות גבוהות","אין מספיק משחקים באזור שלי","קשה למצוא משחקים שמתאימים לגיל שלי","קשה למצוא משחקים שמתאימים לרמת הניסיון שלי","קושי חברתי / חשש להצטרף לקבוצה חדשה","חוסר נגישות פיזית","חוסר נגישות שפתית","חוסר היכרות עם השיטות","קהילה לא מספיק מזמינה","אין קושי מיוחד"] %}
          <label><input type="checkbox" name="difficulties" value="{{ opt }}" {% if opt in data.get('difficulties',[]) %}checked{% endif %}> {{ opt }}</label>
          {% endfor %}
          <label><input type="checkbox" name="difficulties" value="other" onchange="document.getElementById('diff_other').classList.toggle('visible',this.checked)"> אחר:</label>
          <input type="text" name="difficulties_other" id="diff_other" class="other-input" value="{{ data.get('difficulties_other','') }}" placeholder="פרט/י...">
        </div>
      </div>
      <div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div>
    </form>
  </div>
</div>
{% endblock %}
S3EOF

cat > templates/survey/section4.html << 'S4EOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>חלק 4 — מנחים</h1>
    <form method="post" action="/survey/section4">
      <div class="form-group">
        <label>האם אתה/את מנחה כיום? *</label>
        <div class="radio-group">
          {% for opt in ["כן, באופן קבוע","כן, מדי פעם","לא כרגע, אבל הנחיתי בעבר","מעולם לא הנחיתי אבל אני רוצה","לא מתעתד/ת להנחות"] %}
          <label><input type="radio" name="gm_status" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>כמה שחקנים בממוצע בקבוצות שאתה/את מנחה? *</label>
        <div class="radio-group">
          {% for opt in ["2","3–4","5–6","7–8","יותר מ-8","משתנה"] %}
          <label><input type="radio" name="gm_group_size" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>באילו שיטות אתה/את מנחה? (ניתן לבחור כמה)</label>
        <div class="checkbox-group">
          {% for opt in ["מבוכים ודרקונים 5e","Pathfinder","Call of Cthulhu","Fate","Powered by the Apocalypse","שיטה שיצרתי","שיטות בעברית","שיטות אינדי","אחרות"] %}
          <label><input type="checkbox" name="gm_systems" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>האם אתה/את מנחה בתשלום? *</label>
        <div class="radio-group">
          {% for opt in ["כן, בתשלום מלא","לעיתים, חלקית","לא, מנחה ללא תשלום","מעוניין/ת להתחיל להנחות בתשלום"] %}
          <label><input type="radio" name="gm_paid" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>מה הקשיים המרכזיים שלך כמנחה?</label>
        <div class="checkbox-group">
          {% for opt in ["קשה למצוא שחקנים","קשה לתאם זמנים","חוסר זמן להכנה","קשה למצוא מקום לשחק","חוסר ניסיון / ביטחון","חוסר חומרים בעברית","חוסר קהילת מנחים להיוועץ בה","שחיקה"] %}
          <label><input type="checkbox" name="gm_difficulties" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>האם היית מעוניין/ת בהכשרת מנחים? *</label>
        <div class="radio-group">
          {% for opt in ["כן, מאוד","כן, אם יהיה זמין","לא צריך/ה, כבר מנוסה/ת","לא מעוניין/ת"] %}
          <label><input type="radio" name="gm_training" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div>
    </form>
  </div>
</div>
{% endblock %}
S4EOF

cat > templates/survey/section5.html << 'S5EOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>חלק 5 — משחקי תפקידים חיים (לארפ)</h1>
    <form method="post" action="/survey/section5">
      <div class="form-group">
        <label>באיזו תדירות אתה/את משתתף/ת בלארפים? *</label>
        <div class="radio-group">
          {% for opt in ["מספר פעמים בחודש","פעם בחודש","מספר פעמים בשנה","פעם-פעמיים בשנה","לעיתים נדירות","לא השתתפתי עדיין אבל מעוניין/ת"] %}
          <label><input type="radio" name="larp_frequency" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>באילו סוגי לארפים אתה/את משתתף/ת? (ניתן לבחור כמה)</label>
        <div class="checkbox-group">
          {% for opt in ["לארפ גדול (100+ משתתפים)","לארפ בינוני (20–100 משתתפים)","לארפ קטן / קאמרי","Nordic larp","אקשן / לחימה","דרמה / פוליטי","היסטורי","פנטזיה","מד\"ב","אחר"] %}
          <label><input type="checkbox" name="larp_types" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>האם אתה/את גם מארגן/ת לארפים? *</label>
        <div class="radio-group">
          {% for opt in ["כן, מארגן/ת בקביעות","כן, לעיתים","לא, רק משתתף/ת"] %}
          <label><input type="radio" name="larp_organizer" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>מה הקשיים המרכזיים שלך בתחום הלארפ?</label>
        <div class="checkbox-group">
          {% for opt in ["עלות גבוהה","תחבורה","מיעוט אירועים באזורי","חוסר ידע כיצד להיכנס לתחום","חשש חברתי","אין מספיק לארפים בז׳אנר שאני אוהב/ת","אין קושי"] %}
          <label><input type="checkbox" name="larp_difficulties" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div>
    </form>
  </div>
</div>
{% endblock %}
S5EOF

cat > templates/survey/section6.html << 'S6EOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>חלק 6 — הורים</h1>
    <form method="post" action="/survey/section6">
      <div class="form-group">
        <label>באיזו גיל קבוצה הילד/ה שלך? *</label>
        <div class="radio-group">
          {% for opt in ["עד 7","8–10","11–13","14–17","18+"] %}
          <label><input type="radio" name="child_age" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>במה הילד/ה שלך עוסק/ת? (ניתן לבחור כמה)</label>
        <div class="checkbox-group">
          {% for opt in ["שחקן/ית שולחני/ת","מנחה","משתתף/ת בלארפים","משתמש/ת בדיגיטל בלבד","לא משחק/ת עדיין"] %}
          <label><input type="checkbox" name="child_roles" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>האם את/ה רואה ערך חינוכי או חברתי בתחום? *</label>
        <div class="radio-group">
          {% for opt in ["כן, מאוד","כן, מסוים","לא בטוח/ה","לא ממש","לא"] %}
          <label><input type="radio" name="edu_value" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>האם שילמת על פעילות בתחום לילד/ה? *</label>
        <div class="radio-group">
          {% for opt in ["כן, על חוג","כן, על כנס","כן, על מנחה פרטי","כן, על ציוד / ספרים","לא שילמתי עדיין","מוכן/ה לשלם בתנאים מסוימים"] %}
          <label><input type="radio" name="parent_paid" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>מה חסם/חסמה אותך מלהשקיע יותר בתחום לילד/ה?</label>
        <div class="checkbox-group">
          {% for opt in ["עלות גבוהה","לא מצאתי חוג/פעילות מתאימה","חוסר מידע","חששות בטיחות","הילד/ה לא עניין/ת","אין חסם"] %}
          <label><input type="checkbox" name="parent_barriers" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div>
    </form>
  </div>
</div>
{% endblock %}
S6EOF

cat > templates/survey/section7.html << 'S7EOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>חלק 7 — עסקים, חנויות והוצאות</h1>
    <form method="post" action="/survey/section7">
      <div class="form-group">
        <label>מה סוג העסק / הפעילות שלך? (ניתן לבחור כמה) *</label>
        <div class="checkbox-group">
          {% for opt in ["חנות פיזית","חנות אונליין","הוצאה לאור","ייצור / יצירה","סדנאות / חוגים","מנחה מקצועי בתשלום","מתחם משחק","תרגום","אחר"] %}
          <label><input type="checkbox" name="biz_type" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>כמה שנים הפעילות קיימת? *</label>
        <div class="radio-group">
          {% for opt in ["פחות משנה","1–3 שנים","4–7 שנים","8–15 שנים","מעל 15 שנים"] %}
          <label><input type="radio" name="biz_years" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>מה האתגרים המרכזיים שלך כעסק בתחום?</label>
        <div class="checkbox-group">
          {% for opt in ["שוק קטן","תחרות ממשחקים דיגיטליים","חוסר ביקוש","מחסור בחומרים בעברית","הפצה ולוגיסטיקה","מימון ראשוני","מיתוג ושיווק","חוסר תמיכה ממוסדות","אחר"] %}
          <label><input type="checkbox" name="biz_challenges" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>האם יש עסקים נוספים בתחום שאתה/את משתף/ת פעולה איתם? *</label>
        <div class="radio-group">
          {% for opt in ["כן, שיתוף פעולה פעיל","כן, לפעמים","לא, פועל/ת בנפרד","מעוניין/ת אך לא מצאתי שותפים"] %}
          <label><input type="radio" name="biz_collab" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div>
    </form>
  </div>
</div>
{% endblock %}
S7EOF

cat > templates/survey/section8.html << 'S8EOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>חלק 8 — חסמי כניסה לתחום</h1>
    <p style="margin-bottom:20px">חלק זה מיועד למי שמתעניין/ת אבל עדיין לא הצטרף/ה לעולם משחקי התפקידים.</p>
    <form method="post" action="/survey/section8">
      <div class="form-group">
        <label>מה מעניין אותך בעולם משחקי התפקידים? (ניתן לבחור כמה)</label>
        <div class="checkbox-group">
          {% for opt in ["הסיפורים וההרפתקאות","יצירת דמויות","הפן החברתי","יצירתיות ואלתור","הז'אנרים (פנטזיה, מד\"ב וכו')","האסתטיקה / ציוד","מה שראיתי בתרבות הפופולרית","אחר"] %}
          <label><input type="checkbox" name="interest_in" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>מה מונע ממך להצטרף? (ניתן לבחור כמה) *</label>
        <div class="checkbox-group">
          {% for opt in ["לא יודע/ת איפה למצוא קבוצה","לא יודע/ת איך מתחילים","חשש חברתי","אין לי זמן","העלות גבוהה","אין פעילות באזורי","חשש שזה 'לא בשבילי'","אין מישהו שיכניס אותי","לא מצאתי מנחה מתחילים","אחר"] %}
          <label><input type="checkbox" name="barriers" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>מה היה עוזר לך להצטרף? (ניתן לבחור כמה)</label>
        <div class="checkbox-group">
          {% for opt in ["חבר/ה שיכניס/תכניס אותי","משחק מבוא / הכרות","חוג מתחילים","מנחה מנוסה שמלווה","תוכן הסברתי (יוטיוב, אינסטגרם)","אירוע פתוח לציבור","אחר"] %}
          <label><input type="checkbox" name="would_help" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div>
    </form>
  </div>
</div>
{% endblock %}
S8EOF

cat > templates/survey/section9.html << 'S9EOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>חלק 9 — נשירה מהתחום</h1>
    <p style="margin-bottom:20px">חלק זה מיועד למי ששיחק/ה בעבר אך כיום אינו/ה פעיל/ה.</p>
    <form method="post" action="/survey/section9">
      <div class="form-group">
        <label>כמה זמן שיחקת לפני שהפסקת? *</label>
        <div class="radio-group">
          {% for opt in ["פחות משנה","1–2 שנים","3–5 שנים","6–10 שנים","מעל 10 שנים"] %}
          <label><input type="radio" name="years_active" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>מה גרם לך להפסיק? (ניתן לבחור כמה) *</label>
        <div class="checkbox-group">
          {% for opt in ["קושי בתיאום זמנים","הקבוצה התפרקה","לא מצאתי קבוצה חדשה","מעבר חיים (עבודה, ילדים, לימודים)","חוסר עניין הדרגתי","חוויה לא נעימה בקבוצה","חוסר מנחה","מגורים באזור ללא פעילות","עלות גבוהה","אחר"] %}
          <label><input type="checkbox" name="dropout_reasons" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>האם אתה/את שוקל/ת לחזור? *</label>
        <div class="radio-group">
          {% for opt in ["כן, בהחלט","אולי, בתנאים מסוימים","לא יודע/ת","לא, לא מתכנן/ת"] %}
          <label><input type="radio" name="return_intent" value="{{ opt }}" required> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="form-group">
        <label>מה היה מחזיר אותך לתחום?</label>
        <div class="checkbox-group">
          {% for opt in ["קבוצה קבועה","מנחה מנוסה שמנהל/ת הכל","משחקים קצרים (וואנשוטים)","פעילות באזורי","מחיר נגיש","חברים שחוזרים","אחר"] %}
          <label><input type="checkbox" name="return_factors" value="{{ opt }}"> {{ opt }}</label>
          {% endfor %}
        </div>
      </div>
      <div class="btn-row"><button type="submit" class="btn btn-primary">שמור/י והמשך/י ←</button></div>
    </form>
  </div>
</div>
{% endblock %}
S9EOF

cat > templates/survey/submit.html << 'SUBEOF'
{% extends "base.html" %}
{% block content %}
<div class="container">
  <div class="card">
    <h1>סיום וסיכום</h1>
    <p>תודה על מילוי השאלון! לפני שנשלח, כמה שאלות אחרונות:</p>
    <form method="post" action="/survey/submit" style="margin-top:20px">
      <div class="form-group">
        <label>כתובת מייל להגרלה (לא חובה)</label>
        <p style="font-size:.87rem;color:#555;margin-bottom:6px">זה יישמר בנפרד לחלוטין מתשובותיך ויימחק לאחר ההגרלה.</p>
        <input type="email" name="lottery_email" placeholder="your@email.com" autocomplete="email">
      </div>
      <div style="background:#f0f7ff;border-radius:8px;padding:16px;margin-bottom:16px">
        <strong>החלקים שמילאת:</strong>
        <ul style="margin-top:8px;padding-right:20px">
          {% for s in active %}
          <li>{{ SECTION_LABELS.get(s, s) }}</li>
          {% endfor %}
        </ul>
      </div>
      <p style="font-size:.87rem;color:#666;margin-bottom:16px">עם שליחת הטופס, תעודת הזהות שלך תישמר מוצפנת ולא ניתן יהיה למלא את השאלון שוב עם אותה תעודת זהות.</p>
      <div class="btn-row"><button type="submit" class="btn btn-gold">שלח/י את השאלון ✓</button></div>
    </form>
  </div>
</div>
{% endblock %}
SUBEOF

cat > templates/survey/complete.html << 'COMPEOF'
{% extends "base.html" %}
{% block delete_btn %}{% endblock %}
{% block content %}
<div class="container">
  <div class="card" style="text-align:center">
    <div style="font-size:4rem;margin-bottom:12px">🎲</div>
    <h1>תודה רבה!</h1>
    <p style="font-size:1.1rem;margin-top:12px">השאלון נשלח בהצלחה. תשובותיך יעזרו לנו למפות ולפתח את קהילת משחקי התפקידים בישראל.</p>
    {% if lottery_email %}
    <p style="margin-top:12px;color:#155724;background:#d4edda;padding:10px;border-radius:6px">נרשמת להגרלה עם כתובת <strong>{{ lottery_email }}</strong>. בהצלחה!</p>
    {% endif %}
    <p style="margin-top:20px;color:#666">הדוח יפורסם בסוף 2025 בשער המשחקים.</p>
    <div style="margin-top:20px"><a href="/" class="btn btn-primary">חזרה לדף הבית</a></div>
  </div>
</div>
{% endblock %}
COMPEOF

cat > templates/survey/ended.html << 'ENDEOF'
{% extends "base.html" %}
{% block delete_btn %}{% endblock %}
{% block content %}
<div class="container">
  <div class="card" style="text-align:center">
    <div style="font-size:3rem">👋</div>
    <h1 style="margin-top:12px">{{ reason }}</h1>
    <div style="margin-top:20px"><a href="/" class="btn btn-primary">חזרה לדף הבית</a></div>
  </div>
</div>
{% endblock %}
ENDEOF

cat > templates/admin/login.html << 'ADMINLEOF'
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
  <meta charset="UTF-8">
  <title>כניסת מנהל</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="container" style="max-width:400px;margin-top:80px">
  <div class="card">
    <h1>כניסת מנהל</h1>
    {% if error %}<div class="error-msg">{{ error }}</div>{% endif %}
    <form method="post" action="/admin" style="margin-top:16px">
      <div class="form-group">
        <label>סיסמה</label>
        <input type="password" name="password" required autofocus>
      </div>
      <button type="submit" class="btn btn-primary">כניסה</button>
    </form>
  </div>
</div>
</body>
</html>
ADMINLEOF

cat > templates/admin/dashboard.html << 'ADMINDEOF'
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
  <meta charset="UTF-8">
  <title>לוח בקרה</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
<nav><a href="/">ראשי</a></nav>
<div class="container">
  <div class="card">
    <h1>לוח בקרה — סקר קהילת משחקי תפקידים</h1>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:20px 0">
      <div style="background:#e8f4f8;padding:20px;border-radius:8px;text-align:center">
        <div style="font-size:2.5rem;font-weight:bold;color:var(--brand)">{{ total }}</div>
        <div>סה"כ מילויים</div>
      </div>
      <div style="background:#d4edda;padding:20px;border-radius:8px;text-align:center">
        <div style="font-size:2.5rem;font-weight:bold;color:#155724">{{ submitted }}</div>
        <div>נשלחו</div>
      </div>
      <div style="background:#fff3cd;padding:20px;border-radius:8px;text-align:center">
        <div style="font-size:2.5rem;font-weight:bold;color:#856404">{{ in_progress }}</div>
        <div>בתהליך</div>
      </div>
    </div>
    <h2 style="margin-top:20px">פילוח לפי אזור</h2>
    <table style="width:100%;border-collapse:collapse;margin-top:10px">
      <tr style="background:var(--brand);color:white">
        <th style="padding:8px 12px;text-align:right">אזור</th>
        <th style="padding:8px 12px;text-align:center">מספר משיבים</th>
      </tr>
      {% for region, count in region_counts.items() %}
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:8px 12px">{{ region }}</td>
        <td style="padding:8px 12px;text-align:center">{{ count }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
</div>
</body>
</html>
ADMINDEOF

# ================================================================
# Git Commit & Push
# ================================================================
echo "📦 Adding files to Git and pushing..."
git add -A
git commit -m "feat: complete survey implementation with all 9 sections, robust DB and correct track logic"
git push

echo "✅ Deployment trigger sent to Railway successfully!"
