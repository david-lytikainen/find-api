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
        if engine.dialect.name == "sqlite":
            tables = {row["name"] for row in connection.execute(text("select name from sqlite_master where type = 'table'")).mappings()}
        else:
            tables = {row["table_name"] for row in connection.execute(text("select table_name from information_schema.tables where table_schema = current_schema()")).mappings()}
        if "water_reports" in tables and "things_locations" not in tables:
            connection.execute(text("drop table if exists comments"))
            connection.execute(text("drop table water_reports"))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("insert into things (name) select 'Water' where not exists (select 1 from things where lower(name) = 'water')"))
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="find-api", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGIN_LIST, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router, prefix="/api")
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
