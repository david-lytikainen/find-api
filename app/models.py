from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Thing(Base):
    __tablename__ = "things"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    clicks = Column(Integer, nullable=False, default=0, server_default="0")
    archived = Column(Boolean, nullable=False, default=False, server_default="false")


class ThingLocation(Base):
    __tablename__ = "things_locations"
    id = Column(Integer, primary_key=True)
    thing_id = Column(Integer, ForeignKey("things.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(30), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    votes = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("things_locations.id", ondelete="CASCADE"), nullable=True)
    body = Column(String(500), nullable=False)
    votes = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
