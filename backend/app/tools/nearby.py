"""nearby_reports: (geometry, radius_m, status?) -> reports[] for duplicate check + context."""
import math

from sqlalchemy import select

from ..db import Report, SessionLocal
from .geo import centroid


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby_reports(geometry: dict, radius_m: float, status: list[str] | None = None, exclude_id: str | None = None) -> list[dict]:
    lat, lng = centroid(geometry)
    dlat = radius_m / 111_320
    dlng = radius_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    stmt = select(Report).where(
        Report.lat.between(lat - dlat, lat + dlat),
        Report.lng.between(lng - dlng, lng + dlng),
        Report.status != "archived",
    )
    if status:
        stmt = stmt.where(Report.status.in_(status))
    with SessionLocal() as db:
        rows = db.scalars(stmt).all()
    out = []
    for r in rows:
        if r.id == exclude_id:
            continue
        d = haversine_m(lat, lng, r.lat, r.lng)
        if d <= radius_m:
            out.append({"id": r.id, "category": r.category, "status": r.status, "story": r.story[:200],
                        "distance_m": round(d), "created_at": r.created_at.isoformat()})
    return sorted(out, key=lambda x: x["distance_m"])
