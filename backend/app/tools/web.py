"""web_search (fallback): (query, allowed_domains?) -> results[] with title, url, snippet.

Uses Tavily when TAVILY_API_KEY is set; otherwise returns no results.
"""
import re

import httpx

from ..config import get_settings

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b|\b311\b")


def web_search(query: str, allowed_domains: list[str] | None = None) -> list[dict]:
    key = get_settings().tavily_api_key
    if not key:
        return []
    body = {"query": query, "max_results": 5, "search_depth": "basic"}
    if allowed_domains:
        body["include_domains"] = allowed_domains
    try:
        r = httpx.post("https://api.tavily.com/search", json=body,
                       headers={"Authorization": f"Bearer {key}"}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError:
        return []
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")}
            for x in r.json().get("results", [])]


def extract_contacts(text: str) -> dict:
    """Pull emails / phone numbers verbatim out of text. Never guesses."""
    return {"emails": sorted(set(EMAIL_RE.findall(text))), "phones": sorted(set(m.strip() for m in PHONE_RE.findall(text)))}


def is_official(url: str) -> bool:
    """Official city / agency pages only: .gov, .gc.ca, provincial/state, or city domains."""
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    return bool(re.search(r"(\.gov(\.[a-z]{2})?|\.gc\.ca|\.ca\.gov|\.(ab|bc|on|qc|mb|sk|ns|nb|nl|pe)\.ca|"
                          r"^(www\.)?[a-z-]+\.ca|\.city|cityof[a-z-]+\.(org|com|net)|\.gov\.uk)$", host))
