"""Request / response models for the public API."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = ["trash", "dumping", "water", "air", "noise", "graffiti", "pothole", "tree", "other"]
STATUSES = ["open", "action_sent", "acknowledged", "resolved", "archived"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReportCreate(BaseModel):
    geometry: dict  # GeoJSON Point or Polygon
    story: str = ""
    category: str = "other"


class ReportPatch(BaseModel):
    story: str | None = None
    category: str | None = None
    status: Literal["open", "action_sent", "acknowledged", "resolved", "archived"] | None = None
    note: str = ""


class ReportOut(ORM):
    id: str
    user_id: str
    geometry: dict
    lat: float
    lng: float
    story: str
    category: str
    status: str
    address: str | None
    jurisdiction_id: str | None
    followup_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PhotoOut(ORM):
    id: str
    report_id: str | None
    kind: str
    content_type: str
    analysis: dict | None
    url: str = ""
    created_at: datetime


class ReportDetail(ReportOut):
    photos: list[PhotoOut] = []
    still_there: int = 0
    gone: int = 0


class StatusEventOut(ORM):
    id: int
    status: str
    note: str
    actor: str
    created_at: datetime


class ConfirmIn(BaseModel):
    vote: Literal["still_there", "gone"]


class PresignIn(BaseModel):
    content_type: str = "image/jpeg"


class PresignOut(BaseModel):
    photo_id: str
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str] = {}


class AttachPhotoIn(BaseModel):
    photo_id: str
    kind: Literal["before", "after"] = "before"


class RunCreate(BaseModel):
    report_id: str | None = None
    # Alternative to report_id: create the pin on the fly from a region + story
    geometry: dict | None = None
    story: str = ""
    category: str | None = None
    photo_ids: list[str] = []


class RunOut(ORM):
    id: str
    report_id: str
    status: str
    result: dict | None
    error: str | None
    created_at: datetime


class RunEventOut(ORM):
    id: int
    type: str
    node: str | None
    title: str
    content: str
    data: dict | None
    created_at: datetime


class RunDetail(RunOut):
    events: list[RunEventOut] = []


class ResumeIn(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    # approve: optional final user-edited draft; edit: instructions for a redraft
    draft: dict[str, Any] | None = None
    instructions: str = ""


class MessageIn(BaseModel):
    content: str = Field(min_length=1)


class BranchCreate(BaseModel):
    anchor_event_id: int
    selection: str = ""
    question: str = Field(min_length=1)


class BranchOut(ORM):
    id: str
    run_id: str
    anchor_event_id: int
    selection: str
    title: str
    messages: list[dict]
    closed: int
    created_at: datetime


class EmailActionIn(BaseModel):
    run_id: str | None = None
    report_id: str
    to: str
    subject: str
    body: str
    photo_ids: list[str] = []


class CallLogIn(BaseModel):
    report_id: str
    run_id: str | None = None
    to: str
    outcome: str = ""
    ticket_number: str | None = None


class ActionOut(ORM):
    id: str
    report_id: str
    run_id: str | None
    kind: str
    to: str
    subject: str
    body: str
    status: str
    outcome: str | None
    created_at: datetime


class EmailWebhookIn(BaseModel):
    action_id: str | None = None
    provider_id: str | None = None
    event: Literal["delivered", "bounced", "replied"]
    detail: str = ""


class KBSearchIn(BaseModel):
    query: str
    jurisdiction_id: str | None = None
    category: str | None = None
    k: int = 5


class ContactIn(BaseModel):
    id: str | None = None
    jurisdiction_id: str
    category: str
    name: str
    description: str = ""
    email: str | None = None
    phone: str | None = None
    hours: str | None = None
    source_url: str | None = None
    verified: bool = True


class ContactOut(ORM):
    id: str
    jurisdiction_id: str
    category: str
    name: str
    description: str
    email: str | None
    phone: str | None
    hours: str | None
    source_url: str | None
    verified: int
    last_verified: datetime | None
    flags: int


class ScoredContact(ContactOut):
    score: float


class IngestIn(BaseModel):
    url: str
    jurisdiction_id: str
    category: str


class FlagIn(BaseModel):
    reason: str = ""
