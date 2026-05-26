from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
import app.models.models

# יצירת הטבלאות במסד הנתונים
Base.metadata.create_all(bind=engine)

app = FastAPI(title="RPG Community Survey Israel")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/")
async def home(request: Request):
    # שימוש בתחביר המעודכן לגרסאות החדשות של FastAPI
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/survey")
async def survey(request: Request):
    return templates.TemplateResponse(request=request, name="survey.html")

@app.get("/admin")
async def admin(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")
