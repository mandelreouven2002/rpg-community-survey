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
