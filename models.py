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
