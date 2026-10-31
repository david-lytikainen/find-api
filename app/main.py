from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import uvicorn

from app.config import CORS_ORIGIN_LIST, engine
from app.models import Base
from app.routes import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    with engine.begin() as connection:
        connection.execute(text("drop table if exists water_votes"))
        columns = {row["name"] for row in connection.execute(text("pragma table_info(water_reports)")).mappings()} if engine.dialect.name == "sqlite" else {row["column_name"] for row in connection.execute(text("select column_name from information_schema.columns where table_name = 'water_reports'")).mappings()}
        if "credibility" in columns and "votes" not in columns:
            connection.execute(text("alter table water_reports rename column credibility to votes"))
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="find-api", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGIN_LIST, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router, prefix="/api")
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
