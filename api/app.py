from fastapi import FastAPI
from fastapi.responses import FileResponse
from util.paths import REPO_DIR
from api.routers import character, novel_log, run, character_context

app = FastAPI()
app.include_router(character.router)
app.include_router(novel_log.router)
app.include_router(run.router)
app.include_router(character_context.router)

WEB_DIR = REPO_DIR / "web"


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/hello")
def hello():
    return {"message": "hello world!"}
