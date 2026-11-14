"""Follow-up chat on the main thread, and branch conversations anchored to a step."""
import json

from ..services import llm
from .context import build_context
from .runner import current_state


def reply_main(run_id: str, history: list[dict]) -> str:
    ctx = build_context(current_state(run_id), "chat")
    answer = llm.ask_text("chat", ctx, history)
    if answer:
        return answer
    return ("(offline mode) Here is where this case stands:\n\n```json\n"
            + json.dumps({k: ctx.get(k) for k in ("category", "address", "action_type", "approval_status")}, indent=2)
            + "\n```\nSet LLM_MODEL to get a full answer.")


def reply_branch(run_id: str, anchor: dict, selection: str, history: list[dict]) -> str:
    ctx = build_context(current_state(run_id), "branch", anchor_step=anchor, selection=selection)
    answer = llm.ask_text("branch", ctx, history)
    if answer:
        return answer
    return (f"(offline mode) You asked about **{anchor['title']}**. This step reported:\n\n{anchor['content']}\n\n"
            "Set LLM_MODEL to get a real explanation of why the agent did this.")
