from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI
from api.routers import character, novel_log, run, character_context

app = FastAPI()
app.include_router(character.router)
app.include_router(novel_log.router)
app.include_router(run.router)
app.include_router(character_context.router)


@app.get("/hello")
def hello():
    return {"message": "hello world!"}
