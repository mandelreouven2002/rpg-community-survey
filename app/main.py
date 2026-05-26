from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
import app.models.models  # ייבוא חובה כדי שסנכרון הטבלאות יעבוד

# יצירת הטבלאות במסד הנתונים (אם הן עדיין לא קיימות)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="RPG Community Survey Israel")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/survey")
async def survey(request: Request):
    return templates.TemplateResponse("survey.html", {"request": request})

@app.get("/admin")
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})
