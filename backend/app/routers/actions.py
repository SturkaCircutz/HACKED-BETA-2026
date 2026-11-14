from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth import current_user
from ..db import Action, Report, get_db
from ..schemas import ActionOut, CallLogIn, EmailActionIn, EmailWebhookIn
from ..services.lifecycle import set_status
from ..tools.email import send_email

router = APIRouter(tags=["actions"])


def _report(db, report_id: str, user: str) -> Report:
    r = db.get(Report, report_id)
    if r is None or r.user_id != user:
        raise HTTPException(404, "report not found")
    return r


@router.post("/api/actions/email", response_model=ActionOut, status_code=201)
def email(body: EmailActionIn, user: str = Depends(current_user), db=Depends(get_db)):
    """Send an approved draft directly from the UI. The user's click is the approval."""
    r = _report(db, body.report_id, user)
    action_id = send_email(body.to, body.subject, body.body, body.photo_ids, r.id,
                           approved=True, user_id=user, run_id=body.run_id)
    set_status(db, r, "action_sent", f"Email sent to {body.to}", actor=user)
    db.commit()
    return db.get(Action, action_id)


@router.post("/api/actions/call-log", response_model=ActionOut, status_code=201)
def call_log(body: CallLogIn, user: str = Depends(current_user), db=Depends(get_db)):
    r = _report(db, body.report_id, user)
    outcome = body.outcome + (f" (ticket {body.ticket_number})" if body.ticket_number else "")
    a = Action(report_id=r.id, run_id=body.run_id, user_id=user, kind="call", to=body.to,
               status="logged", outcome=outcome)
    db.add(a)
    if r.status == "open":
        set_status(db, r, "action_sent", f"Called {body.to}", actor=user)
    if body.ticket_number:
        set_status(db, r, "acknowledged", f"Ticket {body.ticket_number}", actor=user)
    db.commit()
    return a


@router.get("/api/actions/{action_id}", response_model=ActionOut)
def get_action(action_id: str, user: str = Depends(current_user), db=Depends(get_db)):
    a = db.get(Action, action_id)
    if a is None or a.user_id != user:
        raise HTTPException(404, "action not found")
    return a


@router.post("/api/webhooks/email", status_code=204)
def email_webhook(body: EmailWebhookIn, db=Depends(get_db)):
    """Delivery / bounce / reply events from the mail service (normalized by the SNS adapter).
    In production, protect this route (SNS signature check or a shared secret at the ALB)."""
    a = db.get(Action, body.action_id) if body.action_id else None
    if a is None and body.provider_id:
        a = db.scalar(select(Action).where(Action.provider_id == body.provider_id))
    if a is None:
        raise HTTPException(404, "action not found")
    a.status = body.event
    if body.event == "replied":
        r = db.get(Report, a.report_id)
        if r.status in ("open", "action_sent"):
            set_status(db, r, "acknowledged", f"Reply received from {a.to}", actor="mail")
    db.commit()
