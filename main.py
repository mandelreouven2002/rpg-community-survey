from fastapi import FastAPI, Request, Cookie, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import engine, Base, get_db, SessionLocal
from models import SurveySession
import json

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup(): Base.metadata.create_all(bind=engine)

def render(req, name, **kwargs):
    kwargs["request"] = req
    return templates.TemplateResponse(name=name, context=kwargs)

@app.get("/", response_class=HTMLResponse)
def home(req: Request): return render(req, "home.html")

@app.get("/survey", response_class=HTMLResponse)
def survey(req: Request, db: Session = Depends(get_db)):
    return render(req, "survey/consent.html")

@app.post("/survey/consent")
def consent(consent: str = Form(...)):
    if consent == "yes": return RedirectResponse("/survey/demographics", 303)
    return RedirectResponse("/", 303)

@app.get("/survey/demographics", response_class=HTMLResponse)
def demog_get(req: Request): return render(req, "survey/demographics.html")

@app.post("/survey/demographics")
def demog_post(req: Request, roles: list = Form(...), db: Session = Depends(get_db)):
    sess = SurveySession(section1=json.dumps({"roles": roles}), active_sections=json.dumps(["section2"]))
    db.add(sess)
    db.commit()
    resp = RedirectResponse("/survey/section2", 303)
    resp.set_cookie("session_id", sess.id)
    return resp

@app.get("/survey/section2", response_class=HTMLResponse)
def s2_get(req: Request, session_id: str = Cookie(None), db: Session = Depends(get_db)):
    return render(req, "survey/section2.html", active=["section2"])

@app.post("/survey/section2")
def s2_post(req: Request, session_id: str = Cookie(None), db: Session = Depends(get_db)):
    return RedirectResponse("/survey/submit", 303)

@app.get("/survey/submit", response_class=HTMLResponse)
def submit_get(req: Request): return render(req, "survey/submit.html")

@app.post("/survey/submit")
def submit_post(session_id: str = Cookie(None), db: Session = Depends(get_db)):
    sess = db.query(SurveySession).filter_by(id=session_id).first()
    if sess: sess.is_submitted = True; db.commit()
    return render(None, "survey/complete.html")
