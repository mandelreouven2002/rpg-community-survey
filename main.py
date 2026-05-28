import csv
import hashlib
import io
import json
from datetime import datetime
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import SurveySession

app = FastAPI(title="RPG Community Survey", version="1.0.1")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SECTION_ORDER = [
    "section1",
    "section2",
    "section3",
    "section4",
    "section5",
    "section6",
    "section7",
    "section8",
    "section9",
]

SECTION_TITLES = {
    "section1": "פרטים בסיסיים",
    "section2": "היכרות כללית עם התחום",
    "section3": "משחק בפועל",
    "section4": "הנחיה וארגון משחקים",
    "section5": "שיטות משחק, סגנון ותוכן",
    "section6": "קהילה, אירועים וכנסים",
    "section7": "חסמים, צרכים והזדמנויות",
    "section8": "עסקים, חנויות, יוצרים ותוכן",
    "section9": "סיכום, מחקר והגרלה",
}

SECTION_QUESTIONS: dict[str, list[dict[str, Any]]] = {
    "section1": [
        {"name": "age_group", "label": "קבוצת גיל", "type": "radio", "required": True, "options": ["מתחת ל־14", "14–17", "18–24", "25–34", "35–44", "45–54", "55+", "מעדיף/ה לא לענות"]},
        {"name": "region", "label": "אזור מגורים", "type": "select", "required": True, "options": ["צפון", "חיפה והקריות", "השרון", "גוש דן", "תל אביב-יפו", "ירושלים והסביבה", "השפלה", "דרום", "יהודה ושומרון", "אילת והערבה", "גר/ה בחו״ל", "מעדיף/ה לא לענות"]},
        {"name": "city", "label": "עיר / יישוב", "type": "text", "required": False},
        {"name": "roles", "label": "מה הקשר שלך לתחום? אפשר לבחור כמה", "type": "checkbox", "required": True, "options": ["שחקן/ית שולחני/ת", "מנחה שולחני/ת", "משתתף/ת לארפים", "מארגן/ת לארפים", "הורה לילד/ה שמשחק/ת", "בעל/ת עסק / חנות", "יוצר/ת תוכן", "מתעניין/ת שטרם שיחק/ה", "שחקן/ית עבר"]},
        {"name": "other_hobbies", "label": "אילו תחביבים נוספים יש לך?", "type": "checkbox", "required": False, "options": ["משחקי לוח", "משחקי מחשב", "כתיבה", "קריאה", "קומיקס", "אנימה / מנגה", "מד״ב ופנטזיה", "תיאטרון / אימפרוביזציה", "יצירה / ציור", "אחר"]},
    ],
    "section2": [
        {"name": "years_in_field", "label": "כמה שנים את/ה מכיר/ה את תחום משחקי התפקידים?", "type": "radio", "required": True, "options": ["פחות משנה", "1–2 שנים", "3–5 שנים", "6–10 שנים", "11–20 שנים", "מעל 20 שנים", "לא בטוח/ה"]},
        {"name": "first_exposure", "label": "איך נחשפת לראשונה למשחקי תפקידים?", "type": "checkbox", "required": False, "options": ["חברים", "משפחה", "בית ספר", "חוג", "כנס", "חנות משחקים", "יוטיוב / פודקאסט / תוכן אונליין", "משחקי מחשב", "סדרות / סרטים / תרבות פופולרית", "צבא / שירות לאומי / לימודים", "רשתות חברתיות", "דיסקורד / קהילת אונליין", "אחר"]},
        {"name": "importance", "label": "עד כמה משחקי תפקידים הם חלק משמעותי מהחיים שלך?", "type": "scale", "required": True, "min": 1, "max": 5},
        {"name": "interest_types", "label": "אילו סוגי משחקי תפקידים מעניינים אותך?", "type": "checkbox", "required": False, "options": ["משחקים שולחניים", "לארפים", "משחקי ילדים ונוער", "משחקים טיפוליים / חינוכיים", "משחקים אונליין", "וואנשוטים", "קמפיינים ארוכים", "משחקים סיפוריים", "משחקים טקטיים", "משחקי אינדי", "מבוכים ודרקונים", "יצירת שיטות", "תרגום והוצאה לאור"]},
    ],
    "section3": [
        {"name": "play_frequency", "label": "באיזו תדירות את/ה משחק/ת?", "type": "radio", "required": True, "options": ["כמה פעמים בשבוע", "פעם בשבוע", "פעמיים בחודש", "פעם בחודש", "כמה פעמים בשנה", "כמעט לא", "לא משחק/ת כיום"]},
        {"name": "play_format", "label": "איך את/ה משחק/ת בדרך כלל?", "type": "checkbox", "required": False, "options": ["פרונטלי בבית", "פרונטלי במקום ציבורי", "אונליין", "כנסים", "חוגים", "מועדונים / מרכזי משחק", "אחר"]},
        {"name": "group_size", "label": "גודל קבוצה טיפוסי", "type": "radio", "required": False, "options": ["2–3", "4–5", "6–7", "8+", "משתנה מאוד"]},
        {"name": "campaign_length", "label": "אורך משחק טיפוסי", "type": "checkbox", "required": False, "options": ["וואנשוט", "מיני־קמפיין", "קמפיין של כמה חודשים", "קמפיין של שנה ומעלה", "משתנה"]},
        {"name": "paid_games", "label": "האם השתתפת במשחק בתשלום?", "type": "radio", "required": False, "options": ["כן", "לא", "שוקל/ת", "לא רלוונטי"]},
    ],
    "section4": [
        {"name": "gm_frequency", "label": "באיזו תדירות את/ה מנחה?", "type": "radio", "required": False, "options": ["כמה פעמים בשבוע", "פעם בשבוע", "פעמיים בחודש", "פעם בחודש", "כמה פעמים בשנה", "הנחיתי בעבר", "לא מנחה"]},
        {"name": "gm_contexts", "label": "באילו מסגרות הנחית?", "type": "checkbox", "required": False, "options": ["קבוצה פרטית", "חוג", "כנס", "בית ספר", "מרכז קהילתי", "אונליין", "בתשלום", "התנדבות", "לא הנחיתי"]},
        {"name": "gm_challenges", "label": "מה האתגרים המרכזיים בהנחיה?", "type": "checkbox", "required": False, "options": ["מציאת שחקנים", "תיאום זמנים", "הכנת תוכן", "ניהול קבוצה", "שחיקה", "חוסר ביטחון", "מחיר / ציוד", "מרחב מתאים", "אחר"]},
        {"name": "gm_training_interest", "label": "האם היית מעוניין/ת בהכשרה למנחים?", "type": "radio", "required": False, "options": ["כן מאוד", "אולי", "לא", "כבר עברתי הכשרה"]},
    ],
    "section5": [
        {"name": "systems_played", "label": "באילו שיטות שיחקת או הנחית?", "type": "checkbox", "required": False, "options": ["D&D 5e", "Pathfinder", "חרבות וכשפים", "עולמות פראיים", "Call of Cthulhu", "Powered by the Apocalypse", "Blades in the Dark", "Fate", "שיטות אינדי", "שיטה מקורית / ביתית", "אחר"]},
        {"name": "preferred_genres", "label": "ז׳אנרים מועדפים", "type": "checkbox", "required": False, "options": ["פנטזיה", "מדע בדיוני", "אימה", "חקירה / מסתורין", "גיבורי־על", "היסטורי", "קומדיה", "דרמה", "פוסט־אפוקליפסה", "אחר"]},
        {"name": "style_preferences", "label": "מה חשוב לך במשחק?", "type": "checkbox", "required": False, "options": ["סיפור", "קרבות", "חקירה", "דמויות", "עולם עשיר", "חוקים ברורים", "אלתור", "טקטיקה", "חוויה חברתית", "יצירתיות"]},
        {"name": "language_preference", "label": "באיזו שפה את/ה מעדיף/ה לשחק?", "type": "radio", "required": False, "options": ["עברית", "אנגלית", "גם וגם", "אין העדפה"]},
    ],
    "section6": [
        {"name": "community_channels", "label": "איפה את/ה צורך/ת מידע על התחום?", "type": "checkbox", "required": False, "options": ["פייסבוק", "וואטסאפ", "דיסקורד", "אינסטגרם", "יוטיוב", "אתרי אינטרנט", "חנויות", "כנסים", "חברים", "לא צורך/ת מידע"]},
        {"name": "events_attended", "label": "באילו אירועים השתתפת בשנה האחרונה?", "type": "checkbox", "required": False, "options": ["דרקוניקון", "אייקון", "ביגור", "כנס מקומי", "לארפ", "מפגש קהילה", "אירוע בחנות", "אירוע אונליין", "לא השתתפתי"]},
        {"name": "event_frequency", "label": "כמה פעמים בשנה את/ה מגיע/ה לכנסים או אירועים?", "type": "radio", "required": False, "options": ["0", "1", "2–3", "4–6", "7+"]},
        {"name": "abroad_events", "label": "האם השתתפת באירועי משחקי תפקידים בחו״ל?", "type": "radio", "required": False, "options": ["כן", "לא", "מתכנן/ת", "לא רלוונטי"]},
    ],
    "section7": [
        {"name": "barriers", "label": "מה מקשה על אנשים להיכנס לתחום?", "type": "checkbox", "required": False, "options": ["לא יודעים מאיפה להתחיל", "אין קבוצה", "אין מנחה", "חוסר זמן", "עלות", "מרחק גיאוגרפי", "חסם חברתי", "שפה", "מורכבות חוקים", "מחסור בתוכן בעברית", "אחר"]},
        {"name": "missing_resources", "label": "מה הכי חסר לקהילה?", "type": "checkbox", "required": False, "options": ["מאגר קבוצות", "לוח אירועים", "מדריכים למתחילים", "הכשרות מנחים", "תוכן בעברית", "מרחבי משחק", "פעילות לילדים ונוער", "פעילות בפריפריה", "תמיכה ליוצרים", "מחקר ונתונים"]},
        {"name": "growth_prediction", "label": "איך לדעתך התחום יתפתח בישראל בשלוש השנים הקרובות?", "type": "radio", "required": False, "options": ["יגדל מאוד", "יגדל מעט", "יישאר דומה", "יצטמצם", "לא יודע/ת"]},
        {"name": "open_needs", "label": "מה הדבר האחד שהכי יעזור לקהילה?", "type": "textarea", "required": False},
    ],
    "section8": [
        {"name": "buying_places", "label": "איפה את/ה קונה מוצרים או תוכן למשחקי תפקידים?", "type": "checkbox", "required": False, "options": ["חנויות בישראל", "חנויות בחו״ל", "DriveThruRPG / PDF", "Kickstarter / מימון המונים", "כנסים", "לא קונה", "אחר"]},
        {"name": "annual_spend", "label": "כמה בערך את/ה מוציא/ה בשנה על התחום?", "type": "radio", "required": False, "options": ["0 ₪", "1–100 ₪", "101–300 ₪", "301–700 ₪", "701–1500 ₪", "1500+ ₪", "מעדיף/ה לא לענות"]},
        {"name": "creator_status", "label": "האם את/ה יוצר/ת תוכן בתחום?", "type": "checkbox", "required": False, "options": ["כותב/ת הרפתקאות", "כותב/ת שיטה", "מתרגם/ת", "מאייר/ת / מעצב/ת", "יוצר/ת וידאו / פודקאסט", "מפיק/ת אירועים", "לא יוצר/ת תוכן"]},
        {"name": "business_needs", "label": "אם את/ה עסק/יוצר/ת — מה הכי חסר לך?", "type": "checkbox", "required": False, "options": ["חשיפה", "כלים שיווקיים", "קהילה", "מימון", "ידע עסקי", "שיתופי פעולה", "נתונים על השוק", "לא רלוונטי"]},
    ],
    "section9": [
        {"name": "recommendation_score", "label": "עד כמה היית ממליץ/ה לחבר/ה להיכנס לתחום?", "type": "scale", "required": False, "min": 1, "max": 10},
        {"name": "final_comment", "label": "עוד משהו שחשוב לך לומר?", "type": "textarea", "required": False},
        {"name": "join_updates", "label": "האם תרצה/י לקבל עדכון כשהדוח יתפרסם?", "type": "radio", "required": False, "options": ["כן", "לא"]},
        {"name": "lottery_email", "label": "מייל להגרלה / עדכונים. לא חובה. מומלץ לשמור בנפרד בניתוח.", "type": "email", "required": False},
    ],
}

MULTI_TYPES = {"checkbox"}

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def hash_ip(request: Request) -> str:
    raw = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    first_ip = raw.split(",")[0].strip()
    return hashlib.sha256(first_ip.encode("utf-8")).hexdigest()

def render(request: Request, template: str, **context):
    context["request"] = request
    return templates.TemplateResponse(template, context)

def get_session(db: Session, session_id: str | None) -> SurveySession | None:
    if not session_id:
        return None
    return db.query(SurveySession).filter(SurveySession.id == session_id).first()

def parse_json(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback

def section_index(section: str) -> int:
    return SECTION_ORDER.index(section)

def next_section(section: str) -> str | None:
    i = section_index(section)
    if i + 1 >= len(SECTION_ORDER):
        return None
    return SECTION_ORDER[i + 1]

def previous_section(section: str) -> str | None:
    i = section_index(section)
    if i == 0:
        return None
    return SECTION_ORDER[i - 1]

def serialize_form(form, questions: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for q in questions:
        name = q["name"]
        if q.get("type") in MULTI_TYPES:
            output[name] = form.getlist(name)
        else:
            output[name] = str(form.get(name, "")).strip()
    output["_saved_at"] = now_iso()
    return output

def validate_section(data: dict[str, Any], questions: list[dict[str, Any]]) -> str | None:
    for q in questions:
        if not q.get("required"):
            continue
        name = q["name"]
        val = data.get(name)
        if isinstance(val, list):
            if len(val) == 0:
                return f"נא לענות על השאלה: {q['label']}"
        elif val is None or str(val).strip() == "":
            return f"נא לענות על השאלה: {q['label']}"
    return None

def ensure_schema():
    """
    create_all() creates missing tables but does not add columns to an existing table.
    This fixes old deployed DBs that are missing columns such as updated_at.
    """
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    if "survey_sessions" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("survey_sessions")}
    required_columns = {
        "ip_hash": "VARCHAR(64)",
        "is_submitted": "BOOLEAN DEFAULT FALSE",
        "current_section": "VARCHAR(20)",
        "section1": "TEXT",
        "section2": "TEXT",
        "section3": "TEXT",
        "section4": "TEXT",
        "section5": "TEXT",
        "section6": "TEXT",
        "section7": "TEXT",
        "section8": "TEXT",
        "section9": "TEXT",
        "active_sections": "TEXT",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    }

    with engine.begin() as conn:
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                conn.execute(text(f"ALTER TABLE survey_sessions ADD COLUMN {column_name} {column_type}"))

@app.on_event("startup")
def startup():
    ensure_schema()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "home.html")

@app.get("/health")
def health():
    return {"ok": True, "service": "rpg-community-survey"}

@app.get("/survey", response_class=HTMLResponse)
def consent_get(request: Request):
    return render(request, "survey/consent.html")

@app.post("/survey/consent")
async def consent_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    consent = form.get("consent")

    if consent != "yes":
        return RedirectResponse("/", status_code=303)

    sess = SurveySession(
        ip_hash=hash_ip(request),
        current_section="section1",
        active_sections=json.dumps(SECTION_ORDER, ensure_ascii=False),
    )
    db.add(sess)
    db.commit()

    response = RedirectResponse("/survey/section1", status_code=303)
    response.set_cookie("session_id", sess.id, httponly=True, samesite="lax")
    return response

@app.get("/survey/demographics")
def old_demographics_get():
    return RedirectResponse("/survey/section1", status_code=303)

@app.post("/survey/demographics")
def old_demographics_post():
    return RedirectResponse("/survey/section1", status_code=303)

@app.get("/admin/export.csv")
def export_csv(db: Session = Depends(get_db)):
    rows = db.query(SurveySession).order_by(SurveySession.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)

    headers = ["id", "is_submitted", "created_at", "updated_at", "current_section"]
    for sec in SECTION_ORDER:
        for q in SECTION_QUESTIONS[sec]:
            headers.append(q["name"])
    writer.writerow(headers)

    for sess in rows:
        row = [
            sess.id,
            sess.is_submitted,
            sess.created_at.isoformat() if sess.created_at else "",
            sess.updated_at.isoformat() if sess.updated_at else "",
            sess.current_section,
        ]

        merged = {}
        for sec in SECTION_ORDER:
            merged.update(parse_json(getattr(sess, sec), {}))

        for sec in SECTION_ORDER:
            for q in SECTION_QUESTIONS[sec]:
                val = merged.get(q["name"], "")
                if isinstance(val, list):
                    val = " | ".join(val)
                row.append(val)
        writer.writerow(row)

    buffer.seek(0)
    filename = f"rpg-community-survey-{datetime.utcnow().date().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@app.get("/survey/submit", response_class=HTMLResponse)
def submit_get(request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    sections = {}
    for sec in SECTION_ORDER:
        sections[SECTION_TITLES[sec]] = parse_json(getattr(sess, sec), {})

    return render(request, "survey/submit.html", sections=sections)

@app.post("/survey/submit")
def submit_post(request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    sess.is_submitted = True
    sess.current_section = "complete"
    sess.updated_at = datetime.utcnow()
    db.commit()

    response = RedirectResponse("/survey/complete", status_code=303)
    response.delete_cookie("session_id")
    return response

@app.get("/survey/complete", response_class=HTMLResponse)
def complete_get(request: Request):
    return render(request, "survey/complete.html")

@app.post("/survey/delete")
def delete_my_data(session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    if sess:
        db.delete(sess)
        db.commit()

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session_id")
    return response

@app.get("/survey/{section}", response_class=HTMLResponse)
def section_get(section: str, request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    if section not in SECTION_ORDER:
        return RedirectResponse("/survey", status_code=303)

    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    stored = parse_json(getattr(sess, section), {})
    progress = int(((section_index(section) + 1) / len(SECTION_ORDER)) * 100)

    return render(
        request,
        "survey/section.html",
        section=section,
        title=SECTION_TITLES[section],
        questions=SECTION_QUESTIONS[section],
        data=stored,
        progress=progress,
        previous=previous_section(section),
    )

@app.post("/survey/{section}")
async def section_post(section: str, request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    if section not in SECTION_ORDER:
        return RedirectResponse("/survey", status_code=303)

    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    form = await request.form()
    data = serialize_form(form, SECTION_QUESTIONS[section])
    error = validate_section(data, SECTION_QUESTIONS[section])

    if error:
        progress = int(((section_index(section) + 1) / len(SECTION_ORDER)) * 100)
        return render(
            request,
            "survey/section.html",
            section=section,
            title=SECTION_TITLES[section],
            questions=SECTION_QUESTIONS[section],
            data=data,
            progress=progress,
            previous=previous_section(section),
            error=error,
        )

    setattr(sess, section, json.dumps(data, ensure_ascii=False))
    nxt = next_section(section)
    sess.current_section = nxt or "submit"
    sess.updated_at = datetime.utcnow()
    db.commit()

    if nxt:
        return RedirectResponse(f"/survey/{nxt}", status_code=303)

    return RedirectResponse("/survey/submit", status_code=303)
