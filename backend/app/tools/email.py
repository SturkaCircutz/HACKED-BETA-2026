"""send_email: (to, subject, body, photo_ids, report_id) -> action_id.

Deterministic tool: never rewrites content, never decides. Blocked unless the caller
passes approved=True (human approval in the graph, or a user click in the UI).
"""
import logging

from ..config import get_settings
from ..db import Action, Photo, SessionLocal
from ..services import storage

log = logging.getLogger(__name__)


class NotApproved(Exception):
    pass


def send_email(to: str, subject: str, body: str, photo_ids: list[str], report_id: str, *,
               approved: bool, user_id: str, run_id: str | None = None) -> str:
    if not approved:
        raise NotApproved("send_email is blocked until the user approves the draft")
    s = get_settings()
    with SessionLocal() as db:
        photos = [p for p in (db.get(Photo, pid) for pid in photo_ids) if p]
        full_body = body
        if photos:
            full_body += "\n\nPhotos:\n" + "\n".join(storage.public_url(p.key) for p in photos)
        action = Action(report_id=report_id, run_id=run_id, user_id=user_id, kind="email",
                        to=to, subject=subject, body=full_body, status="queued")
        db.add(action)
        db.flush()
        if s.email_backend == "ses":
            import boto3

            resp = boto3.client("ses", region_name=s.aws_region).send_email(
                Source=s.email_from,
                Destination={"ToAddresses": [to]},
                Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": full_body}}},
                Tags=[{"Name": "action_id", "Value": action.id}],
            )
            action.provider_id = resp["MessageId"]
        else:
            log.info("EMAIL (console) to=%s subject=%s\n%s", to, subject, full_body)
            action.provider_id = f"console-{action.id}"
        action.status = "sent"
        db.commit()
        return action.id
