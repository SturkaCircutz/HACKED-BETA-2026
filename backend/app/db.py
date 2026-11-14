"""SQLAlchemy engine, session and ORM models.

Geometry is stored as GeoJSON plus a centroid (lat/lng) so the same schema runs on
SQLite (dev) and Postgres (prod). Swap to PostGIS / pgvector columns when the data
outgrows in-process filtering.
"""
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex[:16]


class Base(DeclarativeBase):
    pass


class Report(Base):
    """A pin on the map."""

    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String, index=True)
    geometry: Mapped[dict] = mapped_column(JSON)  # GeoJSON Point or Polygon
    lat: Mapped[float] = mapped_column(Float, index=True)
    lng: Mapped[float] = mapped_column(Float, index=True)
    story: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String, default="other", index=True)
    status: Mapped[str] = mapped_column(String, default="open", index=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    jurisdiction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StatusEvent(Base):
    __tablename__ = "status_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    status: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Confirmation(Base):
    """'still there' / 'gone' vote from any user."""

    __tablename__ = "confirmations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    user_id: Mapped[str] = mapped_column(String)
    vote: Mapped[str] = mapped_column(String)  # still_there | gone
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    report_id: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("reports.id"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String)  # object storage key
    content_type: Mapped[str] = mapped_column(String, default="image/jpeg")
    kind: Mapped[str] = mapped_column(String, default="before")  # before | after
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Contact(Base):
    """Knowledge-base row: who to contact for a jurisdiction + category."""

    __tablename__ = "kb_contacts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    jurisdiction_id: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)  # agency / department name
    description: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    hours: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    verified: Mapped[int] = mapped_column(Integer, default=1)
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    flags: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)


class IngestJob(Base):
    __tablename__ = "kb_ingest_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    url: Mapped[str] = mapped_column(String)
    jurisdiction_id: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)  # also the thread_id
    user_id: Mapped[str] = mapped_column(String, index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="running")  # running|paused|done|rejected|failed|cancelled
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunEvent(Base):
    """One step of the main conversation. Each step is anchorable by a branch."""

    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    type: Mapped[str] = mapped_column(String)  # step | message | interrupt | status | error
    node: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Branch(Base):
    """A side conversation anchored to one step of the main conversation."""

    __tablename__ = "branches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    anchor_event_id: Mapped[int] = mapped_column(ForeignKey("run_events.id"))
    selection: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String, default="")
    messages: Mapped[list] = mapped_column(JSON, default=list)
    closed: Mapped[int] = mapped_column(Integer, default=0)  # close != delete
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Action(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    user_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # email | call
    to: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="queued")  # queued|sent|delivered|bounced|replied|logged
    provider_id: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_settings = get_settings()
if _settings.database_url.startswith("sqlite:///"):
    os.makedirs(os.path.dirname(_settings.database_url.removeprefix("sqlite:///")) or ".", exist_ok=True)
engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # Several containers (API replicas, worker) start at once: serialize schema creation.
            conn.execute(text("SELECT pg_advisory_xact_lock(311311)"))
        Base.metadata.create_all(conn)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
