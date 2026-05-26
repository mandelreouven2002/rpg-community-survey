import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from app.database import SessionLocal
from app.models.models import *

router = APIRouter(prefix="/api/survey", tags=["survey"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_string(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

# ==================== מודלים ====================
class Part1Request(BaseModel): tz: str; consent: bool; region: Optional[str] = None; city: Optional[str] = None; roles: List[str] = []
class Part2Request(BaseModel): session_id: str; years_familiar: Optional[str] = None; first_exposure: List[str] = []; significance_level: Optional[int] = None; interested_types: List[str] = []
class Part3Request(BaseModel): session_id: str; play_currently: Optional[str] = None; frequency: Optional[str] = None; frameworks: List[str] = []; locations: Optional[str] = None; online_vs_physical: Optional[str] = None; online_tools: List[str] = []; systems_played: List[str] = []; favorite_genres: List[str] = []; active_groups: Optional[str] = None; group_size: Optional[str] = None; session_length: Optional[str] = None; player_challenges: List[str] = []
class Part16Request(BaseModel): session_id: str; tz: str; missing_thing_1: Optional[str] = None; missing_thing_2: Optional[str] = None; missing_thing_3: Optional[str] = None; helpful_projects: List[str] = []; growth_perception: Optional[str] = None; what_brings_new_people: List[str] = []; nps_score: Optional[int] = None; one_sentence_value: Optional[str] = None

# ==================== ניהול נתונים ====================

@router.post("/part1")
def submit_part1(data: Part1Request, request: Request, db: Session = Depends(get_db)):
    if not data.consent: raise HTTPException(status_code=400, detail="חובה לאשר השתתפות")
    tz_hash = hash_string(data.tz)
    
    # חסימה: בדיקה האם ה-ID קיימת במאגר הראשי (נרשמה בסיום שאלון)
    if db.query(HashedTZ).filter(HashedTZ.hashed_tz == tz_hash).first():
        raise HTTPException(status_code=400, detail="נעשה שימוש בתעודת הזהות הנ״ל. המערכת חוסמת כפילויות.")

    ip_hash = hash_string(request.client.host if request.client else "unknown")
    session_db = SurveySession(ip_hash=ip_hash)
    db.add(session_db)
    db.commit()
    db.refresh(session_db)

    part1_db = Part1Basic(session_id=session_db.id, consent=data.consent, region=data.region, city=data.city, roles=data.roles)
    db.add(part1_db)
    db.commit()
    return {"session_id": session_db.id}

def save_part(db: Session, model_class, data_dict: dict):
    session_id = data_dict.pop("session_id")
    session_db = db.query(SurveySession).filter(SurveySession.id == session_id).first()
    if not session_db: raise HTTPException(status_code=404, detail="Session not found")
    part_db = model_class(session_id=session_id, **data_dict)
    db.add(part_db)
    db.commit()
    return {"status": "success"}

@router.post("/part2")
def submit_part2(data: Part2Request, db: Session = Depends(get_db)): return save_part(db, Part2General, data.dict())
@router.post("/part3")
def submit_part3(data: Part3Request, db: Session = Depends(get_db)): return save_part(db, Part3Tabletop, data.dict())

@router.post("/part16")
def submit_part16(data: Part16Request, db: Session = Depends(get_db)):
    # 1. נעילת הסשן
    session_db = db.query(SurveySession).filter(SurveySession.id == data.session_id).first()
    if session_db:
        session_db.is_submitted = True
        db.commit()

    # 2. שמירת תעודת הזהות למאגר הנעול כדי למנוע שימוש חוזר!
    tz_hash = hash_string(data.tz)
    if not db.query(HashedTZ).filter(HashedTZ.hashed_tz == tz_hash).first():
        db.add(HashedTZ(hashed_tz=tz_hash))
        db.commit()

    data_dict = data.dict()
    data_dict.pop("tz") # מסירים את הת.ז כדי שלא תישמר בטבלת התשובות של חלק 16
    return save_part(db, Part16Vision, data_dict)


# ==================== סטטוס ואיפוס (זיכרון) ====================
@router.get("/status")
def check_status(request: Request, db: Session = Depends(get_db)):
    ip_hash = hash_string(request.client.host if request.client else "unknown")
    session = db.query(SurveySession).filter(SurveySession.ip_hash == ip_hash, SurveySession.is_submitted == False).first()
    if not session: return {"exists": False}
    part1 = db.query(Part1Basic).filter(Part1Basic.session_id == session.id).first()
    if not part1: return {"exists": False}
    
    last_part = 1
    if session.part2: last_part = 2
    if session.part3: last_part = 3
    return {"exists": True, "session_id": session.id, "roles": part1.roles, "last_part": last_part}

@router.delete("/reset")
def reset_survey(request: Request, db: Session = Depends(get_db)):
    ip_hash = hash_string(request.client.host if request.client else "unknown")
    session = db.query(SurveySession).filter(SurveySession.ip_hash == ip_hash, SurveySession.is_submitted == False).first()
    if session:
        db.delete(session)
        db.commit()
        return {"status": "deleted"}
    return {"status": "not_found"}
