"""Pin lifecycle: open -> action_sent -> acknowledged -> resolved -> archived."""
from sqlalchemy import select

from ..db import Notification, Report, StatusEvent, Subscription


def set_status(db, report: Report, status: str, note: str = "", actor: str = "system") -> None:
    if report.status == status:
        return
    report.status = status
    db.add(StatusEvent(report_id=report.id, status=status, note=note, actor=actor))
    notify(db, report, f"Pin is now '{status}'. {note}".strip())


def notify(db, report: Report, message: str) -> None:
    users = {report.user_id} | set(db.scalars(select(Subscription.user_id).where(Subscription.report_id == report.id)))
    for uid in users:
        db.add(Notification(user_id=uid, report_id=report.id, message=message))
