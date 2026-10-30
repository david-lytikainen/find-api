from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class WaterReport(Base):
    __tablename__ = "water_reports"
    id = Column(Integer, primary_key=True)
    description = Column(String(30), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    credibility = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WaterVote(Base):
    __tablename__ = "water_votes"
    __table_args__ = (UniqueConstraint("report_id", "session_id", name="uq_water_votes_report_session"), CheckConstraint("direction in (-1, 1)", name="ck_water_votes_direction"))
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("water_reports.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String(36), nullable=False)
    direction = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
