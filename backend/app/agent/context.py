"""Context Engineer: decides what each agent actually needs to see.

Agents consume context; this module owns context construction. Nodes never pass the
full state to an LLM.
"""
from .state import ReportState

AGENT_FIELDS: dict[str, list[str]] = {
    "intake": ["story", "category", "photo_findings"],
    "draft_action": ["issue_summary", "category", "severity", "story", "address", "photo_findings",
                     "nearby", "action_type", "review_feedback"],
    "chat": ["issue_summary", "category", "severity", "address", "jurisdiction_id", "contacts",
             "contact_source", "nearby", "action_type", "draft", "approval_status", "delivery"],
    "branch": ["issue_summary", "category", "address", "jurisdiction_id", "contact_source", "action_type"],
}
MAX_LIST = 5
MAX_STR = 1500


def _trim(value):
    if isinstance(value, str):
        return value[:MAX_STR]
    if isinstance(value, list):
        return [_trim(v) for v in value[:MAX_LIST]]
    if isinstance(value, dict):
        return {k: _trim(v) for k, v in value.items() if k != "embedding"}
    return value


def build_context(state: ReportState, target_agent: str, **extra) -> dict:
    ctx = {k: _trim(state[k]) for k in AGENT_FIELDS[target_agent] if state.get(k) not in (None, "", [], {})}
    if target_agent in {"chat", "branch"} and state.get("ai_response"):
        response = state["ai_response"]
        ctx["eco311_advice"] = _trim({
            "summary": response.get("summary"),
            "assessment": response.get("assessment"),
            "steps": response.get("steps"),
            "nearby_places": response.get("nearby_places", []),
            "reporting": {k: response.get("reporting", {}).get(k)
                          for k in ("requires_311", "requires_311_reason", "submitted", "url", "phone")},
        })
    ctx.update({k: _trim(v) for k, v in extra.items()})
    return ctx
