import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, String, Text
from database import Base

class SurveySession(Base):
    __tablename__ = "survey_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ip_hash = Column(String(64), nullable=False)
    survey_type = Column(String(10), nullable=True)
    submitted = Column(Boolean, default=False)
    is_submitted = Column(Boolean, default=False)
    current_section = Column(String(20), default="part1")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    active_sections = Column(Text, nullable=True)

    # Legacy compatibility columns from the existing DB.
    section1 = Column(Text, nullable=True)
    section2 = Column(Text, nullable=True)
    section3 = Column(Text, nullable=True)
    section4 = Column(Text, nullable=True)
    section5 = Column(Text, nullable=True)
    section6 = Column(Text, nullable=True)
    section7 = Column(Text, nullable=True)
    section8 = Column(Text, nullable=True)
    section9 = Column(Text, nullable=True)
