import hmac
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD, JWT_SECRET, engine
from app.dto import CommentInput, LoginInput, ThingInput, ThingLocationInput, VoteInput
from app.models import Comment, ThingLocation

router = APIRouter()
EARTH_RADIUS_METERS = 6_371_000
DUPLICATE_RADIUS_METERS = 30 * 0.3048


def haversine_meters(latitude: float, longitude: float, other_latitude: float, other_longitude: float) -> float:
    latitude_delta = math.radians(other_latitude - latitude)
    longitude_delta = math.radians(other_longitude - longitude)
    value = math.sin(latitude_delta / 2) ** 2 + math.cos(math.radians(latitude)) * math.cos(math.radians(other_latitude)) * math.sin(longitude_delta / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(value))


def report_rows(thing_id: int, latitude: float, longitude: float, limit: int | None = None, max_distance: float | None = None) -> list[dict[str, Any]]:
    if engine.dialect.name == "postgresql":
        distance = "(6371000 * acos(least(1.0, greatest(-1.0, sin(radians(:latitude)) * sin(radians(r.latitude)) + cos(radians(:latitude)) * cos(radians(r.latitude)) * cos(radians(r.longitude) - radians(:longitude))))))"
        sql = f"select r.id, r.description, r.latitude, r.longitude, r.votes, {distance} as distance_meters from things_locations r where r.thing_id = :thing_id"
        params: dict[str, Any] = {"latitude": latitude, "longitude": longitude, "thing_id": thing_id}
        if max_distance is not None:
            sql += f" and {distance} <= :max_distance"
            params["max_distance"] = max_distance
        sql += " order by distance_meters asc, r.id asc"
        if limit is not None:
            sql += " limit :limit"
            params["limit"] = limit
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(sql), params).mappings().all()]
    with engine.connect() as connection:
        rows = connection.execute(text("select r.id, r.description, r.latitude, r.longitude, r.votes from things_locations r where r.thing_id = :thing_id"), {"thing_id": thing_id}).mappings().all()
    reports = [dict(row) | {"distance_meters": haversine_meters(latitude, longitude, row["latitude"], row["longitude"])} for row in rows]
    reports.sort(key=lambda report: (report["distance_meters"], report["id"]))
    if max_distance is not None:
        reports = [report for report in reports if report["distance_meters"] <= max_distance]
    return reports[:limit] if limit is not None else reports


def admin_user(authorization: str | None) -> dict[str, str]:
    if not authorization or not authorization.startswith("Bearer ") or not JWT_SECRET:
        raise HTTPException(status_code=401, detail="Admin login required.")
    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid admin token.") from exc
    if payload.get("sub") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return {"name": ADMIN_NAME, "email": ADMIN_EMAIL}


def require_thing(thing_id: int, include_archived: bool = False) -> dict[str, Any]:
    query = "select id, name, clicks, archived from things where id = :thing_id"
    if not include_archived:
        query += " and archived = false"
    with engine.connect() as connection:
        thing = connection.execute(text(query), {"thing_id": thing_id}).mappings().first()
    if not thing:
        raise HTTPException(status_code=404, detail="Thing not found.")
    return dict(thing)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/login")
def login(payload: LoginInput) -> dict[str, Any]:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD or not JWT_SECRET:
        raise HTTPException(status_code=503, detail="Admin login is not configured.")
    if not hmac.compare_digest(payload.email, ADMIN_EMAIL) or not hmac.compare_digest(payload.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    token = jwt.encode({"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(days=365)}, JWT_SECRET, algorithm="HS256")
    return {"token": token, "user": {"name": ADMIN_NAME, "email": ADMIN_EMAIL, "role": "admin"}}


@router.get("/auth/me")
def current_admin(authorization: str | None = Header(default=None)) -> dict[str, str]:
    return admin_user(authorization) | {"role": "admin"}


@router.get("/things")
def list_things() -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        things = connection.execute(text("select id, name, clicks, archived from things where archived = false order by clicks desc, lower(name), id"))
        return {"things": [dict(thing) for thing in things.mappings().all()]}


@router.get("/admin/things")
def list_admin_things(authorization: str | None = Header(default=None)) -> dict[str, list[dict[str, Any]]]:
    admin_user(authorization)
    with engine.connect() as connection:
        things = connection.execute(text("select id, name, clicks, archived from things order by archived, lower(name), id"))
        return {"things": [dict(thing) for thing in things.mappings().all()]}


@router.post("/admin/things")
def create_thing(payload: ThingInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    admin_user(authorization)
    with engine.begin() as connection:
        if connection.execute(text("select id from things where lower(name) = lower(:name)"), {"name": payload.name}).first():
            raise HTTPException(status_code=409, detail="A thing with that name already exists.")
        connection.execute(text("insert into things (name, archived) values (:name, :archived)"), {"name": payload.name, "archived": payload.archived})
        thing_id = connection.execute(text("select id from things where lower(name) = lower(:name)"), {"name": payload.name}).scalar_one()
    return require_thing(thing_id, include_archived=True)


@router.put("/admin/things/{thing_id}")
def update_thing(thing_id: int, payload: ThingInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    admin_user(authorization)
    with engine.begin() as connection:
        if not connection.execute(text("select id from things where id = :thing_id"), {"thing_id": thing_id}).first():
            raise HTTPException(status_code=404, detail="Thing not found.")
        if connection.execute(text("select id from things where lower(name) = lower(:name) and id <> :thing_id"), {"name": payload.name, "thing_id": thing_id}).first():
            raise HTTPException(status_code=409, detail="A thing with that name already exists.")
        connection.execute(text("update things set name = :name, archived = :archived where id = :thing_id"), {"name": payload.name, "archived": payload.archived, "thing_id": thing_id})
    return require_thing(thing_id, include_archived=True)


@router.post("/things/{thing_id}/click")
def click_thing(thing_id: int) -> dict[str, int]:
    with engine.begin() as connection:
        result = connection.execute(text("update things set clicks = clicks + 1 where id = :thing_id and archived = false"), {"thing_id": thing_id})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Thing not found.")
        clicks = connection.execute(text("select clicks from things where id = :thing_id"), {"thing_id": thing_id}).scalar_one()
    return {"clicks": clicks}


@router.get("/things/{thing_id}/locations")
def list_thing_locations(thing_id: int, latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180)) -> dict[str, list[dict[str, Any]]]:
    require_thing(thing_id)
    return {"reports": report_rows(thing_id, latitude, longitude, limit=10)}


@router.post("/things/{thing_id}/locations")
def create_thing_location(thing_id: int, payload: ThingLocationInput) -> dict[str, Any]:
    require_thing(thing_id)
    duplicate = report_rows(thing_id, payload.latitude, payload.longitude, limit=1, max_distance=DUPLICATE_RADIUS_METERS)
    if duplicate and not payload.force_duplicate:
        return {"created": False, "duplicate": duplicate[0]}
    with Session(engine) as session:
        report = ThingLocation(thing_id=thing_id, description=payload.description, latitude=payload.latitude, longitude=payload.longitude, votes=0)
        session.add(report)
        session.flush()
        report_id = report.id
        session.commit()
    with engine.connect() as connection:
        created = connection.execute(text("select id, thing_id, description, latitude, longitude, votes from things_locations where id = :report_id"), {"report_id": report_id}).mappings().one()
    return {"created": True, "report": dict(created)}


@router.put("/things/locations/{report_id}/vote")
def set_thing_location_vote(report_id: int, payload: VoteInput) -> dict[str, int]:
    with engine.begin() as connection:
        result = connection.execute(text("update things_locations set votes = votes + :delta where id = :report_id"), {"delta": payload.delta, "report_id": report_id})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Thing location not found.")
        votes = connection.execute(text("select votes from things_locations where id = :report_id"), {"report_id": report_id}).scalar_one()
    return {"votes": votes}


@router.get("/comments")
def list_comments(report_id: int | None = None, page: int = Query(default=1, ge=1)) -> dict[str, Any]:
    with engine.connect() as connection:
        if report_id is not None and not connection.execute(text("select id from things_locations where id = :report_id"), {"report_id": report_id}).first():
            raise HTTPException(status_code=404, detail="Thing location not found.")
        count = connection.execute(text("select count(*) from comments where report_id = :report_id or (report_id is null and :report_id is null)"), {"report_id": report_id}).scalar_one()
        comments = connection.execute(text("select id, report_id, body, votes, created_at from comments where report_id = :report_id or (report_id is null and :report_id is null) order by votes desc, created_at asc, id asc limit :limit offset :offset"), {"report_id": report_id, "limit": 10, "offset": (page - 1) * 10}).mappings().all()
    return {"comments": [dict(comment) for comment in comments], "page": page, "page_size": 10, "total": count, "pages": math.ceil(count / 10)}


@router.post("/comments")
def create_comment(payload: CommentInput) -> dict[str, Any]:
    with Session(engine) as session:
        if payload.report_id is not None and session.get(ThingLocation, payload.report_id) is None:
            raise HTTPException(status_code=404, detail="Thing location not found.")
        comment = Comment(report_id=payload.report_id, body=payload.body, votes=0)
        session.add(comment)
        session.flush()
        comment_id = comment.id
        session.commit()
    with engine.connect() as connection:
        created = connection.execute(text("select id, report_id, body, votes, created_at from comments where id = :comment_id"), {"comment_id": comment_id}).mappings().one()
    return dict(created)


@router.put("/comments/{comment_id}/vote")
def set_comment_vote(comment_id: int, payload: VoteInput) -> dict[str, int]:
    with engine.begin() as connection:
        result = connection.execute(text("update comments set votes = votes + :delta where id = :comment_id"), {"delta": payload.delta, "comment_id": comment_id})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Comment not found.")
        votes = connection.execute(text("select votes from comments where id = :comment_id"), {"comment_id": comment_id}).scalar_one()
    return {"votes": votes}


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    admin_user(authorization)
    with engine.begin() as connection:
        result = connection.execute(text("delete from comments where id = :comment_id"), {"comment_id": comment_id})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Comment not found.")
    return {"deleted": True}
