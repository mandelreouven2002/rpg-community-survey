import hmac, hashlib, os, json
from datetime import date
from dotenv import load_dotenv

load_dotenv()
_SECRET = os.getenv("SECRET_KEY", "fallback-secret")

def validate_israeli_id(id_str: str) -> bool:
    s = id_str.strip().zfill(9)
    if not s.isdigit() or len(s) != 9:
        return False
    total = 0
    for i, d in enumerate(s):
        v = int(d) * (1 if i % 2 == 0 else 2)
        if v > 9:
            v -= 9
        total += v
    return total % 10 == 0

def hash_value(val: str) -> str:
    return hmac.new(_SECRET.encode(), val.strip().encode(), hashlib.sha256).hexdigest()

def hash_ip(ip: str) -> str:
    return hmac.new(_SECRET.encode(), ip.encode(), hashlib.sha256).hexdigest()

def calculate_age(dob_str: str):
    try:
        dob = date.fromisoformat(dob_str)
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return None

ROLE_SECTION_MAP = {
    "tabletop_player":  "section3",
    "gm":               "section4",
    "larp_participant": "section5",
    "larp_organizer":   "section5",
    "parent":           "section6",
    "business":         "section7",
    "interested":       "section8",
    "former_player":    "section9",
}

def determine_active_sections(roles: list) -> list:
    sections = ["section2"]
    seen = set()
    for r in roles:
        s = ROLE_SECTION_MAP.get(r)
        if s and s not in seen:
            sections.append(s)
            seen.add(s)
    return sections

def next_section(active: list, current: str):
    try:
        idx = active.index(current)
        return active[idx + 1] if idx + 1 < len(active) else None
    except ValueError:
        return None

SECTION_LABELS = {
    "section2": "היכרות עם התחום",
    "section3": "שחקנים שולחניים",
    "section4": "מנחים",
    "section5": "לארפ",
    "section6": "הורים",
    "section7": "עסקים",
    "section8": "חסמי כניסה",
    "section9": "נשירה מהתחום",
}
