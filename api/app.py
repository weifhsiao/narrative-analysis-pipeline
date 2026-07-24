from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI
from api.routers import character, novel_log, run

app = FastAPI()
app.include_router(character.router)
app.include_router(novel_log.router)
app.include_router(run.router)


@app.get("/hello")
def hello():
    return {"message": "hello world!"}
