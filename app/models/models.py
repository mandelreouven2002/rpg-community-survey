from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from datetime import datetime
from app.database import Base

class HashedID(Base):
    __tablename__ = "hashed_ids"
    id = Column(Integer, primary_key=True, index=True)
    hashed_tz = Column(String, unique=True, index=True) # Used ONLY to check if ID exists
    created_at = Column(DateTime, default=datetime.utcnow)

class SurveyAnswer(Base):
    __tablename__ = "survey_answers"
    id = Column(String, primary_key=True, index=True) # Unique ID for the session
    ip_address_hashed = Column(String, index=True)
    survey_type = Column(String) # "short" or "extended"
    is_submitted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Answers Data (Can be JSON or related tables)
    # Storing structured JSON is often best for complex conditional surveys
    responses_json = Column(String, default="{}")
