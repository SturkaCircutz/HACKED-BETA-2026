from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..auth import current_user
from ..db import Notification, Report, get_db

router = APIRouter(tags=["account"])


@router.get("/api/me")
def me(user: str = Depends(current_user), db=Depends(get_db)):
    pins = db.execute(select(Report.status, func.count()).where(Report.user_id == user).group_by(Report.status)).all()
    notes = db.scalars(select(Notification).where(Notification.user_id == user)
                       .order_by(Notification.id.desc()).limit(30)).all()
    return {
        "user_id": user,
        "pins_by_status": dict(pins),
        "notifications": [{"id": n.id, "report_id": n.report_id, "message": n.message, "read": bool(n.read),
                           "created_at": n.created_at} for n in notes],
    }


@router.get("/healthz")
def healthz():
    return {"ok": True}
