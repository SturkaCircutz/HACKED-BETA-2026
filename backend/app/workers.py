"""Background jobs (run by a scheduler: EventBridge -> SQS -> worker container, or cron locally).

    python -m app.workers followup
"""
import sys
from datetime import timedelta

from sqlalchemy import select

from .config import get_settings
from .db import Report, SessionLocal, init_db, utcnow
from .services.lifecycle import notify


def followup_checks() -> int:
    """Ask 'still there?' for pins whose follow-up date has passed, then push it out again."""
    now = utcnow()
    with SessionLocal() as db:
        due = db.scalars(select(Report).where(Report.followup_at.is_not(None), Report.followup_at <= now,
                                              Report.status.in_(["open", "action_sent", "acknowledged"]))).all()
        for r in due:
            notify(db, r, "Is this still there? Tap 'still there' or 'gone' on the pin.")
            r.followup_at = now + timedelta(days=get_settings().followup_days)
        db.commit()
        return len(due)


if __name__ == "__main__":
    init_db()
    job = sys.argv[1] if len(sys.argv) > 1 else "followup"
    if job == "followup":
        print(f"follow-up notifications: {followup_checks()}")
