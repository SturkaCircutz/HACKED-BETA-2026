"""Executes graph runs and records each step as a RunEvent (what the UI streams)."""
import logging

from langgraph.types import Command

from ..db import AgentRun, RunEvent, SessionLocal
from .graph import get_graph

log = logging.getLogger(__name__)
RESULT_KEYS = ["category", "severity", "issue_summary", "address", "jurisdiction_id", "contacts",
               "contact_source", "nearby", "action_type", "draft", "approval_status", "delivery"]


def _config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


def add_event(run_id: str, type_: str, title: str = "", content: str = "", node: str | None = None,
              data: dict | None = None) -> int:
    with SessionLocal() as db:
        ev = RunEvent(run_id=run_id, type=type_, node=node, title=title, content=content, data=data)
        db.add(ev)
        db.commit()
        return ev.id


def _set_run(run_id: str, **fields) -> None:
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        for k, v in fields.items():
            setattr(run, k, v)
        db.commit()


def _is_cancelled(run_id: str) -> bool:
    with SessionLocal() as db:
        return db.get(AgentRun, run_id).status == "cancelled"


def execute(run_id: str, payload) -> None:
    """Run (or resume) the graph until it pauses or ends. `payload` is the initial state or a Command."""
    graph = get_graph()
    try:
        for update in graph.stream(payload, _config(run_id), stream_mode="updates"):
            if _is_cancelled(run_id):
                add_event(run_id, "status", "Cancelled", "Run stopped by user.")
                return
            for node, out in update.items():
                if node == "__interrupt__":
                    value = out[0].value
                    add_event(run_id, "interrupt", "Waiting for your review",
                              "Approve, edit, or reject the draft below.", node="human_review", data=value)
                    _set_run(run_id, status="paused", result=current_result(run_id))
                    return
                for s in (out or {}).get("log", []):
                    add_event(run_id, "step", s["title"], s["content"], node=s["node"], data=s["data"])
        result = current_result(run_id)
        status = "rejected" if result.get("approval_status") == "rejected" else "done"
        _set_run(run_id, status=status, result=result)
        add_event(run_id, "status", status.capitalize(), "")
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        log.exception("run %s failed", run_id)
        _set_run(run_id, status="failed", error=str(exc))
        add_event(run_id, "error", "Run failed", str(exc))


def start(run_id: str, initial_state: dict) -> None:
    execute(run_id, {**initial_state, "run_id": run_id, "log": []})


def resume(run_id: str, decision: dict) -> None:
    _set_run(run_id, status="running")
    execute(run_id, Command(resume=decision))


def current_state(run_id: str) -> dict:
    return get_graph().get_state(_config(run_id)).values


def current_result(run_id: str) -> dict:
    values = current_state(run_id)
    return {k: values[k] for k in RESULT_KEYS if k in values}
