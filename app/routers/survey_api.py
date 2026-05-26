import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.database import SessionLocal
from app.models.models import SurveySession, HashedTZ, Part1Basic, Part2General

router = APIRouter(prefix="/api/survey", tags=["survey"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_string(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

# מודל קבלת נתונים לחלק 1
class Part1Request(BaseModel):
    tz: str
    consent: bool
    birth_date: Optional[str] = None
    region: Optional[str] = None
    roles: List[str] = []

@router.post("/part1")
def submit_part1(data: Part1Request, request: Request, db: Session = Depends(get_db)):
    if not data.consent:
        raise HTTPException(status_code=400, detail="חובה לאשר השתתפות")

    tz_hash = hash_string(data.tz)
    
    # בדיקה האם ת.ז כבר קיימת (השתתפה בעבר)
    if db.query(HashedTZ).filter(HashedTZ.hashed_tz == tz_hash).first():
        raise HTTPException(status_code=400, detail="תעודת זהות זו כבר השתתפה בסקר. תודה!")

    # יצירת סשן מבוסס IP (הת.ז לא נשמרת עדיין למסד!)
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hash_string(client_ip)

    session_db = SurveySession(ip_hash=ip_hash)
    db.add(session_db)
    db.commit()
    db.refresh(session_db)

    # שמירת חלק 1
    part1_db = Part1Basic(
        session_id=session_db.id,
        consent=data.consent,
        region=data.region,
        roles=data.roles
        # אפשר להוסיף המרה מדויקת של תאריך הלידה כאן
    )
    db.add(part1_db)
    db.commit()

    # נחזיר את מזהה הסשן חזרה לדפדפן כדי שישתמש בו בחלקים הבאים
    return {"session_id": session_db.id, "tz_hash": tz_hash}

# מודל קבלת נתונים לחלק 2
class Part2Request(BaseModel):
    session_id: str
    years_familiar: str
    significance_level: int
    interested_types: List[str] = []

@router.post("/part2")
def submit_part2(data: Part2Request, db: Session = Depends(get_db)):
    # וידוא שהסשן קיים
    session_db = db.query(SurveySession).filter(SurveySession.id == data.session_id).first()
    if not session_db:
        raise HTTPException(status_code=404, detail="סשן לא נמצא")

    part2_db = Part2General(
        session_id=data.session_id,
        years_familiar=data.years_familiar,
        significance_level=data.significance_level,
        interested_types=data.interested_types
    )
    db.add(part2_db)
    db.commit()
    return {"status": "success"}

# כאן תוכל להוסיף את שאר החלקים (Part 3 עד 16) בדיוק באותה תבנית...
