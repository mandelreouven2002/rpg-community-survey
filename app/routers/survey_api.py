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

# ==================== מודלים לקבלת נתונים ====================
class Part1Request(BaseModel): tz: str; consent: bool; region: Optional[str] = None; roles: List[str] = []
class Part2Request(BaseModel): session_id: str; years_familiar: Optional[str] = None; significance_level: Optional[int] = None; interested_types: List[str] = []
class Part3Request(BaseModel): session_id: str; play_currently: Optional[str] = None; frequency: Optional[str] = None; frameworks: List[str] = []; locations: Optional[str] = None; online_vs_physical: Optional[str] = None; online_tools: List[str] = []; systems_played: List[str] = []; favorite_genres: List[str] = []; active_groups: Optional[str] = None; group_size: Optional[str] = None; session_length: Optional[str] = None; player_challenges: List[str] = []
class Part4Request(BaseModel): session_id: str; gm_currently: Optional[str] = None; gm_years: Optional[str] = None; gm_frameworks: List[str] = []; paid_gm: Optional[str] = None; paid_services: List[str] = []; paid_price_range: Optional[str] = None; paid_by_who: List[str] = []; want_more_paid: Optional[str] = None; gm_challenges: List[str] = []; desired_training: List[str] = []
class Part5Request(BaseModel): session_id: str; larp_last_year: Optional[str] = None; larp_count: Optional[str] = None; larp_types: List[str] = []; barriers: List[str] = []; want_more_larps: Optional[str] = None
class Part6Request(BaseModel): session_id: str; attended_con: Optional[str] = None; con_names: List[str] = []; con_frequency: Optional[str] = None; why_attend: List[str] = []; barriers: List[str] = []; important_elements: Dict[str, int] = {}; abroad_cons: Optional[str] = None; abroad_con_names: Optional[str] = None
class Part7Request(BaseModel): session_id: str; visited_store: Optional[str] = None; store_frequency: Optional[str] = None; why_store: List[str] = []; where_buy: List[str] = []; money_spent: Optional[str] = None; what_bought: List[str] = []
class Part8Request(BaseModel): session_id: str; has_kids: Optional[str] = None; kids_play: Optional[str] = None; frameworks: List[str] = []; kids_ages: List[str] = []; positive_activity: Optional[int] = None; core_value: List[str] = []; concerns: List[str] = []; willing_to_pay: Optional[str] = None; family_players: Optional[str] = None
class Part9Request(BaseModel): session_id: str; barriers_to_start: List[str] = []; what_would_help: List[str] = []; preferred_framework: Optional[str] = None
class Part10Request(BaseModel): session_id: str; when_stopped: Optional[str] = None; why_stopped: List[str] = []; what_brings_back: List[str] = []
class Part11Request(BaseModel): session_id: str; belonging_level: Optional[int] = None; where_is_community: List[str] = []; welcoming_level: Optional[int] = None; underserved_groups: List[str] = []; bad_experience: Optional[str] = None; bad_experience_type: Optional[str] = None
class Part12Request(BaseModel): session_id: str; other_hobbies: List[str] = []; other_communities: List[str] = []; leisure_hours: Optional[str] = None
class Part13Request(BaseModel): session_id: str; status: Optional[str] = None; field: List[str] = []; connection_to_hobby: Optional[str] = None; connection_details: Optional[str] = None
class Part14Request(BaseModel): session_id: str; created_content: List[str] = []; published_content: Optional[str] = None; barriers: List[str] = []; want_hebrew_content: Optional[int] = None; missing_content: List[str] = []
class Part15Request(BaseModel): session_id: str; business_type: List[str] = []; target_audience: List[str] = []; challenges: List[str] = []; growth_helpers: List[str] = []
class Part16Request(BaseModel): session_id: str; missing_thing_1: Optional[str] = None; missing_thing_2: Optional[str] = None; missing_thing_3: Optional[str] = None; helpful_projects: List[str] = []; growth_perception: Optional[str] = None; what_brings_new_people: List[str] = []; nps_score: Optional[int] = None; one_sentence_value: Optional[str] = None

# ==================== נתיבי שמירה ====================

@router.post("/part1")
def submit_part1(data: Part1Request, request: Request, db: Session = Depends(get_db)):
    if not data.consent: raise HTTPException(status_code=400, detail="חובה לאשר השתתפות")
    tz_hash = hash_string(data.tz)
    if db.query(HashedTZ).filter(HashedTZ.hashed_tz == tz_hash).first():
        raise HTTPException(status_code=400, detail="תעודת זהות זו כבר השתתפה בסקר.")

    ip_hash = hash_string(request.client.host if request.client else "unknown")
    session_db = SurveySession(ip_hash=ip_hash)
    db.add(session_db)
    db.commit()
    db.refresh(session_db)

    part1_db = Part1Basic(session_id=session_db.id, consent=data.consent, region=data.region, roles=data.roles)
    db.add(part1_db)
    db.commit()
    return {"session_id": session_db.id, "tz_hash": tz_hash}

# פונקציית עזר גנרית לשמירת שאר החלקים
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
@router.post("/part4")
def submit_part4(data: Part4Request, db: Session = Depends(get_db)): return save_part(db, Part4GMs, data.dict())
@router.post("/part5")
def submit_part5(data: Part5Request, db: Session = Depends(get_db)): return save_part(db, Part5Larps, data.dict())
@router.post("/part6")
def submit_part6(data: Part6Request, db: Session = Depends(get_db)): return save_part(db, Part6Conventions, data.dict())
@router.post("/part7")
def submit_part7(data: Part7Request, db: Session = Depends(get_db)): return save_part(db, Part7Stores, data.dict())
@router.post("/part8")
def submit_part8(data: Part8Request, db: Session = Depends(get_db)): return save_part(db, Part8Parents, data.dict())
@router.post("/part9")
def submit_part9(data: Part9Request, db: Session = Depends(get_db)): return save_part(db, Part9Barriers, data.dict())
@router.post("/part10")
def submit_part10(data: Part10Request, db: Session = Depends(get_db)): return save_part(db, Part10Former, data.dict())
@router.post("/part11")
def submit_part11(data: Part11Request, db: Session = Depends(get_db)): return save_part(db, Part11Community, data.dict())
@router.post("/part12")
def submit_part12(data: Part12Request, db: Session = Depends(get_db)): return save_part(db, Part12Hobbies, data.dict())
@router.post("/part13")
def submit_part13(data: Part13Request, db: Session = Depends(get_db)): return save_part(db, Part13WorkStudy, data.dict())
@router.post("/part14")
def submit_part14(data: Part14Request, db: Session = Depends(get_db)): return save_part(db, Part14Creation, data.dict())
@router.post("/part15")
def submit_part15(data: Part15Request, db: Session = Depends(get_db)): return save_part(db, Part15Business, data.dict())

@router.post("/part16")
def submit_part16(data: Part16Request, db: Session = Depends(get_db)):
    # זהו החלק האחרון! נעדכן את הסטטוס ל"נשלח בהצלחה" וננעל את הסשן
    session_db = db.query(SurveySession).filter(SurveySession.id == data.session_id).first()
    if session_db:
        session_db.is_submitted = True
        db.commit()
    return save_part(db, Part16Vision, data.dict())


# ==================== זיכרון IP ואיפוס ====================

@router.get("/status")
def check_status(request: Request, db: Session = Depends(get_db)):
    ip_hash = hash_string(request.client.host if request.client else "unknown")
    # מחפש סשן פתוח שטרם נשלח סופית
    session = db.query(SurveySession).filter(SurveySession.ip_hash == ip_hash, SurveySession.is_submitted == False).first()
    
    if not session:
        return {"exists": False}
        
    # אם יש סשן, נשלוף את התפקידים שנבחרו בחלק 1 כדי שה-JS יידע לשחזר את המסלול
    part1 = db.query(Part1Basic).filter(Part1Basic.session_id == session.id).first()
    if not part1:
        return {"exists": False}
        
    # בדיקה מהירה לאיזה חלק המשתמש הגיע לאחרונה
    last_part = 1
    if session.part2: last_part = 2
    if session.part3: last_part = 3
    if session.part4: last_part = 4
    if session.part5: last_part = 5
    if session.part6: last_part = 6
    if session.part7: last_part = 7
    if session.part8: last_part = 8
    if session.part9: last_part = 9
    if session.part10: last_part = 10
    if session.part11: last_part = 11
    if session.part12: last_part = 12
    if session.part13: last_part = 13
    if session.part14: last_part = 14
    if session.part15: last_part = 15

    return {
        "exists": True, 
        "session_id": session.id, 
        "roles": part1.roles, 
        "last_part": last_part
    }

@router.delete("/reset")
def reset_survey(request: Request, db: Session = Depends(get_db)):
    ip_hash = hash_string(request.client.host if request.client else "unknown")
    session = db.query(SurveySession).filter(SurveySession.ip_hash == ip_hash, SurveySession.is_submitted == False).first()
    
    if session:
        # פקודת המחיקה הזו תמחק אוטומטית (Cascade) גם את כל התשובות 
        # המקושרות לסשן הזה בכל 16 הטבלאות האחרות!
        db.delete(session)
        db.commit()
        return {"status": "deleted"}
    return {"status": "not_found"}
