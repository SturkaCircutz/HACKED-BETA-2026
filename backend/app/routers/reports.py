from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from ..auth import current_user
from ..config import get_settings
from ..db import Confirmation, Photo, Report, StatusEvent, Subscription, get_db
from ..schemas import (AttachPhotoIn, ConfirmIn, PhotoOut, ReportCreate, ReportDetail, ReportOut, ReportPatch,
                       StatusEventOut)
from ..services import storage
from ..services.lifecycle import set_status
from ..tools.geo import centroid

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _get(db, report_id: str) -> Report:
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404, "report not found")
    return r


def _own(r: Report, user: str) -> None:
    if r.user_id != user:
        raise HTTPException(403, "only the reporter can do this")


def photo_out(p: Photo) -> PhotoOut:
    return PhotoOut.model_validate(p).model_copy(update={"url": storage.public_url(p.key)})


def create_report(db, user: str, body: ReportCreate) -> Report:
    try:
        lat, lng = centroid(body.geometry)
    except (KeyError, ValueError, IndexError, ZeroDivisionError) as exc:
        raise HTTPException(422, f"invalid geometry: {exc}") from exc
    r = Report(user_id=user, geometry=body.geometry, lat=lat, lng=lng, story=body.story, category=body.category)
    db.add(r)
    db.flush()
    db.add(StatusEvent(report_id=r.id, status="open", note="Pin created", actor=user))
    db.add(Subscription(report_id=r.id, user_id=user))
    db.commit()
    return r


@router.get("", response_model=list[ReportOut])
def list_reports(bbox: str | None = Query(None, description="minLng,minLat,maxLng,maxLat"),
                 status: str | None = Query(None, description="comma separated"),
                 category: str | None = None, mine: bool = False,
                 user: str = Depends(current_user), db=Depends(get_db)):
    stmt = select(Report).order_by(Report.created_at.desc()).limit(500)
    if bbox:
        try:
            min_lng, min_lat, max_lng, max_lat = map(float, bbox.split(","))
        except ValueError as exc:
            raise HTTPException(422, "bbox must be minLng,minLat,maxLng,maxLat") from exc
        stmt = stmt.where(Report.lat.between(min_lat, max_lat), Report.lng.between(min_lng, max_lng))
    if status:
        stmt = stmt.where(Report.status.in_(status.split(",")))
    else:
        stmt = stmt.where(Report.status != "archived")
    if category:
        stmt = stmt.where(Report.category == category)
    if mine:
        stmt = stmt.where(Report.user_id == user)
    return db.scalars(stmt).all()


@router.post("", response_model=ReportOut, status_code=201)
def post_report(body: ReportCreate, user: str = Depends(current_user), db=Depends(get_db)):
    return create_report(db, user, body)


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: str, db=Depends(get_db)):
    r = _get(db, report_id)
    votes = dict(db.execute(select(Confirmation.vote, func.count()).where(Confirmation.report_id == r.id)
                            .group_by(Confirmation.vote)).all())
    photos = db.scalars(select(Photo).where(Photo.report_id == r.id).order_by(Photo.created_at)).all()
    return ReportDetail.model_validate(r).model_copy(update={
        "photos": [photo_out(p) for p in photos],
        "still_there": votes.get("still_there", 0), "gone": votes.get("gone", 0)})


@router.patch("/{report_id}", response_model=ReportOut)
def patch_report(report_id: str, body: ReportPatch, user: str = Depends(current_user), db=Depends(get_db)):
    r = _get(db, report_id)
    _own(r, user)
    if body.story is not None:
        r.story = body.story
    if body.category is not None:
        r.category = body.category
    if body.status is not None:
        set_status(db, r, body.status, body.note, actor=user)
    db.commit()
    return r


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str, user: str = Depends(current_user), db=Depends(get_db)):
    """Soft delete: archived pins are hidden from the map but kept in history."""
    r = _get(db, report_id)
    _own(r, user)
    set_status(db, r, "archived", "Removed by reporter", actor=user)
    db.commit()


@router.get("/{report_id}/events", response_model=list[StatusEventOut])
def report_events(report_id: str, db=Depends(get_db)):
    _get(db, report_id)
    return db.scalars(select(StatusEvent).where(StatusEvent.report_id == report_id).order_by(StatusEvent.id)).all()


@router.post("/{report_id}/confirm", response_model=ReportDetail)
def confirm(report_id: str, body: ConfirmIn, user: str = Depends(current_user), db=Depends(get_db)):
    r = _get(db, report_id)
    existing = db.scalar(select(Confirmation).where(Confirmation.report_id == r.id, Confirmation.user_id == user))
    if existing:
        existing.vote = body.vote
    else:
        db.add(Confirmation(report_id=r.id, user_id=user, vote=body.vote))
    db.flush()
    if body.vote == "gone" and r.status not in ("resolved", "archived"):
        gone = db.scalar(select(func.count()).where(Confirmation.report_id == r.id, Confirmation.vote == "gone"))
        if user == r.user_id or gone >= get_settings().gone_votes_to_resolve:
            set_status(db, r, "resolved", f"Confirmed gone ({gone} vote(s))", actor=user)
    elif body.vote == "still_there" and r.status == "resolved":
        set_status(db, r, "open", "Reopened: a user says it is still there", actor=user)
    db.commit()
    return get_report(report_id, db)


@router.post("/{report_id}/subscribe", status_code=204)
def subscribe(report_id: str, user: str = Depends(current_user), db=Depends(get_db)):
    _get(db, report_id)
    if not db.scalar(select(Subscription).where(Subscription.report_id == report_id, Subscription.user_id == user)):
        db.add(Subscription(report_id=report_id, user_id=user))
        db.commit()


@router.post("/{report_id}/photos", response_model=PhotoOut)
def attach_photo(report_id: str, body: AttachPhotoIn, user: str = Depends(current_user), db=Depends(get_db)):
    r = _get(db, report_id)
    p = db.get(Photo, body.photo_id)
    if p is None or p.user_id != user:
        raise HTTPException(404, "photo not found")
    p.report_id, p.kind = r.id, body.kind
    db.commit()
    return photo_out(p)


@router.get("/{report_id}/photos", response_model=list[PhotoOut])
def list_photos(report_id: str, db=Depends(get_db)):
    _get(db, report_id)
    return [photo_out(p) for p in db.scalars(select(Photo).where(Photo.report_id == report_id).order_by(Photo.created_at))]
