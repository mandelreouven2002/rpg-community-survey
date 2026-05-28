import csv
import hashlib
import io
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, engine, get_db

app = FastAPI(title="RPG Community Survey", version="2.0.0")

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


def render(request: Request, template: str, **context):
    context["request"] = request
    return templates.TemplateResponse(template, context)


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


def previous_part(key: str) -> str | None:
    i = PART_KEYS.index(key)
    return PART_KEYS[i - 1] if i > 0 else None


def next_part(key: str) -> str | None:
    i = PART_KEYS.index(key)
    return PART_KEYS[i + 1] if i + 1 < len(PART_KEYS) else None


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
    param_sql = ", ".join(f":{col}" for col in insert_columns)

    db.execute(
        text(f"INSERT INTO {table} ({col_sql}) VALUES ({param_sql})"),
        data,
    )

    nxt = next_part(part["key"])
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
                "current_section": nxt or "submit",
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
                "current_section": nxt or "submit",
                "updated_at": now(),
            },
        )

    db.commit()


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "home.html")


@app.get("/health")
def health():
    return {"ok": True, "service": "rpg-community-survey", "version": "2.0.0"}


@app.get("/survey", response_class=HTMLResponse)
def consent_get(request: Request):
    return render(request, "survey/consent.html")


@app.post("/survey/consent")
async def consent_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    if form.get("consent") != "yes":
        return RedirectResponse("/", status_code=303)

    session_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO survey_sessions
            (id, ip_hash, survey_type, submitted, is_submitted, current_section, created_at, updated_at, active_sections)
            VALUES
            (:id, :ip_hash, :survey_type, :submitted, :is_submitted, :current_section, :created_at, :updated_at, :active_sections)
        """),
        {
            "id": session_id,
            "ip_hash": hash_ip(request),
            "survey_type": "full",
            "submitted": False,
            "is_submitted": False,
            "current_section": "part1",
            "created_at": now(),
            "updated_at": now(),
            "active_sections": json.dumps(PART_KEYS, ensure_ascii=False),
        },
    )
    db.commit()

    response = RedirectResponse("/survey/part1", status_code=303)
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax")
    return response


@app.get("/survey/demographics")
def old_demographics_get():
    return RedirectResponse("/survey/part1", status_code=303)


@app.post("/survey/demographics")
def old_demographics_post():
    return RedirectResponse("/survey/part1", status_code=303)


@app.get("/survey/submit", response_class=HTMLResponse)
def submit_get(request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    sections = {}
    for part in PARTS:
        sections[part["title"]] = read_part_data(db, session_id, part)

    return render(request, "survey/submit.html", sections=sections)


@app.post("/survey/submit")
def submit_post(session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

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
    return response


@app.get("/survey/complete", response_class=HTMLResponse)
def complete_get(request: Request):
    return render(request, "survey/complete.html")


@app.post("/survey/delete")
def delete_my_data(session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    if session_id:
        for part in PARTS:
            db.execute(text(f"DELETE FROM {part['table']} WHERE session_id = :session_id"), {"session_id": session_id})
        db.execute(text("DELETE FROM survey_sessions WHERE id = :id"), {"id": session_id})
        db.commit()

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session_id")
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
    if part_key not in PART_BY_KEY:
        return RedirectResponse("/survey", status_code=303)

    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    part = PART_BY_KEY[part_key]
    data = read_part_data(db, session_id, part)
    progress = int(((PART_KEYS.index(part_key) + 1) / len(PART_KEYS)) * 100)

    return render(
        request,
        "survey/section.html",
        section=part_key,
        title=part["title"],
        questions=part["questions"],
        data=data,
        progress=progress,
        previous=previous_part(part_key),
    )


@app.post("/survey/{part_key}")
async def part_post(part_key: str, request: Request, session_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    if part_key not in PART_BY_KEY:
        return RedirectResponse("/survey", status_code=303)

    sess = get_session(db, session_id)
    if not sess:
        return RedirectResponse("/survey", status_code=303)

    part = PART_BY_KEY[part_key]
    form = await request.form()

    error = validate_form(form, part)
    if error:
        progress = int(((PART_KEYS.index(part_key) + 1) / len(PART_KEYS)) * 100)
        data = {}
        for question in part["questions"]:
            if question["type"] == "checkbox":
                data[question["name"]] = form.getlist(question["name"])
            else:
                data[question["name"]] = str(form.get(question["name"], "")).strip()

        return render(
            request,
            "survey/section.html",
            section=part_key,
            title=part["title"],
            questions=part["questions"],
            data=data,
            progress=progress,
            previous=previous_part(part_key),
            error=error,
        )

    save_part(db, session_id, part, form)

    nxt = next_part(part_key)
    if nxt:
        return RedirectResponse(f"/survey/{nxt}", status_code=303)

    return RedirectResponse("/survey/submit", status_code=303)
