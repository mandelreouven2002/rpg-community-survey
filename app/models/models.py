import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from app.database import Base

# ==========================================
# 1. מנגנוני אבטחה וניהול סשן
# ==========================================

class HashedTZ(Base):
    __tablename__ = "hashed_tzs"
    id = Column(Integer, primary_key=True, index=True)
    hashed_tz = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class RaffleEmail(Base):
    __tablename__ = "raffle_emails"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    want_updates = Column(Boolean, default=False)
    want_raffle = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class SurveySession(Base):
    __tablename__ = "survey_sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    ip_hash = Column(String, index=True)
    survey_type = Column(String, nullable=True) # 'short' or 'extended'
    is_submitted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # קשרים לטבלאות החלקים
    part1 = relationship("Part1Basic", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part2 = relationship("Part2General", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part3 = relationship("Part3Tabletop", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part4 = relationship("Part4GMs", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part5 = relationship("Part5Larps", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part6 = relationship("Part6Conventions", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part7 = relationship("Part7Stores", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part8 = relationship("Part8Parents", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part9 = relationship("Part9Barriers", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part10 = relationship("Part10Former", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part11 = relationship("Part11Community", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part12 = relationship("Part12Hobbies", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part13 = relationship("Part13WorkStudy", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part14 = relationship("Part14Creation", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part15 = relationship("Part15Business", back_populates="session", uselist=False, cascade="all, delete-orphan")
    part16 = relationship("Part16Vision", back_populates="session", uselist=False, cascade="all, delete-orphan")


# ==========================================
# 2. חלקי השאלון
# ==========================================

class Part1Basic(Base):
    __tablename__ = "part1_basic"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    consent = Column(Boolean, nullable=False)
    birth_date = Column(Date)
    region = Column(String)
    city = Column(String, nullable=True)
    roles = Column(JSON) # מערך תפקידים: שחקן, מנחה, הורה וכו'
    session = relationship("SurveySession", back_populates="part1")

class Part2General(Base):
    __tablename__ = "part2_general"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    years_familiar = Column(String)
    first_exposure = Column(JSON)
    significance_level = Column(Integer) # 1-5
    interested_types = Column(JSON)
    session = relationship("SurveySession", back_populates="part2")

class Part3Tabletop(Base):
    __tablename__ = "part3_tabletop"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    play_currently = Column(String)
    frequency = Column(String)
    frameworks = Column(JSON)
    locations = Column(String)
    online_vs_physical = Column(String)
    online_tools = Column(JSON)
    systems_played = Column(JSON)
    favorite_genres = Column(JSON)
    active_groups = Column(String)
    group_size = Column(String)
    session_length = Column(String)
    player_challenges = Column(JSON)
    session = relationship("SurveySession", back_populates="part3")

class Part4GMs(Base):
    __tablename__ = "part4_gms"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    gm_currently = Column(String)
    gm_years = Column(String)
    gm_frameworks = Column(JSON)
    paid_gm = Column(String)
    paid_services = Column(JSON)
    paid_price_range = Column(String)
    paid_by_who = Column(JSON)
    want_more_paid = Column(String)
    gm_challenges = Column(JSON)
    desired_training = Column(JSON)
    session = relationship("SurveySession", back_populates="part4")

class Part5Larps(Base):
    __tablename__ = "part5_larps"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    larp_last_year = Column(String)
    larp_count = Column(String)
    larp_types = Column(JSON)
    barriers = Column(JSON)
    want_more_larps = Column(String)
    session = relationship("SurveySession", back_populates="part5")

class Part6Conventions(Base):
    __tablename__ = "part6_conventions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    attended_con = Column(String)
    con_names = Column(JSON)
    con_frequency = Column(String)
    why_attend = Column(JSON)
    barriers = Column(JSON)
    important_elements = Column(JSON) # מילון של דירוגי 1-5 לכל אלמנט
    abroad_cons = Column(String)
    abroad_con_names = Column(Text, nullable=True)
    session = relationship("SurveySession", back_populates="part6")

class Part7Stores(Base):
    __tablename__ = "part7_stores"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    visited_store = Column(String)
    store_frequency = Column(String)
    why_store = Column(JSON)
    where_buy = Column(JSON)
    money_spent = Column(String)
    what_bought = Column(JSON)
    session = relationship("SurveySession", back_populates="part7")

class Part8Parents(Base):
    __tablename__ = "part8_parents"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    has_kids = Column(String)
    kids_play = Column(String)
    frameworks = Column(JSON)
    kids_ages = Column(JSON)
    positive_activity = Column(Integer) # 1-5
    core_value = Column(JSON)
    concerns = Column(JSON)
    willing_to_pay = Column(String)
    family_players = Column(String)
    session = relationship("SurveySession", back_populates="part8")

class Part9Barriers(Base):
    __tablename__ = "part9_barriers"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    barriers_to_start = Column(JSON)
    what_would_help = Column(JSON)
    preferred_framework = Column(String)
    session = relationship("SurveySession", back_populates="part9")

class Part10Former(Base):
    __tablename__ = "part10_former"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    when_stopped = Column(String)
    why_stopped = Column(JSON)
    what_brings_back = Column(JSON)
    session = relationship("SurveySession", back_populates="part10")

class Part11Community(Base):
    __tablename__ = "part11_community"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    belonging_level = Column(Integer) # 1-5
    where_is_community = Column(JSON)
    welcoming_level = Column(Integer) # 1-5
    underserved_groups = Column(JSON)
    bad_experience = Column(String)
    bad_experience_type = Column(String, nullable=True)
    session = relationship("SurveySession", back_populates="part11")

class Part12Hobbies(Base):
    __tablename__ = "part12_hobbies"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    other_hobbies = Column(JSON)
    other_communities = Column(JSON)
    leisure_hours = Column(String)
    session = relationship("SurveySession", back_populates="part12")

class Part13WorkStudy(Base):
    __tablename__ = "part13_workstudy"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    status = Column(String)
    field = Column(JSON)
    connection_to_hobby = Column(String)
    connection_details = Column(Text, nullable=True)
    session = relationship("SurveySession", back_populates="part13")

class Part14Creation(Base):
    __tablename__ = "part14_creation"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    created_content = Column(JSON)
    published_content = Column(String)
    barriers = Column(JSON)
    want_hebrew_content = Column(Integer) # 1-5
    missing_content = Column(JSON)
    session = relationship("SurveySession", back_populates="part14")

class Part15Business(Base):
    __tablename__ = "part15_business"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    business_type = Column(JSON)
    target_audience = Column(JSON)
    challenges = Column(JSON)
    growth_helpers = Column(JSON)
    session = relationship("SurveySession", back_populates="part15")

class Part16Vision(Base):
    __tablename__ = "part16_vision"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("survey_sessions.id"))
    missing_thing_1 = Column(String)
    missing_thing_2 = Column(String)
    missing_thing_3 = Column(String)
    helpful_projects = Column(JSON)
    growth_perception = Column(String)
    what_brings_new_people = Column(JSON)
    nps_score = Column(Integer) # 0-10
    one_sentence_value = Column(Text)
    session = relationship("SurveySession", back_populates="part16")
