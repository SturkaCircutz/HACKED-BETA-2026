"""Follow-up chat on the main thread, and branch conversations anchored to a step."""
from ..services import llm
from .context import build_context
from .runner import current_state


def reply_main(run_id: str, history: list[dict]) -> str:
    ctx = build_context(current_state(run_id), "chat")
    answer = llm.ask_text("chat", ctx, history)
    if answer:
        return answer
    last_question = str(history[-1].get("content", "")).lower() if history else ""
    if any(word in last_question for word in ("resolve", "cleaned", "finished", "close the case")):
        return ("Once the litter is actually gone, choose 'I cleaned it up' in this case or open the pin "
                "on the map and choose 'Gone'. This updates your local pin only; it does not close a separate "
                "City service request. If the issue is still there, keep the pin open.")
    response = ctx.get("eco311_advice") or {}
    steps = response.get("steps") or []
    if steps:
        return ("The live assistant is temporarily unavailable. Your saved guidance is still available:\n\n"
                + "\n".join(f"{i + 1}. {text}" for i, text in enumerate(steps[:3]))
                + "\n\nUse the map to update the pin after you take action.")
    return ("The live assistant is temporarily unavailable. Your report is still saved. "
            "Check the guidance above, or return to the map to view and update your pin.")


def reply_branch(run_id: str, anchor: dict, selection: str, history: list[dict]) -> str:
    ctx = build_context(current_state(run_id), "branch", anchor_step=anchor, selection=selection)
    answer = llm.ask_text("branch", ctx, history)
    if answer:
        return answer
    return (f"(offline mode) You asked about **{anchor['title']}**. This step reported:\n\n{anchor['content']}\n\n"
            "Set LLM_MODEL to get a real explanation of why the agent did this.")
