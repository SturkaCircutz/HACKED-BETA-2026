"""Provider-agnostic LLM access. The provider is chosen by LLM_MODEL ("openai:...", "anthropic:...").

Every caller must handle `get_chat_model() is None` with a deterministic fallback so the
app runs end to end without any API key.
"""
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from ..config import get_settings

log = logging.getLogger(__name__)
PROMPT_DIR = Path(__file__).resolve().parent.parent / "agent" / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text()


@lru_cache
def get_chat_model(kind: str = "chat"):
    settings = get_settings()
    model = (settings.vision_model or settings.llm_model) if kind == "vision" else settings.llm_model
    if not model:
        return None
    from langchain.chat_models import init_chat_model

    return init_chat_model(model, temperature=0.2)


def _parse_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def ask_json(prompt_name: str, context: dict, images: list[str] | None = None) -> dict | None:
    """Call the LLM with an agent system prompt + JSON context; return the parsed JSON reply.

    Returns None when no model is configured or the call fails, so callers fall back.
    """
    llm = get_chat_model("vision" if images else "chat")
    if llm is None:
        return None
    from langchain_core.messages import HumanMessage, SystemMessage

    content: list | str = json.dumps(context, default=str, ensure_ascii=False)
    if images:
        content = [{"type": "text", "text": content}] + [
            {"type": "image_url", "image_url": {"url": url}} for url in images
        ]
    try:
        reply = llm.invoke([SystemMessage(load_prompt(prompt_name)), HumanMessage(content=content)])
        return _parse_json(reply.text if hasattr(reply, "text") and isinstance(reply.text, str) else str(reply.content))
    except Exception:  # noqa: BLE001 - any provider error -> fallback path
        log.exception("LLM call failed for %s", prompt_name)
        return None


def ask_text(prompt_name: str, context: dict, history: list[dict]) -> str | None:
    """Free-text chat turn (used by branches and follow-up chat)."""
    llm = get_chat_model()
    if llm is None:
        return None
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    msgs = [SystemMessage(load_prompt(prompt_name) + "\n\nCONTEXT:\n" + json.dumps(context, default=str, ensure_ascii=False))]
    for m in history:
        msgs.append(HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"]))
    try:
        reply = llm.invoke(msgs)
        return reply.content if isinstance(reply.content, str) else str(reply.content)
    except Exception:  # noqa: BLE001
        log.exception("LLM chat failed for %s", prompt_name)
        return None
