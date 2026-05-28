import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, engine, get_db

app = FastAPI(title="RPG Community Survey", version="2.1.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def q(name: str, label: str, type_: str = "text", options=None, required: bool = False, min_: int = 1, max_: int = 5):
    item = {"name": name, "label": label, "type": type_, "required": required}
    if options is not None:
        item["options"] = options
    if type_ == "scale":
        item["min"] = min_
        item["max"] = max_
    return item


PARTS: list[dict[str, Any]] = [
    {
        "key": "part1",
        "table": "part1_basic",
        "title": "חלק 1 — פרטים בסיסיים",
        "columns": ["consent", "birth_date", "region", "city", "roles"],
        "questions": [
            q("birth_date", "תאריך לידה", "date"),
            q("region", "אזור מגורים", "select", ["צפון", "חיפה והקריות", "השרון", "גוש דן", "תל אביב-יפו", "ירושלים והסביבה", "השפלה", "דרום", "יהודה ושומרון", "אילת והערבה", "גר/ה בחו״ל", "מעדיף/ה לא לענות"]),
            q("city", "עיר / יישוב"),
            q("roles", "מה הקשר שלך לתחום? אפשר לבחור כמה", "checkbox", ["שחקן/ית שולחני/ת", "מנחה שולחני/ת", "משתתף/ת לארפים", "מארגן/ת לארפים", "הורה לילד/ה שמשחק/ת", "בעל/ת עסק / חנות", "יוצר/ת תוכן", "מתעניין/ת", "שחקן/ית עבר"]),
        ],
    },
    {
        "key": "part2",
        "table": "part2_general",
        "title": "חלק 2 — היכרות כללית עם התחום",
        "columns": ["years_familiar", "first_exposure", "significance_level", "interested_types"],
        "questions": [
            q("years_familiar", "כמה שנים את/ה מכיר/ה את תחום משחקי התפקידים?", "radio", ["פחות משנה", "1–2 שנים", "3–5 שנים", "6–10 שנים", "11–20 שנים", "מעל 20 שנים", "לא בטוח/ה"]),
            q("first_exposure", "איך נחשפת לראשונה למשחקי תפקידים?", "checkbox", ["חברים", "משפחה", "בית ספר", "חוג", "כנס", "חנות משחקים", "יוטיוב / פודקאסט", "משחקי מחשב", "סדרות / סרטים", "צבא / שירות / לימודים", "רשתות חברתיות", "דיסקורד", "אחר"]),
            q("significance_level", "עד כמה משחקי תפקידים הם חלק משמעותי מהחיים שלך?", "scale", min_=1, max_=5),
            q("interested_types", "אילו סוגי משחקי תפקידים מעניינים אותך?", "checkbox", ["משחקים שולחניים", "לארפים", "משחקי ילדים ונוער", "משחקים טיפוליים / חינוכיים", "משחקים אונליין", "וואנשוטים", "קמפיינים ארוכים", "משחקים סיפוריים", "משחקים טקטיים", "משחקי אינדי", "מבוכים ודרקונים", "יצירת שיטות", "תרגום והוצאה לאור"]),
        ],
    },
    {
        "key": "part3",
        "table": "part3_tabletop",
        "title": "חלק 3 — משחקים שולחניים",
        "columns": ["play_currently", "frequency", "frameworks", "locations", "online_vs_physical", "online_tools", "systems_played", "favorite_genres", "active_groups", "group_size", "session_length", "player_challenges"],
        "questions": [
            q("play_currently", "האם את/ה משחק/ת כיום משחקי תפקידים שולחניים?", "radio", ["כן", "לא", "לעיתים רחוקות"]),
            q("frequency", "באיזו תדירות את/ה משחק/ת?", "radio", ["כמה פעמים בשבוע", "פעם בשבוע", "פעמיים בחודש", "פעם בחודש", "כמה פעמים בשנה", "כמעט לא"]),
            q("frameworks", "באילו מסגרות את/ה משחק/ת?", "checkbox", ["קבוצה פרטית", "חוג", "כנס", "חנות", "אונליין", "מועדון / מרכז קהילתי", "בית ספר / לימודים", "אחר"]),
            q("locations", "איפה המשחקים מתקיימים בדרך כלל?"),
            q("online_vs_physical", "מה היחס בין אונליין לפרונטלי?", "radio", ["בעיקר פרונטלי", "בעיקר אונליין", "חצי־חצי", "משתנה מאוד"]),
            q("online_tools", "באילו כלים אונליין את/ה משתמש/ת?", "checkbox", ["Discord", "Roll20", "Foundry VTT", "Zoom / Meet", "Owlbear Rodeo", "WhatsApp", "לא משחק/ת אונליין", "אחר"]),
            q("systems_played", "באילו שיטות שיחקת?", "checkbox", ["D&D 5e", "Pathfinder", "חרבות וכשפים", "עולמות פראיים", "Call of Cthulhu", "Powered by the Apocalypse", "Blades in the Dark", "Fate", "שיטת בית", "אחר"]),
            q("favorite_genres", "ז׳אנרים מועדפים", "checkbox", ["פנטזיה", "מדע בדיוני", "אימה", "חקירה / מסתורין", "גיבורי־על", "היסטורי", "קומדיה", "דרמה", "פוסט־אפוקליפסה", "אחר"]),
            q("active_groups", "בכמה קבוצות פעילות את/ה משתתף/ת?", "radio", ["0", "1", "2", "3+", "משתנה"]),
            q("group_size", "גודל קבוצה טיפוסי", "radio", ["2–3", "4–5", "6–7", "8+", "משתנה"]),
            q("session_length", "אורך מפגש טיפוסי", "radio", ["עד שעה", "1–2 שעות", "2–4 שעות", "4+ שעות", "משתנה"]),
            q("player_challenges", "מה מקשה עליך כשחקן/ית?", "checkbox", ["תיאום זמנים", "מציאת קבוצה", "מציאת מנחה", "מרחק", "עלות", "חוסר ביטחון", "חוקים מורכבים", "אחר"]),
        ],
    },
    {
        "key": "part4",
        "table": "part4_gms",
        "title": "חלק 4 — מנחים והנחיה",
        "columns": ["gm_currently", "gm_years", "gm_frameworks", "paid_gm", "paid_services", "paid_price_range", "paid_by_who", "want_more_paid", "gm_challenges", "desired_training"],
        "questions": [
            q("gm_currently", "האם את/ה מנחה כיום?", "radio", ["כן", "לא", "הנחיתי בעבר"]),
            q("gm_years", "כמה שנות ניסיון יש לך בהנחיה?", "radio", ["פחות משנה", "1–2", "3–5", "6–10", "10+"]),
            q("gm_frameworks", "באילו מסגרות הנחית?", "checkbox", ["קבוצה פרטית", "חוג", "כנס", "בית ספר", "מרכז קהילתי", "אונליין", "בתשלום", "התנדבות"]),
            q("paid_gm", "האם הנחית בתשלום?", "radio", ["כן", "לא", "שוקל/ת"]),
            q("paid_services", "אילו שירותים בתשלום סיפקת?", "checkbox", ["קמפיין", "וואנשוט", "חוג ילדים", "סדנה", "אירוע חברה", "אחר", "לא רלוונטי"]),
            q("paid_price_range", "טווח מחיר למפגש, אם רלוונטי"),
            q("paid_by_who", "מי שילם?", "checkbox", ["שחקנים", "הורים", "ארגון", "חנות", "אחר", "לא רלוונטי"]),
            q("want_more_paid", "האם היית רוצה שיהיו יותר משחקים בתשלום?", "radio", ["כן", "לא", "אולי"]),
            q("gm_challenges", "אתגרי הנחיה מרכזיים", "checkbox", ["מציאת שחקנים", "תיאום זמנים", "הכנת תוכן", "ניהול קבוצה", "שחיקה", "מחיר / ציוד", "מרחב מתאים", "אחר"]),
            q("desired_training", "איזו הכשרה למנחים הייתה מעניינת אותך?", "checkbox", ["מנחים מתחילים", "ניהול קבוצה", "כתיבת הרפתקאות", "בטיחות וכלים חברתיים", "הנחיית ילדים", "הנחיה בתשלום", "לא מעוניין/ת"]),
        ],
    },
    {
        "key": "part5",
        "table": "part5_larps",
        "title": "חלק 5 — לארפים",
        "columns": ["larp_last_year", "larp_count", "larp_types", "barriers", "want_more_larps"],
        "questions": [
            q("larp_last_year", "האם השתתפת בלארפ בשנה האחרונה?", "radio", ["כן", "לא"]),
            q("larp_count", "בכמה לארפים השתתפת בשנה האחרונה?", "radio", ["0", "1", "2–3", "4–6", "7+"]),
            q("larp_types", "אילו סוגי לארפים מעניינים אותך?", "checkbox", ["פנטזיה", "אימה", "מד״ב", "פוליטי / חברתי", "קרבות", "דרמה", "לארפים קצרים", "לארפים גדולים", "אחר"]),
            q("barriers", "מה מקשה על השתתפות בלארפים?", "checkbox", ["אין מידע", "מרחק", "עלות", "חוסר זמן", "חסם חברתי", "ציוד / תחפושת", "אין מספיק אירועים", "אחר"]),
            q("want_more_larps", "האם היית רוצה שיהיו יותר לארפים בישראל?", "radio", ["כן", "לא", "אולי"]),
        ],
    },
    {
        "key": "part6",
        "table": "part6_conventions",
        "title": "חלק 6 — כנסים ואירועים",
        "columns": ["attended_con", "con_names", "con_frequency", "why_attend", "barriers", "important_elements", "abroad_cons", "abroad_con_names"],
        "questions": [
            q("attended_con", "האם השתתפת בכנס משחקי תפקידים בשנה האחרונה?", "radio", ["כן", "לא"]),
            q("con_names", "באילו כנסים / אירועים השתתפת?", "checkbox", ["דרקוניקון", "אייקון", "ביגור", "כנס מקומי", "אירוע בחנות", "אירוע אונליין", "אחר"]),
            q("con_frequency", "כמה פעמים בשנה את/ה מגיע/ה לכנסים?", "radio", ["0", "1", "2–3", "4–6", "7+"]),
            q("why_attend", "למה את/ה מגיע/ה לכנסים?", "checkbox", ["לשחק", "להנחות", "לפגוש חברים", "לקנות מוצרים", "להכיר קהילה", "להרצות / להפיק", "אחר"]),
            q("barriers", "מה מקשה להגיע לכנסים?", "checkbox", ["מרחק", "עלות", "זמן", "אין מידע", "חוסר עניין", "עומס / צפיפות", "אחר"]),
            q("important_elements", "מה חשוב בכנס טוב?", "checkbox", ["משחקים מגוונים", "ארגון ברור", "מחיר נגיש", "מיקום נגיש", "מתחם נעים", "תוכן לילדים", "דוכנים", "קהילה"]),
            q("abroad_cons", "האם השתתפת בכנסים בחו״ל?", "radio", ["כן", "לא", "מתכנן/ת"]),
            q("abroad_con_names", "אם כן, באילו?", "textarea"),
        ],
    },
    {
        "key": "part7",
        "table": "part7_stores",
        "title": "חלק 7 — חנויות וקנייה",
        "columns": ["visited_store", "store_frequency", "why_store", "where_buy", "money_spent", "what_bought"],
        "questions": [
            q("visited_store", "האם ביקרת בחנות משחקים בשנה האחרונה?", "radio", ["כן", "לא"]),
            q("store_frequency", "באיזו תדירות את/ה מבקר/ת בחנויות משחקים?", "radio", ["אף פעם", "פעם בשנה", "כמה פעמים בשנה", "פעם בחודש", "יותר מפעם בחודש"]),
            q("why_store", "למה את/ה מגיע/ה לחנות?", "checkbox", ["לקנות", "לשחק", "להכיר אנשים", "אירועים", "ייעוץ", "אחר"]),
            q("where_buy", "איפה את/ה קונה מוצרים?", "checkbox", ["חנויות בישראל", "חנויות בחו״ל", "PDF / דיגיטלי", "Kickstarter", "כנסים", "לא קונה"]),
            q("money_spent", "כמה בערך את/ה מוציא/ה בשנה על התחום?", "radio", ["0 ₪", "1–100 ₪", "101–300 ₪", "301–700 ₪", "701–1500 ₪", "1500+ ₪", "מעדיף/ה לא לענות"]),
            q("what_bought", "מה את/ה קונה?", "checkbox", ["ספרים", "קוביות", "מיניאטורות", "מפות / עזרים", "PDF", "מרצ׳נדייז", "כרטיסי כנס", "אחר"]),
        ],
    },
    {
        "key": "part8",
        "table": "part8_parents",
        "title": "חלק 8 — הורים וילדים",
        "columns": ["has_kids", "kids_play", "frameworks", "kids_ages", "positive_activity", "core_value", "concerns", "willing_to_pay", "family_players"],
        "questions": [
            q("has_kids", "האם יש לך ילדים?", "radio", ["כן", "לא"]),
            q("kids_play", "האם הילדים שלך משחקים משחקי תפקידים?", "radio", ["כן", "לא", "לא רלוונטי"]),
            q("frameworks", "באילו מסגרות הם משחקים?", "checkbox", ["בית", "חוג", "בית ספר", "כנס", "אונליין", "חנות", "לא רלוונטי"]),
            q("kids_ages", "גילי הילדים שמשחקים", "checkbox", ["עד 6", "7–9", "10–12", "13–15", "16–18", "לא רלוונטי"]),
            q("positive_activity", "עד כמה משחקי תפקידים נתפסים בעיניך כפעילות חיובית לילדים?", "scale", min_=1, max_=5),
            q("core_value", "אילו ערכים יש במשחקי תפקידים לילדים?", "checkbox", ["דמיון", "חברות", "פתרון בעיות", "שפה", "ביטחון עצמי", "עבודת צוות", "למידה", "אחר"]),
            q("concerns", "אילו חששות קיימים?", "checkbox", ["זמן מסך", "אלימות", "עלות", "חברה לא מתאימה", "מורכבות", "אין חששות", "אחר"]),
            q("willing_to_pay", "האם היית מוכן/ה לשלם על חוג / פעילות?", "radio", ["כן", "לא", "אולי", "לא רלוונטי"]),
            q("family_players", "כמה בני משפחה נוספים משחקים?", "radio", ["0", "1", "2", "3+", "לא רלוונטי"]),
        ],
    },
    {
        "key": "part9",
        "table": "part9_barriers",
        "title": "חלק 9 — חסמים וכניסה לתחום",
        "columns": ["barriers_to_start", "what_would_help", "preferred_framework"],
        "questions": [
            q("barriers_to_start", "מה מקשה על אנשים להתחיל לשחק?", "checkbox", ["לא יודעים מאיפה להתחיל", "אין קבוצה", "אין מנחה", "אין זמן", "עלות", "מרחק", "חסם חברתי", "שפה", "חוקים מורכבים", "חוסר תוכן בעברית", "אחר"]),
            q("what_would_help", "מה יעזור לאנשים להיכנס לתחום?", "checkbox", ["מדריך למתחילים", "מאגר קבוצות", "אירועי היכרות", "חוגים", "מנחים למתחילים", "תוכן בעברית", "קהילות מקומיות", "אחר"]),
            q("preferred_framework", "איזו מסגרת הכי מתאימה למתחילים?", "radio", ["קבוצה פרטית", "חוג", "כנס", "חנות", "אונליין", "בית ספר / מרכז קהילתי"]),
        ],
    },
    {
        "key": "part10",
        "table": "part10_former",
        "title": "חלק 10 — שחקני עבר",
        "columns": ["when_stopped", "why_stopped", "what_brings_back"],
        "questions": [
            q("when_stopped", "אם הפסקת לשחק — מתי?", "radio", ["בשנה האחרונה", "לפני 1–3 שנים", "לפני 4–10 שנים", "לפני יותר מ־10 שנים", "לא הפסקתי"]),
            q("why_stopped", "למה הפסקת?", "checkbox", ["חוסר זמן", "אין קבוצה", "אין מנחה", "מעבר מקום", "צבא / לימודים / עבודה", "עלות", "שחיקה", "לא רלוונטי", "אחר"]),
            q("what_brings_back", "מה יכול להחזיר אותך לשחק?", "checkbox", ["קבוצה זמינה", "משחק קצר", "כנס", "אונליין", "חברים", "שיטה פשוטה", "מנחה בתשלום", "לא רלוונטי"]),
        ],
    },
    {
        "key": "part11",
        "table": "part11_community",
        "title": "חלק 11 — קהילה ושייכות",
        "columns": ["belonging_level", "where_is_community", "welcoming_level", "underserved_groups", "bad_experience", "bad_experience_type"],
        "questions": [
            q("belonging_level", "עד כמה את/ה מרגיש/ה שייכות לקהילת משחקי התפקידים?", "scale", min_=1, max_=5),
            q("where_is_community", "איפה הקהילה שלך נמצאת?", "checkbox", ["קבוצת משחק", "פייסבוק", "וואטסאפ", "דיסקורד", "כנסים", "חנות", "חברים", "אין לי קהילה"]),
            q("welcoming_level", "עד כמה הקהילה מסבירת פנים לחדשים?", "scale", min_=1, max_=5),
            q("underserved_groups", "אילו קבוצות מקבלות פחות מענה לדעתך?", "checkbox", ["ילדים", "נוער", "מבוגרים", "נשים", "שחקנים חדשים", "פריפריה", "דוברי עברית", "קהילות דתיות", "אחר"]),
            q("bad_experience", "האם חווית חוויה לא נעימה בתחום?", "radio", ["כן", "לא", "מעדיף/ה לא לענות"]),
            q("bad_experience_type", "אם כן, באיזה סוג?", "radio", ["חברתית", "בטיחותית", "כספית", "ארגונית", "אחר", "לא רלוונטי"]),
        ],
    },
    {
        "key": "part12",
        "table": "part12_hobbies",
        "title": "חלק 12 — תחביבים נוספים",
        "columns": ["other_hobbies", "other_communities", "leisure_hours"],
        "questions": [
            q("other_hobbies", "אילו תחביבים נוספים יש לך?", "checkbox", ["משחקי לוח", "משחקי מחשב", "כתיבה", "קריאה", "קומיקס", "אנימה / מנגה", "מד״ב ופנטזיה", "תיאטרון", "יצירה", "אחר"]),
            q("other_communities", "באילו קהילות פנאי נוספות את/ה פעיל/ה?", "checkbox", ["גיימינג", "משחקי לוח", "מד״ב ופנטזיה", "קומיקס", "לארפים", "כתיבה", "תיאטרון", "לא פעיל/ה"]),
            q("leisure_hours", "כמה שעות פנאי יש לך בשבוע לתחביבים?", "radio", ["0–2", "3–5", "6–10", "11–20", "20+"]),
        ],
    },
    {
        "key": "part13",
        "table": "part13_workstudy",
        "title": "חלק 13 — עבודה ולימודים",
        "columns": ["status", "field", "connection_to_hobby", "connection_details"],
        "questions": [
            q("status", "סטטוס עיקרי", "radio", ["תלמיד/ה", "סטודנט/ית", "עובד/ת", "עצמאי/ת", "בין עבודות", "אחר", "מעדיף/ה לא לענות"]),
            q("field", "תחום עיסוק / לימודים", "checkbox", ["טכנולוגיה", "חינוך", "טיפול", "אמנות / עיצוב", "ניהול / עסקים", "מדעים", "צבא / שירות", "אחר", "מעדיף/ה לא לענות"]),
            q("connection_to_hobby", "האם יש קשר בין התחום שלך למשחקי תפקידים?", "radio", ["כן", "לא", "אולי"]),
            q("connection_details", "אם כן, מה הקשר?", "textarea"),
        ],
    },
    {
        "key": "part14",
        "table": "part14_creation",
        "title": "חלק 14 — יצירה ותוכן",
        "columns": ["created_content", "published_content", "barriers", "want_hebrew_content", "missing_content"],
        "questions": [
            q("created_content", "איזה תוכן יצרת?", "checkbox", ["הרפתקאות", "שיטה", "עולם מערכה", "תרגום", "איור / עיצוב", "וידאו / פודקאסט", "לא יצרתי", "אחר"]),
            q("published_content", "האם פרסמת תוכן שיצרת?", "radio", ["כן", "לא", "שוקל/ת"]),
            q("barriers", "מה מקשה על יצירת / פרסום תוכן?", "checkbox", ["זמן", "ידע", "כסף", "עריכה / עיצוב", "שיווק", "ביטחון עצמי", "אין קהל", "אחר"]),
            q("want_hebrew_content", "עד כמה חסר לך תוכן בעברית?", "scale", min_=1, max_=5),
            q("missing_content", "איזה תוכן חסר בעברית?", "checkbox", ["מדריכים", "הרפתקאות", "שיטות", "תרגומים", "תוכן לילדים", "תוכן למנחים", "סקירות", "אחר"]),
        ],
    },
    {
        "key": "part15",
        "table": "part15_business",
        "title": "חלק 15 — עסקים ופעילות מקצועית",
        "columns": ["business_type", "target_audience", "challenges", "growth_helpers"],
        "questions": [
            q("business_type", "איזה סוג פעילות עסקית יש לך?", "checkbox", ["חנות", "חוגים", "הנחיה בתשלום", "הוצאה לאור", "אירועים", "תוכן דיגיטלי", "אין פעילות עסקית", "אחר"]),
            q("target_audience", "מי קהל היעד שלך?", "checkbox", ["ילדים", "נוער", "מבוגרים", "הורים", "שחקנים חדשים", "מנחים", "קהילה כללית", "לא רלוונטי"]),
            q("challenges", "אתגרים עסקיים מרכזיים", "checkbox", ["שיווק", "תמחור", "בירוקרטיה", "מסים", "קהל קטן", "עונתיות", "מיקום", "כוח אדם", "אחר"]),
            q("growth_helpers", "מה יעזור לעסקים בתחום לצמוח?", "checkbox", ["נתוני שוק", "פרסום מרוכז", "שיתופי פעולה", "אירועים", "הכשרות", "תמיכה משפטית / פיננסית", "קהילה מקצועית", "אחר"]),
        ],
    },
    {
        "key": "part16",
        "table": "part16_vision",
        "title": "חלק 16 — חזון וסיכום",
        "columns": ["missing_thing_1", "missing_thing_2", "missing_thing_3", "helpful_projects", "growth_perception", "what_brings_new_people", "nps_score", "one_sentence_value"],
        "questions": [
            q("missing_thing_1", "מה הדבר הראשון שהכי חסר בתחום?"),
            q("missing_thing_2", "מה הדבר השני שהכי חסר בתחום?"),
            q("missing_thing_3", "מה הדבר השלישי שהכי חסר בתחום?"),
            q("helpful_projects", "אילו פרויקטים יעזרו לקהילה?", "checkbox", ["מאגר קבוצות", "לוח אירועים", "מדריכים", "הכשרות מנחים", "דוח שנתי", "פורטל עסקים", "קהילות מקומיות", "אחר"]),
            q("growth_perception", "איך התחום יתפתח בישראל בשנים הקרובות?", "radio", ["יגדל מאוד", "יגדל מעט", "יישאר דומה", "יצטמצם", "לא יודע/ת"]),
            q("what_brings_new_people", "מה יביא אנשים חדשים לתחום?", "checkbox", ["חברים", "בתי ספר", "תוכן בעברית", "אירועי היכרות", "חנויות", "רשתות חברתיות", "משחקים פשוטים", "אחר"]),
            q("nps_score", "עד כמה היית ממליץ/ה לחבר/ה להיכנס לתחום?", "scale", min_=0, max_=10),
            q("one_sentence_value", "במשפט אחד: למה משחקי תפקידים חשובים?", "textarea"),
        ],
    },
]

PART_BY_KEY = {part["key"]: part for part in PARTS}
PART_KEYS = [part["key"] for part in PARTS]

# Most survey questions are required.
# Exceptions are privacy-sensitive, open details, or conditional follow-ups.
OPTIONAL_QUESTIONS = {
    ("part1", "city"),
    ("part3", "online_tools"),
    ("part4", "paid_services"),
    ("part4", "paid_price_range"),
    ("part4", "paid_by_who"),
    ("part4", "want_more_paid"),
    ("part6", "abroad_con_names"),
    ("part8", "frameworks"),
    ("part8", "kids_ages"),
    ("part11", "bad_experience_type"),
    ("part13", "connection_details"),
}

for _part in PARTS:
    for _question in _part["questions"]:
        _question["required"] = (_part["key"], _question["name"]) not in OPTIONAL_QUESTIONS

SHORT_PART_KEYS = ["part1", "part2", "part3", "part9", "part11", "part16"]

def normalize_israeli_id(raw_identifier: str) -> str:
    return "".join(ch for ch in raw_identifier.strip() if ch.isdigit())


def is_valid_israeli_id(raw_identifier: str) -> bool:
    """
    Israeli ID validation:
    pad to 9 digits, multiply alternating 1/2, sum digits, total must divide by 10.
    """
    value = normalize_israeli_id(raw_identifier)
    if not value or len(value) > 9:
        return False

    value = value.zfill(9)
    total = 0

    for index, char in enumerate(value):
        digit = int(char)
        multiplier = 1 if index % 2 == 0 else 2
        product = digit * multiplier
        total += product if product < 10 else (product // 10 + product % 10)

    return total % 10 == 0


def hash_identifier(raw_identifier: str) -> str:
    normalized = normalize_israeli_id(raw_identifier)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_active_part_keys(survey_type: str = "full", roles: list[str] | None = None) -> list[str]:
    roles = roles or []

    def has_any(*needles: str) -> bool:
        return any(any(needle in role for needle in needles) for role in roles)

    # Core sections. These are the useful baseline for almost everyone.
    active = ["part1", "part2", "part6", "part9", "part11", "part16"]

    # Short questionnaire: core + immediately relevant conditional paths.
    if survey_type == "short":
        if has_any("שולחני", "שיחקתי בעבר", "עבר"):
            active.append("part3")
        if has_any("מנחה"):
            active.append("part4")
        if has_any("לארפ"):
            active.append("part5")
        if has_any("הורה"):
            active.append("part8")
        if has_any("מתעניין"):
            active.append("part9")
        if has_any("עבר"):
            active.append("part10")
        return [key for key in PART_KEYS if key in set(active)]

    # Full questionnaire.
    active = ["part1", "part2", "part6", "part7", "part9", "part11", "part12", "part13", "part16"]

    if has_any("שולחני", "שיחקתי בעבר", "עבר"):
        active.append("part3")
    if has_any("מנחה", "חוגים", "סדנאות"):
        active.append("part4")
    if has_any("לארפ"):
        active.append("part5")
    if has_any("הורה"):
        active.append("part8")
    if has_any("עבר"):
        active.append("part10")
    if has_any("יוצר", "כותב", "מתרגם", "מוציא"):
        active.append("part14")
    if has_any("עסק", "חנות", "הוצאה", "חוגים", "סדנאות", "מארגן"):
        active.append("part15")

    return [key for key in PART_KEYS if key in set(active)]


def session_active_part_keys(sess) -> list[str]:
    if not sess:
        return PART_KEYS

    raw = sess.get("active_sections") if hasattr(sess, "get") else None
    if raw:
        try:
            parsed = json.loads(raw)
            keys = [key for key in parsed if key in PART_BY_KEY]
            if keys:
                return keys
        except Exception:
            pass

    survey_type = (sess.get("survey_type") if hasattr(sess, "get") else None) or "full"
    return build_active_part_keys(survey_type)

def resume_destination(sess) -> str:
    if not sess:
        return "/survey"

    if sess.get("submitted") or sess.get("is_submitted"):
        return "/survey/complete"

    active_keys = session_active_part_keys(sess)
    current = sess.get("current_section") or active_keys[0]

    if current == "submit":
        return "/survey/submit"
    if current in active_keys:
        return f"/survey/{current}"

    return f"/survey/{active_keys[0]}"


def render(request: Request, template: str, **context):
    context["request"] = request
    return templates.TemplateResponse(
        request=request,
        name=template,
        context=context,
    )


def hash_ip(request: Request) -> str:
    raw = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    first_ip = raw.split(",")[0].strip()
    return hashlib.sha256(first_ip.encode("utf-8")).hexdigest()


def now() -> datetime:
    return datetime.utcnow()


def get_session(db: Session, session_id: str | None):
    if not session_id:
        return None
    return db.execute(
        text("SELECT * FROM survey_sessions WHERE id = :id"),
        {"id": session_id},
    ).mappings().first()


def is_under_13(birth_date_raw: str) -> bool:
    if not birth_date_raw:
        return False

    try:
        born = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
    except ValueError:
        return False

    today = datetime.utcnow().date()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return age < 13


def delete_session_data(db: Session, session_id: str):
    for part in PARTS:
        db.execute(
            text(f"DELETE FROM {part['table']} WHERE session_id = :session_id"),
            {"session_id": session_id},
        )
    db.execute(text("DELETE FROM survey_sessions WHERE id = :id"), {"id": session_id})
    db.commit()


def delete_unsubmitted_by_ip(db: Session, ip_hash: str):
    for part in PARTS:
        db.execute(
            text(f"""
                DELETE FROM {part['table']}
                WHERE session_id IN (
                    SELECT id
                    FROM survey_sessions
                    WHERE ip_hash = :ip_hash
                      AND COALESCE(submitted, FALSE) = FALSE
                      AND COALESCE(is_submitted, FALSE) = FALSE
                )
            """),
            {"ip_hash": ip_hash},
        )

    db.execute(
        text("""
            DELETE FROM survey_sessions
            WHERE ip_hash = :ip_hash
              AND COALESCE(submitted, FALSE) = FALSE
              AND COALESCE(is_submitted, FALSE) = FALSE
        """),
        {"ip_hash": ip_hash},
    )
    db.commit()


def cleanup_old_drafts():
    cutoff = datetime.utcnow() - timedelta(days=30)

    with engine.begin() as conn:
        for part in PARTS:
            conn.execute(
                text(f"""
                    DELETE FROM {part['table']}
                    WHERE session_id IN (
                        SELECT id
                        FROM survey_sessions
                        WHERE COALESCE(submitted, FALSE) = FALSE
                          AND COALESCE(is_submitted, FALSE) = FALSE
                          AND created_at < :cutoff
                    )
                """),
                {"cutoff": cutoff},
            )

        conn.execute(
            text("""
                DELETE FROM survey_sessions
                WHERE COALESCE(submitted, FALSE) = FALSE
                  AND COALESCE(is_submitted, FALSE) = FALSE
                  AND created_at < :cutoff
            """),
            {"cutoff": cutoff},
        )


def part_access_redirect(sess, requested_key: str) -> str | None:
    """
    Prevent jumping forward by manually editing the URL.

    Allowed:
    - current section
    - already completed earlier sections
    - all sections after reaching submit/review

    Blocked:
    - future sections
    - inactive conditional sections
    """
    if not sess:
        return "/survey"

    if sess.get("submitted") or sess.get("is_submitted"):
        return "/survey/complete"

    active_keys = session_active_part_keys(sess)
    if not active_keys:
        return "/survey"

    current = sess.get("current_section") or active_keys[0]

    if requested_key not in PART_BY_KEY:
        return "/survey"

    if requested_key not in active_keys:
        return resume_destination(sess)

    # After part1, before choosing short/full.
    if current == "type":
        if requested_key == "part1":
            return None
        return "/survey/type"

    # At submit/review stage, allow reviewing all active parts.
    if current == "submit":
        return None

    # Recover from stale/broken current_section.
    if current not in active_keys:
        return resume_destination(sess)

    requested_index = active_keys.index(requested_key)
    current_index = active_keys.index(current)

    # The important rule: no future jumps.
    if requested_index > current_index:
        return f"/survey/{current}"

    return None


def current_after_save(part_key: str, active_keys: list[str], current_section: str | None) -> str:
    """
    Move forward only when saving the current part.
    If the user went back and edited an older part, do not move progress backwards.
    """
    candidate = next_part(part_key, active_keys) or "submit"

    if not current_section:
        return candidate

    if current_section in {"submit", "complete"}:
        return current_section

    if current_section == "type":
        return candidate

    if current_section in active_keys:
        current_index = active_keys.index(current_section)

        if candidate == "submit":
            candidate_index = len(active_keys)
        elif candidate in active_keys:
            candidate_index = active_keys.index(candidate)
        else:
            candidate_index = 0

        if current_index > candidate_index:
            return current_section

    return candidate


def previous_part(key: str, active_keys: list[str] | None = None) -> str | None:
    keys = active_keys or PART_KEYS
    if key not in keys:
        return None
    i = keys.index(key)
    return keys[i - 1] if i > 0 else None


def next_part(key: str, active_keys: list[str] | None = None) -> str | None:
    keys = active_keys or PART_KEYS
    if key not in keys:
        return keys[0] if keys else None
    i = keys.index(key)
    return keys[i + 1] if i + 1 < len(keys) else None


def normalize_json_value(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def read_part_data(db: Session, session_id: str, part: dict[str, Any]) -> dict[str, Any]:
    row = db.execute(
        text(f"SELECT * FROM {part['table']} WHERE session_id = :session_id ORDER BY id DESC LIMIT 1"),
        {"session_id": session_id},
    ).mappings().first()

    if not row:
        return {}

    data = {}
    for question in part["questions"]:
        name = question["name"]
        value = row.get(name)
        if question["type"] == "checkbox":
            data[name] = normalize_json_value(value)
        elif value is None:
            data[name] = ""
        else:
            data[name] = value
    return data


def form_value(form, question: dict[str, Any]):
    name = question["name"]
    qtype = question["type"]

    if qtype == "checkbox":
        return json.dumps(form.getlist(name), ensure_ascii=False)

    raw = str(form.get(name, "")).strip()
    if raw == "":
        return None

    if qtype == "scale":
        try:
            return int(raw)
        except ValueError:
            return None

    return raw


def validate_form(form, part: dict[str, Any]) -> str | None:
    for question in part["questions"]:
        if not question.get("required"):
            continue
        name = question["name"]
        if question["type"] == "checkbox":
            if len(form.getlist(name)) == 0:
                return f"נא לענות על השאלה: {question['label']}"
        else:
            if not str(form.get(name, "")).strip():
                return f"נא לענות על השאלה: {question['label']}"
    return None


def save_part(db: Session, session_id: str, part: dict[str, Any], form):
    table = part["table"]
    columns = list(part["columns"])

    data = {"session_id": session_id}

    for col in columns:
        data[col] = None

    if part["key"] == "part1":
        data["consent"] = True

    question_map = {question["name"]: question for question in part["questions"]}
    for name, question in question_map.items():
        if name in columns:
            data[name] = form_value(form, question)

    db.execute(text(f"DELETE FROM {table} WHERE session_id = :session_id"), {"session_id": session_id})

    insert_columns = ["session_id"] + columns
    col_sql = ", ".join(insert_columns)
    json_columns = {
        question["name"]
        for question in part["questions"]
        if question["type"] == "checkbox"
    }
    param_sql = ", ".join(
        f"CAST(:{col} AS JSON)" if col in json_columns else f":{col}"
        for col in insert_columns
    )

    db.execute(
        text(f"INSERT INTO {table} ({col_sql}) VALUES ({param_sql})"),
        data,
    )

    sess = get_session(db, session_id)
    active_keys = session_active_part_keys(sess)

    if part["key"] == "part1":
        roles = []
        try:
            roles = json.loads(data.get("roles") or "[]")
        except Exception:
            roles = []

        survey_type = (sess.get("survey_type") if sess else None)

        # The spec says route choice happens after part1.
        if not survey_type:
            db.execute(
                text("""
                    UPDATE survey_sessions
                    SET active_sections = :active_sections,
                        current_section = 'type',
                        updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": session_id,
                    "active_sections": json.dumps(["part1"], ensure_ascii=False),
                    "updated_at": now(),
                },
            )
            db.commit()
            return

        active_keys = build_active_part_keys(survey_type, roles)

        db.execute(
            text("""
                UPDATE survey_sessions
                SET active_sections = :active_sections
                WHERE id = :id
            """),
            {
                "id": session_id,
                "active_sections": json.dumps(active_keys, ensure_ascii=False),
            },
        )

    nxt = next_part(part["key"], active_keys)
    target_current_section = current_after_save(
        part["key"],
        active_keys,
        sess.get("current_section") if sess else None,
    )
    section_json = json.dumps({k: v for k, v in data.items() if k != "session_id"}, ensure_ascii=False)

    part_number = int(part["key"].replace("part", ""))
    if 1 <= part_number <= 9:
        db.execute(
            text(f"""
                UPDATE survey_sessions
                SET current_section = :current_section,
                    updated_at = :updated_at,
                    section{part_number} = :section_json
                WHERE id = :id
            """),
            {
                "id": session_id,
                "current_section": target_current_section,
                "updated_at": now(),
                "section_json": section_json,
            },
        )
    else:
        db.execute(
            text("""
                UPDATE survey_sessions
                SET current_section = :current_section,
                    updated_at = :updated_at
                WHERE id = :id
            """),
            {
                "id": session_id,
                "current_section": target_current_section,
                "updated_at": now(),
            },
        )

    db.commit()


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    cleanup_old_drafts()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "home.html")


@app.get("/health")
def health():
    return {"ok": True, "service": "rpg-community-survey", "version": "2.1.0"}


@app.get("/survey", response_class=HTMLResponse)
def consent_get(request: Request):
    return render(request, "survey/consent.html")


@app.post("/survey/consent")
async def consent_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    if form.get("consent") != "yes":
        return RedirectResponse("/", status_code=303)

    respondent_id = str(form.get("respondent_id", "")).strip()
    if not respondent_id:
        return render(request, "survey/consent.html", error="נא להזין תעודת זהות.")

    if not is_valid_israeli_id(respondent_id):
        return render(request, "survey/consent.html", error="מספר תעודת הזהות אינו תקין. נא לבדוק ולהכניס שוב.")

    respondent_id_hash = hash_identifier(respondent_id)

    already_submitted = db.execute(
        text("SELECT id FROM id_hashes WHERE id_hash = :id_hash LIMIT 1"),
        {"id_hash": respondent_id_hash},
    ).mappings().first()

    if already_submitted:
        return render(request, "survey/consent.html", error="מספר תעודת הזהות כבר שימש לשליחת שאלון. לא ניתן לשלוח שאלון נוסף.")

    ip_hash = hash_ip(request)

    if form.get("resume_existing") == "yes":
        existing = db.execute(
            text("""
                SELECT *
                FROM survey_sessions
                WHERE ip_hash = :ip_hash
                  AND COALESCE(is_submitted, FALSE) = FALSE
                  AND COALESCE(submitted, FALSE) = FALSE
                ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                LIMIT 1
            """),
            {"ip_hash": ip_hash},
        ).mappings().first()

        if existing:
            response = RedirectResponse(resume_destination(existing), status_code=303)
            response.set_cookie("session_id", existing["id"], httponly=True, samesite="lax")
            response.set_cookie("respondent_id_hash", respondent_id_hash, httponly=True, samesite="lax")
            return response

    session_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO survey_sessions
            (id, ip_hash, survey_type, submitted, is_submitted, current_section, created_at, updated_at, active_sections)
            VALUES
            (:id, :ip_hash, NULL, :submitted, :is_submitted, :current_section, :created_at, :updated_at, :active_sections)
        """),
        {
            "id": session_id,
            "ip_hash": ip_hash,
            "submitted": False,
            "is_submitted": False,
            "current_section": "part1",
            "created_at": now(),
            "updated_at": now(),
            "active_sections": json.dumps(["part1"], ensure_ascii=False),
        },
    )
    db.commit()

    response = RedirectResponse("/survey/part1", status_code=303)
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax")
    response.set_cookie("respondent_id_hash", respondent_id_hash, httponly=True, samesite="lax")
    return response



@app.get("/survey/type", response_class=HTMLResponse)
def survey_type_get(request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    part1 = read_part_data(db, session_id, PART_BY_KEY["part1"])
    roles = part1.get("roles", [])

    short_parts = build_active_part_keys("short", roles)
    full_parts = build_active_part_keys("full", roles)

    return render(
        request,
        "survey/type.html",
        short_count=len(short_parts),
        full_count=len(full_parts),
    )


@app.post("/survey/type")
async def survey_type_post(request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    form = await request.form()
    survey_type = str(form.get("survey_type", "short")).strip()
    if survey_type not in {"short", "full"}:
        survey_type = "short"

    part1 = read_part_data(db, session_id, PART_BY_KEY["part1"])
    roles = part1.get("roles", [])
    active_sections = build_active_part_keys(survey_type, roles)

    # After choosing the route, continue to the first section after part1.
    next_key = next_part("part1", active_sections) or "submit"

    db.execute(
        text("""
            UPDATE survey_sessions
            SET survey_type = :survey_type,
                active_sections = :active_sections,
                current_section = :current_section,
                updated_at = :updated_at
            WHERE id = :id
        """),
        {
            "id": session_id,
            "survey_type": survey_type,
            "active_sections": json.dumps(active_sections, ensure_ascii=False),
            "current_section": next_key,
            "updated_at": now(),
        },
    )
    db.commit()

    if next_key == "submit":
        return RedirectResponse("/survey/submit", status_code=303)

    return RedirectResponse(f"/survey/{next_key}", status_code=303)


@app.get("/survey/demographics")
def old_demographics_get():
    return RedirectResponse("/survey/part1", status_code=303)


@app.post("/survey/demographics")
def old_demographics_post():
    return RedirectResponse("/survey/part1", status_code=303)



@app.get("/survey/too-young", response_class=HTMLResponse)
def too_young_get(request: Request):
    return render(request, "survey/too_young.html")


@app.get("/survey/submit", response_class=HTMLResponse)
def submit_get(request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    active_keys = session_active_part_keys(sess)
    sections = {}
    for key in active_keys:
        part = PART_BY_KEY[key]
        sections[part["title"]] = read_part_data(db, session_id, part)

    return render(request, "survey/submit.html", sections=sections)


@app.post("/survey/submit")
def submit_post(
    request: Request,
    session_id: str | None = Cookie(None),
    respondent_id_hash: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    if not respondent_id_hash:
        return render(request, "survey/consent.html", error="לא נמצא מזהה המשתתף. נא להתחיל מחדש כדי לשלוח את השאלון.")

    already_submitted = db.execute(
        text("SELECT id FROM id_hashes WHERE id_hash = :id_hash LIMIT 1"),
        {"id_hash": respondent_id_hash},
    ).mappings().first()

    if already_submitted:
        return render(request, "survey/consent.html", error="מספר תעודת הזהות כבר שימש לשליחת שאלון. לא ניתן לשלוח שאלון נוסף.")

    db.execute(
        text("INSERT INTO id_hashes (id_hash) VALUES (:id_hash)"),
        {"id_hash": respondent_id_hash},
    )

    db.execute(
        text("""
            UPDATE survey_sessions
            SET submitted = TRUE,
                is_submitted = TRUE,
                current_section = 'complete',
                updated_at = :updated_at
            WHERE id = :id
        """),
        {"id": session_id, "updated_at": now()},
    )
    db.commit()

    response = RedirectResponse("/survey/complete", status_code=303)
    response.delete_cookie("session_id")
    response.delete_cookie("respondent_id_hash")
    return response



@app.post("/survey/raffle")
async def raffle_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    want_updates = form.get("want_updates") == "yes"
    want_raffle = form.get("want_raffle") == "yes"
    email = str(form.get("email", "")).strip().lower()

    if (want_updates or want_raffle) and email:
        db.execute(
            text("""
                INSERT INTO raffle_emails (email, want_updates, want_raffle, created_at)
                VALUES (:email, :want_updates, :want_raffle, :created_at)
                ON CONFLICT (email)
                DO UPDATE SET
                    want_updates = EXCLUDED.want_updates,
                    want_raffle = EXCLUDED.want_raffle,
                    created_at = EXCLUDED.created_at
            """),
            {
                "email": email,
                "want_updates": want_updates,
                "want_raffle": want_raffle,
                "created_at": now(),
            },
        )
        db.commit()

    return RedirectResponse("/survey/complete?raffle_saved=1", status_code=303)


@app.get("/survey/complete", response_class=HTMLResponse)
def complete_get(request: Request):
    return render(request, "survey/complete.html")


@app.post("/survey/delete")
def delete_my_data(
    request: Request,
    session_id: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    if session_id:
        sess = get_session(db, session_id)
        if sess:
            delete_unsubmitted_by_ip(db, sess["ip_hash"])
        else:
            delete_unsubmitted_by_ip(db, hash_ip(request))
    else:
        delete_unsubmitted_by_ip(db, hash_ip(request))

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session_id")
    response.delete_cookie("respondent_id_hash")
    return response


@app.get("/admin/export.csv")
def export_csv(db: Session = Depends(get_db)):
    sessions = db.execute(
        text("""
            SELECT id, survey_type, submitted, is_submitted, current_section, created_at, updated_at
            FROM survey_sessions
            ORDER BY created_at DESC
        """)
    ).mappings().all()

    headers = ["session_id", "survey_type", "submitted", "is_submitted", "current_section", "created_at", "updated_at"]
    for part in PARTS:
        for col in part["columns"]:
            headers.append(f"{part['key']}.{col}")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)

    for sess in sessions:
        row = [
            sess["id"],
            sess.get("survey_type"),
            sess.get("submitted"),
            sess.get("is_submitted"),
            sess.get("current_section"),
            sess.get("created_at"),
            sess.get("updated_at"),
        ]

        for part in PARTS:
            part_row = db.execute(
                text(f"SELECT * FROM {part['table']} WHERE session_id = :session_id ORDER BY id DESC LIMIT 1"),
                {"session_id": sess["id"]},
            ).mappings().first() or {}

            for col in part["columns"]:
                val = part_row.get(col)
                if isinstance(val, (list, dict)):
                    val = json.dumps(val, ensure_ascii=False)
                row.append(val)

        writer.writerow(row)

    buffer.seek(0)
    filename = f"rpg-community-survey-{datetime.utcnow().date().isoformat()}.csv"
    return StreamingResponse(
        iter(["\ufeff" + buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/survey/{part_key}", response_class=HTMLResponse)
def part_get(part_key: str, request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    redirect_to = part_access_redirect(sess, part_key)
    if redirect_to:
        return RedirectResponse(redirect_to, status_code=303)

    active_keys = session_active_part_keys(sess)
    part = PART_BY_KEY[part_key]
    data = read_part_data(db, session_id, part)
    current = sess.get("current_section") if sess else part_key

    progress = int(((active_keys.index(part_key) + 1) / len(active_keys)) * 100)

    def is_accessible(key: str) -> bool:
        if current == "submit":
            return True
        if current in active_keys:
            return active_keys.index(key) <= active_keys.index(current)
        return key == part_key

    return render(
        request,
        "survey/section.html",
        section=part_key,
        title=part["title"],
        questions=part["questions"],
        data=data,
        progress=progress,
        previous=previous_part(part_key, active_keys),
        active_parts=[
            {
                "key": key,
                "title": PART_BY_KEY[key]["title"],
                "is_current": key == part_key,
                "is_accessible": is_accessible(key),
            }
            for key in active_keys
        ],
    )


@app.post("/survey/{part_key}")
async def part_post(part_key: str, request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    redirect_to = part_access_redirect(sess, part_key)
    if redirect_to:
        return RedirectResponse(redirect_to, status_code=303)

    active_keys = session_active_part_keys(sess)
    part = PART_BY_KEY[part_key]
    form = await request.form()

    if part_key == "part1":
        birth_date_raw = str(form.get("birth_date", "")).strip()
        if birth_date_raw and is_under_13(birth_date_raw):
            delete_session_data(db, session_id)
            response = RedirectResponse("/survey/too-young", status_code=303)
            response.delete_cookie("session_id")
            response.delete_cookie("respondent_id_hash")
            return response

    error = validate_form(form, part)
    if error:
        progress = int(((active_keys.index(part_key) + 1) / len(active_keys)) * 100)
        data = {}

        for question in part["questions"]:
            if question["type"] == "checkbox":
                data[question["name"]] = form.getlist(question["name"])
            else:
                data[question["name"]] = str(form.get(question["name"], "")).strip()

        current = sess.get("current_section") if sess else part_key

        def is_accessible(key: str) -> bool:
            if current == "submit":
                return True
            if current in active_keys:
                return active_keys.index(key) <= active_keys.index(current)
            return key == part_key

        return render(
            request,
            "survey/section.html",
            section=part_key,
            title=part["title"],
            questions=part["questions"],
            data=data,
            progress=progress,
            previous=previous_part(part_key, active_keys),
            error=error,
            active_parts=[
                {
                    "key": key,
                    "title": PART_BY_KEY[key]["title"],
                    "is_current": key == part_key,
                    "is_accessible": is_accessible(key),
                }
                for key in active_keys
            ],
        )

    save_part(db, session_id, part, form)

    sess = get_session(db, session_id)
    if sess and sess.get("current_section") == "type":
        return RedirectResponse("/survey/type", status_code=303)

    return RedirectResponse(resume_destination(sess), status_code=303)
