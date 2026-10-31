import hmac
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD, JWT_SECRET, engine
from app.dto import CommentInput, LoginInput, LocationInput, VoteInput, WaterReportInput
from app.models import Comment, WaterReport

router = APIRouter()
EARTH_RADIUS_METERS = 6_371_000
DUPLICATE_RADIUS_METERS = 30 * 0.3048


def haversine_meters(latitude: float, longitude: float, other_latitude: float, other_longitude: float) -> float:
    latitude_delta = math.radians(other_latitude - latitude)
    longitude_delta = math.radians(other_longitude - longitude)
    value = math.sin(latitude_delta / 2) ** 2 + math.cos(math.radians(latitude)) * math.cos(math.radians(other_latitude)) * math.sin(longitude_delta / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(value))


def report_rows(latitude: float, longitude: float, limit: int | None = None, max_distance: float | None = None) -> list[dict[str, Any]]:
    if engine.dialect.name == "postgresql":
        distance = "(6371000 * acos(least(1.0, greatest(-1.0, sin(radians(:latitude)) * sin(radians(r.latitude)) + cos(radians(:latitude)) * cos(radians(r.latitude)) * cos(radians(r.longitude) - radians(:longitude))))))"
        sql = f"select r.id, r.description, r.latitude, r.longitude, r.votes, {distance} as distance_meters from water_reports r where r.id >= :minimum_id"
        params: dict[str, Any] = {"latitude": latitude, "longitude": longitude, "minimum_id": 1}
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
        rows = connection.execute(text("select r.id, r.description, r.latitude, r.longitude, r.votes from water_reports r where r.id >= :minimum_id"), {"minimum_id": 1}).mappings().all()
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


@router.get("/water/reports")
def list_water_reports(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180)) -> dict[str, list[dict[str, Any]]]:
    return {"reports": report_rows(latitude, longitude, limit=10)}


@router.post("/water/reports")
def create_water_report(payload: WaterReportInput) -> dict[str, Any]:
    duplicate = report_rows(payload.latitude, payload.longitude, limit=1, max_distance=DUPLICATE_RADIUS_METERS)
    if duplicate and not payload.force_duplicate:
        return {"created": False, "duplicate": duplicate[0]}
    with Session(engine) as session:
        report = WaterReport(description=payload.description, latitude=payload.latitude, longitude=payload.longitude, votes=0)
        session.add(report)
        session.flush()
        report_id = report.id
        session.commit()
    with engine.connect() as connection:
        created = connection.execute(text("select id, description, latitude, longitude, votes from water_reports where id = :report_id"), {"report_id": report_id}).mappings().one()
    return {"created": True, "report": dict(created)}


@router.put("/water/reports/{report_id}/vote")
def set_water_vote(report_id: int, payload: VoteInput) -> dict[str, int]:
    with engine.begin() as connection:
        result = connection.execute(text("update water_reports set votes = votes + :delta where id = :report_id"), {"delta": payload.delta, "report_id": report_id})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Water report not found.")
        votes = connection.execute(text("select votes from water_reports where id = :report_id"), {"report_id": report_id}).scalar_one()
    return {"votes": votes}


@router.get("/water/comments")
def list_comments(report_id: int | None = None, page: int = Query(default=1, ge=1)) -> dict[str, Any]:
    with engine.connect() as connection:
        if report_id is not None and not connection.execute(text("select id from water_reports where id = :report_id"), {"report_id": report_id}).first():
            raise HTTPException(status_code=404, detail="Water report not found.")
        count = connection.execute(text("select count(*) from comments where report_id = :report_id or (report_id is null and :report_id is null)"), {"report_id": report_id}).scalar_one()
        comments = connection.execute(text("select id, report_id, body, votes, created_at from comments where report_id = :report_id or (report_id is null and :report_id is null) order by votes desc, created_at asc, id asc limit :limit offset :offset"), {"report_id": report_id, "limit": 10, "offset": (page - 1) * 10}).mappings().all()
    return {"comments": [dict(comment) for comment in comments], "page": page, "page_size": 10, "total": count, "pages": math.ceil(count / 10)}


@router.post("/water/comments")
def create_comment(payload: CommentInput) -> dict[str, Any]:
    with Session(engine) as session:
        if payload.report_id is not None and session.get(WaterReport, payload.report_id) is None:
            raise HTTPException(status_code=404, detail="Water report not found.")
        comment = Comment(report_id=payload.report_id, body=payload.body, votes=0)
        session.add(comment)
        session.flush()
        comment_id = comment.id
        session.commit()
    with engine.connect() as connection:
        created = connection.execute(text("select id, report_id, body, votes, created_at from comments where id = :comment_id"), {"comment_id": comment_id}).mappings().one()
    return dict(created)


@router.put("/water/comments/{comment_id}/vote")
def set_comment_vote(comment_id: int, payload: VoteInput) -> dict[str, int]:
    with engine.begin() as connection:
        result = connection.execute(text("update comments set votes = votes + :delta where id = :comment_id"), {"delta": payload.delta, "comment_id": comment_id})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Comment not found.")
        votes = connection.execute(text("select votes from comments where id = :comment_id"), {"comment_id": comment_id}).scalar_one()
    return {"votes": votes}


@router.delete("/water/comments/{comment_id}")
def delete_comment(comment_id: int, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    admin_user(authorization)
    with engine.begin() as connection:
        result = connection.execute(text("delete from comments where id = :comment_id"), {"comment_id": comment_id})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Comment not found.")
    return {"deleted": True}
