"""reverse_geocode: (lat, lng | polygon) -> address, city, region, country, jurisdiction_id."""
import re

import httpx

from ..config import get_settings


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def centroid(geometry: dict) -> tuple[float, float]:
    """Return (lat, lng) for a GeoJSON Point or the vertex mean of a Polygon."""
    if geometry["type"] == "Point":
        lng, lat = geometry["coordinates"][:2]
        return float(lat), float(lng)
    if geometry["type"] == "Polygon":
        ring = geometry["coordinates"][0]
        pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
        return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)
    raise ValueError(f"unsupported geometry type {geometry['type']}")


def jurisdiction_chain(jurisdiction_id: str | None) -> list[str]:
    """'ca-ab-edmonton' -> ['ca-ab-edmonton', 'ca-ab', 'ca'] (most specific first)."""
    if not jurisdiction_id:
        return []
    parts = jurisdiction_id.split("-")
    return ["-".join(parts[:i]) for i in range(len(parts), 0, -1)]


def _unknown(lat: float, lng: float) -> dict:
    return {"address": f"{lat:.5f}, {lng:.5f}", "city": None, "region": None, "country": None, "jurisdiction_id": None}


def reverse_geocode(lat: float, lng: float) -> dict:
    s = get_settings()
    try:
        if s.google_maps_api_key:
            return _google(lat, lng, s.google_maps_api_key)
        return _nominatim(lat, lng)
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return _unknown(lat, lng)


def _nominatim(lat: float, lng: float) -> dict:
    s = get_settings()
    r = httpx.get(
        f"{s.nominatim_url}/reverse",
        params={"lat": lat, "lon": lng, "format": "jsonv2", "addressdetails": 1},
        headers={"User-Agent": s.http_user_agent},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    addr = data.get("address", {})
    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county")
    region_code = addr.get("ISO3166-2-lvl4", "")  # e.g. "CA-AB"
    country = addr.get("country_code", "")
    base = region_code.lower() if region_code else country
    jid = "-".join(p for p in [base, slug(city) if city else ""] if p) or None
    return {
        "address": data.get("display_name") or _unknown(lat, lng)["address"],
        "city": city,
        "region": addr.get("state"),
        "country": country.upper() or None,
        "jurisdiction_id": jid,
    }


def _google(lat: float, lng: float, key: str) -> dict:
    r = httpx.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"latlng": f"{lat},{lng}", "key": key},
        timeout=10,
    )
    r.raise_for_status()
    result = r.json()["results"][0]
    comp = {t: c for c in result["address_components"] for t in c["types"]}
    city = comp.get("locality", {}).get("long_name")
    region = comp.get("administrative_area_level_1", {})
    country = comp.get("country", {}).get("short_name", "")
    parts = [country.lower(), region.get("short_name", "").lower(), slug(city) if city else ""]
    return {
        "address": result["formatted_address"],
        "city": city,
        "region": region.get("long_name"),
        "country": country or None,
        "jurisdiction_id": "-".join(p for p in parts if p) or None,
    }


def forward_geocode(q: str) -> list[dict]:
    """Search box: place name -> coordinates."""
    s = get_settings()
    try:
        r = httpx.get(
            f"{s.nominatim_url}/search",
            params={"q": q, "format": "jsonv2", "limit": 5},
            headers={"User-Agent": s.http_user_agent},
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        return []
    return [{"name": d["display_name"], "lat": float(d["lat"]), "lng": float(d["lon"])} for d in r.json()]
