import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import engine
from app.dto import LocationInput, VoteInput, WaterReportInput
from app.models import WaterReport

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
        sql = f"select r.id, r.description, r.latitude, r.longitude, r.credibility, {distance} as distance_meters from water_reports r where r.id >= :minimum_id"
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
        rows = connection.execute(text("select r.id, r.description, r.latitude, r.longitude, r.credibility from water_reports r where r.id >= :minimum_id"), {"minimum_id": 1}).mappings().all()
    reports = [dict(row) | {"distance_meters": haversine_meters(latitude, longitude, row["latitude"], row["longitude"])} for row in rows]
    reports.sort(key=lambda report: (report["distance_meters"], report["id"]))
    if max_distance is not None:
        reports = [report for report in reports if report["distance_meters"] <= max_distance]
    return reports[:limit] if limit is not None else reports


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/water/reports")
def list_water_reports(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180)) -> dict[str, list[dict[str, Any]]]:
    return {"reports": report_rows(latitude, longitude, limit=10)}


@router.post("/water/reports")
def create_water_report(payload: WaterReportInput) -> dict[str, Any]:
    duplicate = report_rows(payload.latitude, payload.longitude, limit=1, max_distance=DUPLICATE_RADIUS_METERS)
    if duplicate and not payload.force_duplicate:
        return {"created": False, "duplicate": duplicate[0]}
    with Session(engine) as session:
        report = WaterReport(description=payload.description, latitude=payload.latitude, longitude=payload.longitude, credibility=0)
        session.add(report)
        session.flush()
        report_id = report.id
        session.commit()
    with engine.connect() as connection:
        created = connection.execute(text("select id, description, latitude, longitude, credibility from water_reports where id = :report_id"), {"report_id": report_id}).mappings().one()
    return {"created": True, "report": dict(created)}


@router.put("/water/reports/{report_id}/vote")
def set_water_vote(report_id: int, payload: VoteInput) -> dict[str, int]:
    with engine.begin() as connection:
        result = connection.execute(text("update water_reports set credibility = credibility + :delta where id = :report_id"), {"delta": payload.delta, "report_id": report_id})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Water report not found.")
        credibility = connection.execute(text("select credibility from water_reports where id = :report_id"), {"report_id": report_id}).scalar_one()
    return {"credibility": credibility}
