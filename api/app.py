from dotenv import load_dotenv

load_dotenv()
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from api.routers import character, novel_log, run, character_context

app = FastAPI()
app.include_router(character.router)
app.include_router(novel_log.router)
app.include_router(run.router)
app.include_router(character_context.router)

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/hello")
def hello():
    return {"message": "hello world!"}
