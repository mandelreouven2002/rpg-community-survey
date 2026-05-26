import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.database import SessionLocal
from app.models.models import *

router = APIRouter(prefix="/api/survey", tags=["survey"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def hash_string(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

@router.post("/part1")
def submit_part1(data: Part1Request, request: Request, db: Session = Depends(get_db)):
    if not data.consent: raise HTTPException(status_code=400, detail="חובה לאשר השתתפות")
    
    # בדיקת חסימה מוחלטת מול מסד הנתונים
    tz_hash = hash_string(data.tz)
    if db.query(HashedTZ).filter(HashedTZ.hashed_tz == tz_hash).first():
        raise HTTPException(status_code=400, detail="תעודת זהות זו כבר השתתפה בסקר בעבר. תודה!")

    # יצירת סשן... (שאר הלוגיקה נשארת כפי שהייתה)
    # ...
    return {"session_id": "..."} 
