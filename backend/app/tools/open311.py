"""open311: (jurisdiction_id, action, payload?) -> services[] | request status.

GeoReport v2 read-only calls, where a city offers an endpoint (OPEN311_ENDPOINTS).
"""
import httpx

from ..config import get_settings
from .geo import jurisdiction_chain


def open311(jurisdiction_id: str | None, action: str, payload: dict | None = None) -> dict:
    endpoints = get_settings().open311_endpoints
    base = next((endpoints[j] for j in jurisdiction_chain(jurisdiction_id) if j in endpoints), None)
    if not base:
        return {"available": False}
    try:
        if action == "services":
            r = httpx.get(f"{base}/services.json", timeout=10)
            r.raise_for_status()
            return {"available": True, "services": r.json()}
        if action == "status":
            r = httpx.get(f"{base}/requests/{(payload or {})['service_request_id']}.json", timeout=10)
            r.raise_for_status()
            return {"available": True, "request": r.json()}
    except (httpx.HTTPError, KeyError) as exc:
        return {"available": True, "error": str(exc)}
    raise ValueError(f"unknown open311 action {action}")
