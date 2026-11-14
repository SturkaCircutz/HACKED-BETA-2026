import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from ..auth import current_user
from ..db import AgentRun, Branch, Photo, Report, RunEvent, SessionLocal, get_db
from ..schemas import (BranchCreate, BranchOut, MessageIn, ReportCreate, ResumeIn, RunCreate, RunDetail,
                       RunEventOut, RunOut)
from ..agent import chat, runner
from .reports import create_report

router = APIRouter(prefix="/api/agent", tags=["agent"])
TERMINAL = {"paused", "done", "rejected", "failed", "cancelled"}


def _run(db, run_id: str, user: str) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None or run.user_id != user:
        raise HTTPException(404, "run not found")
    return run


@router.post("/runs", response_model=RunOut, status_code=201)
def start_run(body: RunCreate, bg: BackgroundTasks, user: str = Depends(current_user), db=Depends(get_db)):
    if body.report_id:
        report = db.get(Report, body.report_id)
        if report is None:
            raise HTTPException(404, "report not found")
    elif body.geometry:
        report = create_report(db, user, ReportCreate(geometry=body.geometry, story=body.story,
                                                      category=body.category or "other"))
    else:
        raise HTTPException(422, "report_id or geometry is required")
    for pid in body.photo_ids:  # photos uploaded before the pin existed
        p = db.get(Photo, pid)
        if p and p.user_id == user and p.report_id is None:
            p.report_id = report.id
    photo_ids = list(db.scalars(select(Photo.id).where(Photo.report_id == report.id, Photo.kind == "before")))
    run = AgentRun(user_id=user, report_id=report.id, status="running")
    db.add(run)
    db.commit()
    runner.add_event(run.id, "message", "You", report.story or "(no story)", node="user",
                     data={"role": "user", "photo_ids": photo_ids})
    bg.add_task(runner.start, run.id, {
        "user_id": user, "report_id": report.id, "story": body.story or report.story,
        "category": body.category or report.category, "geometry": report.geometry,
        "lat": report.lat, "lng": report.lng, "photo_ids": photo_ids})
    return run


@router.get("/runs", response_model=list[RunOut])
def list_runs(report_id: str, user: str = Depends(current_user), db=Depends(get_db)):
    return db.scalars(select(AgentRun).where(AgentRun.report_id == report_id, AgentRun.user_id == user)
                      .order_by(AgentRun.created_at.desc())).all()


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, user: str = Depends(current_user), db=Depends(get_db)):
    run = _run(db, run_id, user)
    events = db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.id)).all()
    return RunDetail.model_validate(run).model_copy(update={"events": [RunEventOut.model_validate(e) for e in events]})


@router.get("/runs/{run_id}/stream")
async def stream(run_id: str, request: Request, after: int = 0, user: str = Depends(current_user)):
    """SSE: replays events after `after`, then pushes new ones until the run pauses or ends."""
    with SessionLocal() as db:
        _run(db, run_id, user)

    async def gen():
        last = after
        while not await request.is_disconnected():
            with SessionLocal() as db:
                events = db.scalars(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.id > last)
                                    .order_by(RunEvent.id)).all()
                status = db.get(AgentRun, run_id).status
            for e in events:
                last = e.id
                yield f"id: {e.id}\nevent: {e.type}\ndata: {RunEventOut.model_validate(e).model_dump_json()}\n\n"
            if status in TERMINAL:
                yield f"event: end\ndata: {json.dumps({'status': status})}\n\n"
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/runs/{run_id}/resume", response_model=RunOut)
def resume(run_id: str, body: ResumeIn, bg: BackgroundTasks, user: str = Depends(current_user), db=Depends(get_db)):
    run = _run(db, run_id, user)
    if run.status != "paused":
        raise HTTPException(409, f"run is {run.status}, not paused")
    run.status = "running"
    db.commit()
    bg.add_task(runner.resume, run_id, body.model_dump())
    return run


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel(run_id: str, user: str = Depends(current_user), db=Depends(get_db)):
    run = _run(db, run_id, user)
    if run.status not in ("done", "rejected", "failed"):
        run.status = "cancelled"
        db.commit()
    return run


@router.post("/threads/{run_id}/messages", response_model=list[RunEventOut])
def thread_message(run_id: str, body: MessageIn, user: str = Depends(current_user), db=Depends(get_db)):
    """Follow-up chat on the same case (the main conversation)."""
    _run(db, run_id, user)
    prior = db.scalars(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.type == "message",
                                              RunEvent.node.in_(["user", "assistant"])).order_by(RunEvent.id)).all()
    history = [{"role": "user" if e.node == "user" else "assistant", "content": e.content} for e in prior[1:]]
    history.append({"role": "user", "content": body.content})
    q_id = runner.add_event(run_id, "message", "You", body.content, node="user", data={"role": "user"})
    answer = chat.reply_main(run_id, history)
    a_id = runner.add_event(run_id, "message", "Assistant", answer, node="assistant", data={"role": "assistant"})
    return [RunEventOut.model_validate(db.get(RunEvent, i)) for i in (q_id, a_id)]


# ---- Branches (split workspace) ----------------------------------------------------------------
@router.get("/runs/{run_id}/branches", response_model=list[BranchOut])
def list_branches(run_id: str, user: str = Depends(current_user), db=Depends(get_db)):
    _run(db, run_id, user)
    return db.scalars(select(Branch).where(Branch.run_id == run_id).order_by(Branch.created_at)).all()


@router.post("/runs/{run_id}/branches", response_model=BranchOut, status_code=201)
def create_branch(run_id: str, body: BranchCreate, user: str = Depends(current_user), db=Depends(get_db)):
    _run(db, run_id, user)
    anchor = db.get(RunEvent, body.anchor_event_id)
    if anchor is None or anchor.run_id != run_id:
        raise HTTPException(404, "anchor step not found")
    n = db.scalar(select(func.count()).select_from(Branch).where(Branch.run_id == run_id))
    branch = Branch(run_id=run_id, anchor_event_id=anchor.id, selection=body.selection,
                    title=f"Branch {chr(ord('A') + n % 26)}", messages=[])
    return _branch_turn(db, branch, anchor, body.question, new=True)


@router.post("/branches/{branch_id}/messages", response_model=BranchOut)
def branch_message(branch_id: str, body: MessageIn, user: str = Depends(current_user), db=Depends(get_db)):
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(404, "branch not found")
    _run(db, branch.run_id, user)
    return _branch_turn(db, branch, db.get(RunEvent, branch.anchor_event_id), body.content)


@router.patch("/branches/{branch_id}", response_model=BranchOut)
def close_branch(branch_id: str, closed: bool = True, user: str = Depends(current_user), db=Depends(get_db)):
    """Close != delete: a closed branch is hidden from the tab bar but kept."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(404, "branch not found")
    _run(db, branch.run_id, user)
    branch.closed = int(closed)
    db.commit()
    return branch


def _branch_turn(db, branch: Branch, anchor: RunEvent, question: str, new: bool = False) -> Branch:
    history = [*branch.messages, {"role": "user", "content": question}]
    answer = chat.reply_branch(branch.run_id, {"title": anchor.title, "content": anchor.content, "node": anchor.node,
                                               "data": anchor.data}, branch.selection, history)
    branch.messages = [*history, {"role": "assistant", "content": answer}]  # reassign so JSON change is tracked
    if new:
        db.add(branch)
    db.commit()
    return branch
