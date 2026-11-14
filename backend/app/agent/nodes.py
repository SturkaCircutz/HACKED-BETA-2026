"""Graph nodes. Fixed pipeline: intake -> geo_resolve -> (retrieve_contacts || nearby_reports)
-> draft_action -> human_review (pause) -> deliver -> track."""
from datetime import timedelta

from langgraph.types import interrupt

from ..config import get_settings
from ..db import Contact, Report, SessionLocal, StatusEvent, utcnow
from ..services import llm
from ..services.embeddings import embed
from ..tools.email import send_email
from ..tools.geo import reverse_geocode
from ..tools.nearby import nearby_reports as nearby_tool
from ..tools.open311 import open311
from ..tools.photo import analyze_photo
from ..tools.rag import contact_dict, contact_text, rag_search
from ..tools.web import extract_contacts, is_official, web_search
from .context import build_context
from .state import ReportState

KEYWORDS = {
    "dumping": ["dump", "mattress", "couch", "furniture", "tires", "illegal"],
    "trash": ["trash", "garbage", "litter", "bin", "overflow", "waste", "bags"],
    "water": ["water", "leak", "flood", "sewer", "drain", "river", "creek", "spill"],
    "air": ["smoke", "smell", "odor", "odour", "fumes", "dust", "burning"],
    "noise": ["noise", "loud", "music", "construction noise", "barking"],
    "graffiti": ["graffiti", "tag", "spray paint"],
    "pothole": ["pothole", "road damage", "crack"],
    "tree": ["tree", "branch", "fallen"],
}


def step(node: str, title: str, content: str, **data) -> dict:
    return {"node": node, "title": title, "content": content, "data": data}


# 1 ------------------------------------------------------------------------------------------
def intake(state: ReportState) -> dict:
    findings = [analyze_photo(pid) for pid in state.get("photo_ids", [])]
    state = {**state, "photo_findings": findings}
    out = llm.ask_json("intake", build_context(state, "intake"))
    if not out:
        text = (state.get("story", "") + " " + " ".join(f.get("issue_type") or "" for f in findings)).lower()
        guessed = next((c for c, words in KEYWORDS.items() if any(w in text for w in words)), None)
        category = state.get("category") if state.get("category") not in (None, "", "other") else (guessed or "other")
        out = {"category": category, "severity": "medium", "summary": state.get("story", "")[:200] or f"{category} issue"}
    content = f"Classified as **{out['category']}** (severity: {out.get('severity', 'medium')}). {out.get('summary', '')}"
    if findings:
        content += f"\n\nAnalyzed {len(findings)} photo(s)."
    return {
        "photo_findings": findings,
        "category": out["category"],
        "severity": out.get("severity", "medium"),
        "issue_summary": out.get("summary", ""),
        "log": [step("intake", "Understand the report", content, findings=findings)],
    }


# 2 ------------------------------------------------------------------------------------------
def geo_resolve(state: ReportState) -> dict:
    geo = reverse_geocode(state["lat"], state["lng"])
    with SessionLocal() as db:
        r = db.get(Report, state["report_id"])
        r.address, r.jurisdiction_id, r.category = geo["address"], geo["jurisdiction_id"], state["category"]
        db.commit()
    content = f"Location: {geo['address']}\n\nJurisdiction: `{geo['jurisdiction_id'] or 'unknown'}`"
    return {**{k: geo[k] for k in ("address", "city", "jurisdiction_id")},
            "log": [step("geo_resolve", "Resolve location", content, **geo)]}


# 3a -----------------------------------------------------------------------------------------
def retrieve_contacts(state: ReportState) -> dict:
    """RAG first, official web pages second. New web contacts are stored as 'unverified'."""
    query = f"{state.get('category')} {state.get('issue_summary', '')} {state.get('story', '')}"
    contacts = rag_search(query, state.get("jurisdiction_id"), state.get("category"), k=5)
    source = "kb"
    usable = [c for c in contacts if c["email"] or c["phone"]]
    if not usable:
        contacts, source = _web_fallback(state), "web"
        usable = contacts
    if not usable:
        source = "none"
    o311 = open311(state.get("jurisdiction_id"), "services")
    if usable:
        top = usable[0]
        content = (f"Best match ({source.upper()}{'' if top['verified'] else ', unverified'}): **{top['name']}**"
                   f"\n\n- email: {top['email'] or '—'}\n- phone: {top['phone'] or '—'}\n- hours: {top['hours'] or '—'}"
                   f"\n- source: {top['source_url'] or '—'}")
    else:
        content = "No contact found in the knowledge base or on official pages."
    return {"contacts": usable, "contact_source": source, "open311": o311,
            "log": [step("retrieve_contacts", "Find who to contact", content, contacts=usable, source=source,
                         open311_available=o311.get("available", False))]}


def _web_fallback(state: ReportState) -> list[dict]:
    place = state.get("city") or state.get("address") or ""
    results = web_search(f"{place} report {state.get('category')} environment contact email phone")
    found: list[dict] = []
    with SessionLocal() as db:
        for res in results:
            if not is_official(res["url"]):
                continue
            ext = extract_contacts(res["snippet"])
            if not ext["emails"] and not ext["phones"]:
                continue
            c = Contact(jurisdiction_id=state.get("jurisdiction_id") or "unknown", category=state.get("category") or "other",
                        name=res["title"][:200], description=res["snippet"][:500],
                        email=(ext["emails"] or [None])[0], phone=(ext["phones"] or [None])[0],
                        source_url=res["url"], verified=0)
            c.embedding = embed(contact_text(c))
            db.add(c)
            db.flush()
            found.append(contact_dict(c, 0.0))
        db.commit()
    return found


# 3b -----------------------------------------------------------------------------------------
def nearby_reports(state: ReportState) -> dict:
    found = nearby_tool(state["geometry"], get_settings().nearby_radius_m, exclude_id=state["report_id"])
    same = [r for r in found if r["category"] == state.get("category")]
    content = (f"{len(found)} other pin(s) within {get_settings().nearby_radius_m} m"
               + (f", {len(same)} possibly duplicate (same category)." if same else ". No duplicates."))
    return {"nearby": found, "log": [step("nearby_reports", "Check nearby reports", content, nearby=found)]}


# 4 ------------------------------------------------------------------------------------------
def draft_action(state: ReportState) -> dict:
    try:
        from agent import analyze_report_sync
        ai_response = analyze_report_sync(
            story=state.get("story", ""),
            lat=state["lat"], lng=state["lng"],
            report_id=state.get("report_id"),
            review_feedback=state.get("review_feedback", ""),
        )
    except Exception:
        import logging
        from .guidance_fallback import fallback_guidance
        logging.getLogger(__name__).exception("Zero Hero action assessment unavailable")
        ai_response = fallback_guidance(state)
    contacts = state.get("contacts", [])
    top = contacts[0] if contacts else None
    assistance_needed = (ai_response or {}).get("assessment", {}).get("requires_311")
    action_type = "email" if top and top.get("email") and assistance_needed is not False else "call"
    ctx = build_context({**state, "action_type": action_type}, "draft_action",
                        contact={"name": top["name"], "hours": top.get("hours")} if top else None)
    out = llm.ask_json("draft_action", ctx) or {}

    if action_type == "email":
        draft = {
            "to": top["email"], "to_name": top["name"], "contact_verified": top["verified"],
            "subject": out.get("subject") or _fallback_subject(state),
            "body": out.get("body") or _fallback_body(state),
            "photo_ids": state.get("photo_ids", []),
        }
        content = f"**To:** {draft['to_name']} <{draft['to']}>\n\n**Subject:** {draft['subject']}\n\n{draft['body']}"
    else:
        phone = top["phone"] if top else None
        name = top["name"] if top else "your city's non-emergency / 311 line"
        draft = {
            "phone": phone, "contact_name": name, "hours": top.get("hours") if top else None,
            "contact_verified": bool(top and top["verified"]),
            "script": out.get("script") or _fallback_script(state, name),
        }
        content = (f"**Call:** {name} {phone or '(number not found — check your city website)'}\n\n"
                   + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(draft["script"])))
    title = "Draft email" if action_type == "email" else "Draft call script"
    if state.get("review_feedback"):
        title += " (revised)"
    return {"action_type": action_type, "draft": draft, "approval_status": "awaiting", "review_feedback": "",
            "ai_response": ai_response,
            "log": [step("draft_action", title, content, draft=draft, action_type=action_type)]}


def _fallback_subject(state: ReportState) -> str:
    return f"{state.get('category', 'Environmental').capitalize()} issue reported at {state.get('address', 'my location')[:80]}"


def _fallback_body(state: ReportState) -> str:
    dup = [r for r in state.get("nearby", []) if r["category"] == state.get("category")]
    lines = [
        "Hello,",
        "",
        f"I would like to report a {state.get('category', 'environmental')} issue.",
        "",
        f"Location: {state.get('address')} ({state['lat']:.5f}, {state['lng']:.5f})",
        f"What I saw: {state.get('story') or state.get('issue_summary')}",
    ]
    if state.get("photo_ids"):
        lines.append(f"Photos: {len(state['photo_ids'])} attached below.")
    if dup:
        lines.append(f"Other residents have reported {len(dup)} similar issue(s) nearby.")
    lines += ["", "Could you let me know whether this can be addressed, and share a reference number if one is created?",
              "", "Thank you."]
    return "\n".join(lines)


def _fallback_script(state: ReportState, name: str) -> list[str]:
    return [
        f"Call {name} and say you want to report a {state.get('category')} issue.",
        f"Give the location: {state.get('address')}.",
        f"Describe it: {state.get('story') or state.get('issue_summary')}",
        "Mention you have photos and ask where to send them.",
        "Ask for a ticket / reference number and write it down.",
        "Log the call in this app so the pin can be tracked.",
    ]


# 5 ------------------------------------------------------------------------------------------
def human_review(state: ReportState) -> dict:
    if state.get("action_type") != "email":
        return {"approval_status": "not_required",
                "log": [step("human_review", "Guidance ready", "Your plan is ready. No call or City request has been made.")]}
    decision = interrupt({"type": "human_review", "action_type": state["action_type"], "draft": state["draft"]})
    kind = decision.get("decision")
    if kind == "approve":
        draft = {**state["draft"], **(decision.get("draft") or {})}
        return {"approval_status": "approved", "draft": draft,
                "log": [step("human_review", "Approved by you", "You approved the draft.")]}
    if kind == "edit":
        text = decision.get("instructions", "")
        return {"approval_status": "edit_requested", "review_feedback": text,
                "log": [step("human_review", "Edit requested", f"You asked for changes: {text}")]}
    if kind == "continue":
        return {"approval_status": "skipped",
                "log": [step("human_review", "Continue without sending", "Your guidance is saved. No email will be sent.")]}
    raise ValueError("Choose approve, edit, or continue.")


def route_after_review(state: ReportState) -> str:
    return {"approved": "deliver", "not_required": "deliver", "skipped": "deliver",
            "edit_requested": "draft_action"}.get(state.get("approval_status"), "__end__")


# 6 ------------------------------------------------------------------------------------------
def deliver(state: ReportState) -> dict:
    draft = state["draft"]
    if state.get("approval_status") == "skipped":
        delivery = {"kind": "guidance", "status": "ready"}
        return {"delivery": delivery,
                "log": [step("deliver", "Plan saved", "Guidance only. Nothing was sent to an external service.", **delivery)]}
    if state["action_type"] == "email":
        action_id = send_email(draft["to"], draft["subject"], draft["body"], draft.get("photo_ids", []),
                               state["report_id"], approved=state.get("approval_status") == "approved",
                               user_id=state["user_id"], run_id=state["run_id"])
        sent = get_settings().email_backend == "ses"
        delivery = {"kind": "email", "action_id": action_id, "status": "sent" if sent else "preview"}
        content = f"Email sent to {draft['to']}." if sent else "Email prepared in console mode. No external email was sent."
    else:
        # Calls are never placed by the agent: the UI shows the number + script.
        delivery = {"kind": "call", "status": "ready", "phone": draft.get("phone")}
        content = f"Ready to call {draft.get('phone') or draft['contact_name']}. Log the outcome when you're done."
    return {"delivery": delivery, "log": [step("deliver", "Deliver", content, **delivery)]}


# 7 ------------------------------------------------------------------------------------------
def track(state: ReportState) -> dict:
    days = get_settings().followup_days
    with SessionLocal() as db:
        r = db.get(Report, state["report_id"])
        r.followup_at = utcnow() + timedelta(days=days)
        if state["delivery"]["kind"] == "email" and state["delivery"].get("status") == "sent" and r.status == "open":
            r.status = "action_sent"
            db.add(StatusEvent(report_id=r.id, status="action_sent", note=f"Email sent to {state['draft']['to']}",
                               actor="agent"))
        db.commit()
    return {"log": [step("track", "Track the pin", "Your local pin is available on the map. Mark it as cleaned only after the issue is actually resolved.")]}
