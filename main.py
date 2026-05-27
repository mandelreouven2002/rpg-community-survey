import os, json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import engine, get_db, Base, SessionLocal
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

# ==========================================
# פונקציות עזר - חסינות לתקלות גרסה וזיהוי ענן
# ==========================================
def render(request: Request, name: str, **kwargs):
    """
    פונקציית עזר שפותרת את שגיאת ה-500 בגרסאות החדשות של FastAPI
    """
    kwargs["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=kwargs)

def get_client_ip(request: Request) -> str:
    """זיהוי IP אמיתי גם מאחורי ה-Load Balancer של Railway"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        db.query(SurveySession).filter(
            SurveySession.is_submitted == False,
            SurveySession.created_at < cutoff
        ).delete()
        db.commit()
    finally:
        db.close()

def _get_session(request: Request, db: Session, session_id: Optional[str]) -> Optional[SurveySession]:
    ip_hash = hash_ip(get_client_ip(request))
    if session_id:
        s = db.query(SurveySession).filter_by(id=session_id, is_submitted=False).first()
        if s:
            return s
    return db.query(SurveySession).filter_by(ip_hash=ip_hash, is_submitted=False)\
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
    return render(request, "home.html")

@app.get("/survey", response_class=HTMLResponse)
def survey_start(request: Request,
                 session_id: Optional[str] = Cookie(default=None),
                 db: Session = Depends(get_db)):
    existing = _get_session(request, db, session_id)
    if existing and existing.section1:
        return render(request, "survey/resume.html", session=existing, SECTION_LABELS=SECTION_LABELS)
    return render(request, "survey/consent.html")

@app.post("/survey/consent")
async def survey_consent(request: Request, consent: str = Form(...)):
    if consent != "yes":
        return render(request, "survey/ended.html", reason="תודה על הזמן שלך. השאלון הסתיים.")
    return RedirectResponse("/survey/identity", status_code=303)

@app.get("/survey/identity", response_class=HTMLResponse)
def identity_form(request: Request):
    return render(request, "survey/identity.html", error=None)

@app.post("/survey/identity")
async def identity_submit(request: Request, id_number: str = Form(...),
                          db: Session = Depends(get_db)):
    id_number = id_number.strip()
    if not validate_israeli_id(id_number):
        return render(request, "survey/identity.html", error="מספר תעודת הזהות אינו תקין. אנא בדוק/י ונסה/י שוב.")
    hashed = hash_value(id_number.zfill(9))
    if db.query(IdHash).filter_by(id_hash=hashed).first():
        return render(request, "survey/identity.html", error="תעודת זהות זו כבר שימשה למילוי השאלון. לא ניתן למלא יותר מפעם אחת.")
    resp = RedirectResponse("/survey/demographics", status_code=303)
    resp.set_cookie("pending_id_hash", hashed, httponly=True, max_age=3600)
    return resp

@app.get("/survey/demographics", response_class=HTMLResponse)
def demographics_form(request: Request):
    return render(request, "survey/demographics.html", error=None)

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
            return render(request, "survey/ended.html", reason="השאלון מיועד לבני 13 ומעלה. תודה על הזמן שלך.")
    if not roles:
        return render(request, "survey/demographics.html", error="אנא בחר/י לפחות תפקיד אחד.")

    active = determine_active_sections(roles)
    s1 = json.dumps({"dob": dob, "dob_prefer_not": bool(dob_prefer_not),
                     "region": region, "city": city, "roles": roles}, ensure_ascii=False)
    ip_hash = hash_ip(get_client_ip(request))

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
    return render(request, "survey/choose_version.html", num_sections=len(active))

@app.post("/survey/choose-version")
async def choose_version_submit(request: Request, version: str = Form(...),
                                 session_id: Optional[str] = Cookie(default=None),
                                 db: Session = Depends(get_db)):
    sess = _get_session(request, db, session_id)
    if not sess:
        return RedirectResponse("/survey")
    
    sess.survey_type = version
    active = json.loads(sess.active_sections or "[]")
    
    if version == "short":
        sections_to_remove = ["section7", "section9"] 
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
        return render(request, f"survey/section{num}.html", session=sess,
            data=json.loads(getattr(sess, f"section{num}") or "{}"),
            active=json.loads(sess.active_sections or "[]"),
            SECTION_LABELS=SECTION_LABELS)

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
    return render(request, "survey/submit.html", session=sess, active=json.loads(sess.active_sections or "[]"), SECTION_LABELS=SECTION_LABELS)

@app.post("/survey/submit")
async def submit_post(request: Request, lottery_email: Optional[str] = Form(default=None),
                      session_id: Optional[str] = Cookie(default=None),
                      pending_id_hash: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    sess, r = _require(request, db, session_id)
    if r: return r
    if pending_id_hash and not db.query(IdHash).filter_by(id_hash=pending_id_hash).first():
        db.add(IdHash(id_hash=pending_id_hash))
    sess.is_submitted = True
    sess.updated_at = datetime.utcnow()
    db.commit()
    resp = render(request, "survey/complete.html", lottery_email=lottery_email)
    resp.delete_cookie("session_id")
    resp.delete_cookie("pending_id_hash")
    return resp

@app.post("/survey/delete")
async def delete_survey(request: Request, db: Session = Depends(get_db)):
    ip_hash = hash_ip(get_client_ip(request))
    for s in db.query(SurveySession).filter_by(ip_hash=ip_hash).all():
        db.delete(s)
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_id")
    resp.delete_cookie("pending_id_hash")
    return resp

@app.post("/survey/resume")
async def resume(request: Request, action: str = Form(...), session_id: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    ip_hash = hash_ip(get_client_ip(request))
    if action == "new":
        for s in db.query(SurveySession).filter_by(ip_hash=ip_hash, is_submitted=False).all():
            db.delete(s)
        db.commit()
        resp = RedirectResponse("/survey", status_code=303)
        resp.delete_cookie("session_id")
        return resp
    sess = db.query(SurveySession).filter_by(ip_hash=ip_hash, is_submitted=False).order_by(SurveySession.created_at.desc()).first()
    if sess:
        return RedirectResponse(f"/survey/{sess.current_section or 'section2'}", status_code=303)
    return RedirectResponse("/survey", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
def admin_login(request: Request):
    return render(request, "admin/login.html", error=None)

@app.post("/admin", response_class=HTMLResponse)
async def admin_post(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    if password != ADMIN_PASSWORD:
        return render(request, "admin/login.html", error="סיסמה שגויה")
    total     = db.query(SurveySession).count()
    submitted = db.query(SurveySession).filter_by(is_submitted=True).count()
    sessions  = db.query(SurveySession).filter_by(is_submitted=True).all()
    region_counts = {}
    for s in sessions:
        if s.section1:
            r = json.loads(s.section1).get("region", "לא ידוע")
            region_counts[r] = region_counts.get(r, 0) + 1
    return render(request, "admin/dashboard.html", total=total, submitted=submitted, in_progress=total-submitted, region_counts=region_counts)
