import pytest

from app.tools.email import NotApproved, send_email
from tests.conftest import point


def add_contact(client, **kw):
    body = {"jurisdiction_id": "ca-ab-edmonton", "category": "trash", "name": "Waste Services",
            "description": "litter and overflowing bins", "verified": True, **kw}
    return client.post("/api/kb/contacts", json=body).json()


def start(client, story="Overflowing garbage bags and litter by the bus stop", **kw):
    r = client.post("/api/agent/runs", json={"geometry": point(), "story": story, **kw})
    assert r.status_code == 201, r.text
    return client.get(f"/api/agent/runs/{r.json()['id']}").json()


def nodes(run):
    return [e["node"] for e in run["events"] if e["type"] == "step"]


def test_email_path_pauses_then_sends_after_approval(client):
    add_contact(client, email="waste@example.org")
    run = start(client)
    assert run["status"] == "paused"
    assert nodes(run)[:2] == ["intake", "geo_resolve"]
    assert {"retrieve_contacts", "nearby_reports"} <= set(nodes(run))
    assert nodes(run)[-1] == "draft_action"
    assert run["events"][-1]["type"] == "interrupt"
    assert run["result"]["action_type"] == "email"
    assert run["result"]["draft"]["to"] == "waste@example.org"
    report_id = run["report_id"]
    assert client.get(f"/api/reports/{report_id}").json()["status"] == "open"  # nothing sent yet

    r = client.post(f"/api/agent/runs/{run['id']}/resume",
                    json={"decision": "approve", "draft": {"subject": "Edited subject"}})
    assert r.status_code == 200
    run = client.get(f"/api/agent/runs/{run['id']}").json()
    assert run["status"] == "done"
    assert nodes(run)[-2:] == ["deliver", "track"]
    action = client.get(f"/api/actions/{run['result']['delivery']['action_id']}").json()
    assert action["subject"] == "Edited subject" and action["status"] == "sent"
    report = client.get(f"/api/reports/{report_id}").json()
    assert report["status"] == "action_sent" and report["followup_at"]


def test_edit_redrafts_and_reject_sends_nothing(client):
    add_contact(client, email="waste@example.org")
    run = start(client)
    client.post(f"/api/agent/runs/{run['id']}/resume", json={"decision": "edit", "instructions": "shorter"})
    run = client.get(f"/api/agent/runs/{run['id']}").json()
    assert run["status"] == "paused"
    assert nodes(run).count("draft_action") == 2
    client.post(f"/api/agent/runs/{run['id']}/resume", json={"decision": "reject"})
    run = client.get(f"/api/agent/runs/{run['id']}").json()
    assert run["status"] == "rejected"
    assert "delivery" not in run["result"]
    assert client.get(f"/api/reports/{run['report_id']}").json()["status"] == "open"


def test_resume_requires_paused(client):
    add_contact(client, email="waste@example.org")
    run = start(client)
    client.post(f"/api/agent/runs/{run['id']}/resume", json={"decision": "reject"})
    assert client.post(f"/api/agent/runs/{run['id']}/resume", json={"decision": "approve"}).status_code == 409


def test_call_path_and_call_log(client):
    add_contact(client, category="general", name="City 311", phone="311", email=None)
    run = start(client)
    assert run["result"]["action_type"] == "call"
    assert run["result"]["draft"]["phone"] == "311"
    client.post(f"/api/agent/runs/{run['id']}/resume", json={"decision": "approve"})
    run = client.get(f"/api/agent/runs/{run['id']}").json()
    assert run["result"]["delivery"] == {"kind": "call", "status": "ready", "phone": "311"}
    assert client.get(f"/api/reports/{run['report_id']}").json()["status"] == "open"  # not called yet
    client.post("/api/actions/call-log", json={"report_id": run["report_id"], "to": "311",
                                               "outcome": "logged", "ticket_number": "T-1"})
    events = [e["status"] for e in client.get(f"/api/reports/{run['report_id']}/events").json()]
    assert events == ["open", "action_sent", "acknowledged"]


def test_no_contact_gives_generic_call_script(client):
    run = start(client)
    assert run["result"]["contact_source"] == "none"
    assert run["result"]["draft"]["phone"] is None
    assert run["result"]["draft"]["script"]


def test_send_email_blocked_without_approval():
    with pytest.raises(NotApproved):
        send_email("a@b.c", "s", "b", [], "r1", approved=False, user_id="alice")


def test_branches_anchor_to_steps(client):
    add_contact(client, email="waste@example.org")
    run = start(client)
    anchor = next(e for e in run["events"] if e["node"] == "retrieve_contacts")
    r = client.post(f"/api/agent/runs/{run['id']}/branches",
                    json={"anchor_event_id": anchor["id"], "selection": "Waste Services", "question": "Why this one?"})
    assert r.status_code == 201
    b = r.json()
    assert b["title"] == "Branch A" and len(b["messages"]) == 2
    b = client.post(f"/api/agent/branches/{b['id']}/messages", json={"content": "Any alternative?"}).json()
    assert len(b["messages"]) == 4
    client.post(f"/api/agent/runs/{run['id']}/branches",
                json={"anchor_event_id": anchor["id"], "question": "again"})
    client.patch(f"/api/agent/branches/{b['id']}?closed=true")
    branches = client.get(f"/api/agent/runs/{run['id']}/branches").json()
    assert [x["title"] for x in branches] == ["Branch A", "Branch B"]
    assert branches[0]["closed"] == 1  # closed, not deleted
    # main conversation is untouched by branches
    assert len(client.get(f"/api/agent/runs/{run['id']}").json()["events"]) == len(run["events"])


def test_followup_chat_on_main_thread(client):
    add_contact(client, email="waste@example.org")
    run = start(client)
    out = client.post(f"/api/agent/threads/{run['id']}/messages", json={"content": "What's next?"}).json()
    assert [e["node"] for e in out] == ["user", "assistant"]


def test_nearby_duplicates_detected(client):
    add_contact(client, email="waste@example.org")
    client.post("/api/reports", json={"geometry": point(-113.5001, 53.5201), "story": "bags", "category": "trash"})
    client.post("/api/reports", json={"geometry": point(-113.6, 53.6), "story": "far", "category": "trash"})
    run = start(client, category="trash")
    assert len(run["result"]["nearby"]) == 1
    assert "similar issue" in run["result"]["draft"]["body"]


def test_photo_upload_and_attach(client):
    pre = client.post("/api/uploads/presign", json={"content_type": "image/png"}).json()
    path = pre["upload_url"].split("8000", 1)[1]
    assert client.put(path, content=b"\x89PNG fake", headers=pre["headers"]).status_code == 204
    report = client.post("/api/reports", json={"geometry": point(), "story": "x"}).json()
    client.post(f"/api/reports/{report['id']}/photos", json={"photo_id": pre["photo_id"], "kind": "after"})
    photos = client.get(f"/api/reports/{report['id']}/photos").json()
    assert photos[0]["kind"] == "after"
    assert client.get(path).content == b"\x89PNG fake"


def test_polygon_region_and_bbox_query(client):
    poly = {"type": "Polygon", "coordinates": [[[-113.51, 53.51], [-113.49, 53.51], [-113.49, 53.53], [-113.51, 53.51]]]}
    r = client.post("/api/reports", json={"geometry": poly, "story": "dumped tires"}).json()
    assert round(r["lat"], 3) == 53.517
    inside = client.get("/api/reports", params={"bbox": "-113.6,53.4,-113.4,53.6"}).json()
    outside = client.get("/api/reports", params={"bbox": "0,0,1,1"}).json()
    assert len(inside) == 1 and outside == []


def test_lifecycle_votes_and_soft_delete(client):
    report = client.post("/api/reports", json={"geometry": point(), "story": "x"}).json()
    bob = {"X-User-Id": "bob"}
    carol = {"X-User-Id": "carol"}
    client.post(f"/api/reports/{report['id']}/confirm", json={"vote": "gone"}, headers=bob)
    assert client.get(f"/api/reports/{report['id']}").json()["status"] == "open"
    d = client.post(f"/api/reports/{report['id']}/confirm", json={"vote": "gone"}, headers=carol).json()
    assert d["status"] == "resolved" and d["gone"] == 2
    d = client.post(f"/api/reports/{report['id']}/confirm", json={"vote": "still_there"}, headers=bob).json()
    assert d["status"] == "open"
    assert client.delete(f"/api/reports/{report['id']}", headers=bob).status_code == 403
    assert client.delete(f"/api/reports/{report['id']}").status_code == 204
    assert client.get("/api/reports").json() == []
    assert client.get(f"/api/reports/{report['id']}").json()["status"] == "archived"
    assert client.get("/api/me").json()["notifications"]


def test_email_webhook_reply_acknowledges(client):
    report = client.post("/api/reports", json={"geometry": point(), "story": "x"}).json()
    a = client.post("/api/actions/email", json={"report_id": report["id"], "to": "w@example.org",
                                                "subject": "s", "body": "b"}).json()
    assert client.post("/api/webhooks/email", json={"action_id": a["id"], "event": "replied"}).status_code == 204
    assert client.get(f"/api/reports/{report['id']}").json()["status"] == "acknowledged"


def test_kb_search_filters_jurisdiction_and_flags(client):
    c = add_contact(client, email="waste@example.org")
    add_contact(client, jurisdiction_id="us-ny-new-york", email="nyc@example.org")
    hits = client.post("/api/kb/search", json={"query": "litter", "jurisdiction_id": "ca-ab-edmonton",
                                               "category": "trash"}).json()
    assert [h["email"] for h in hits] == ["waste@example.org"]
    for _ in range(3):
        client.post(f"/api/kb/contacts/{c['id']}/flag", json={})
    assert client.post("/api/kb/search", json={"query": "litter", "jurisdiction_id": "ca-ab-edmonton"}).json() == []


def test_seed_loads_unverified(tmp_path):
    from pathlib import Path

    from app.seed import load

    path = Path(__file__).resolve().parent.parent / "seed" / "contacts.json"
    assert load(path) == 4
    assert load(path) == 0  # idempotent


def test_followup_worker(client):
    from datetime import timedelta

    from app.db import Report, SessionLocal, utcnow
    from app.workers import followup_checks

    report = client.post("/api/reports", json={"geometry": point(), "story": "x"}).json()
    with SessionLocal() as db:
        db.get(Report, report["id"]).followup_at = utcnow() - timedelta(days=1)
        db.commit()
    assert followup_checks() == 1
    assert followup_checks() == 0
