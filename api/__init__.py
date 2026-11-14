"""Bounded, read-only city/open-map clients; no report submission or email."""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit

import httpx

from database import Store

CITY_BASE = "https://311.edmonton.ca/open311/v2"
CITY_SOURCE = "https://311.edmonton.ca/"
EPL_URL = "https://data.edmonton.ca/resource/jn25-zspi.json"
BOUNDARY_URL = "https://data.edmonton.ca/resource/qqvh-dp5m.json"
BOUNDARY_SOURCE = "https://data.edmonton.ca/Administrative/City-of-Edmonton-Corporate-Boundary-current-/qqvh-dp5m"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
ORS_URL = "https://api.openrouteservice.org/v2/matrix/foot-walking/json"
PUBLIC_SORTING_SOURCE = "https://www.edmonton.ca/programs_services/garbage_waste/waste-sorting-public-space"
CHURCHILL_SQUARE_SORTING = (53.544235, -113.489876)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def _coordinates(lat, lng):
    lat, lng = _number(lat), _number(lng)
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("Latitude/longitude must be finite and in range.")
    return round(lat, 6), round(lng, 6)


def _distance(lat, lng, lat2, lng2):
    a, b = math.radians(lat), math.radians(lat2)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lng2 - lng) / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


class CityAPI:
    def __init__(self, store: Store, *, client=None, offline: bool | None = None):
        self.store, self.client = store, client
        self.offline = os.getenv("ECO311_OFFLINE") == "1" if offline is None else offline
        self._owns_client = client is None

    async def __aenter__(self):
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=6, follow_redirects=False,
                                            limits=httpx.Limits(max_connections=6, max_keepalive_connections=4))
        return self

    async def __aexit__(self, *_):
        if self._owns_client and self.client is not None:
            await self.client.aclose()
            self.client = None

    @staticmethod
    def _socrata_headers():
        token = os.getenv("SOCRATA_APP_TOKEN", "").strip()
        return {"X-App-Token": token} if token else {}

    async def _fetch(self, method, url, **kwargs):
        if self.offline:
            return None, "Offline mode: live data was not requested."
        if self.client is None:
            raise RuntimeError("Use CityAPI inside 'async with'.")
        cooldown_key = f"provider:cooldown:{urlsplit(url).hostname}"
        if self.store.cache_get(cooldown_key) is not None:
            return None, "Provider rate limit cooldown is active; retry later."
        headers = {"User-Agent": "Eco311/0.1 (hackathon; bounded public-data reads)", **kwargs.pop("headers", {})}
        try:
            async with asyncio.timeout(8):
                async with self.client.stream(method, url, headers=headers, timeout=6, follow_redirects=False, **kwargs) as response:
                    if response.status_code == 429:
                        retry = response.headers.get("Retry-After", "60")
                        seconds = _number(retry)
                        if seconds is None:
                            try:
                                when = parsedate_to_datetime(retry)
                                seconds = when.replace(tzinfo=when.tzinfo or timezone.utc).timestamp() - time.time()
                            except (TypeError, ValueError, OverflowError):
                                seconds = 60
                        seconds = max(0, seconds)
                        self.store.cache_set(cooldown_key, {"retry_after_seconds": seconds}, seconds)
                    response.raise_for_status()
                    if (_number(response.headers.get("Content-Length")) or 0) > 2_000_000:
                        return None, "Response exceeded the public-data size limit."
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        if len(body) + len(chunk) > 2_000_000:
                            return None, "Response exceeded the public-data size limit."
                        body.extend(chunk)
                    return json.loads(body), None
        except httpx.HTTPStatusError as exc:
            return None, f"HTTP {exc.response.status_code}"
        except (httpx.HTTPError, httpx.StreamError, TimeoutError):
            return None, "Network request failed or timed out."
        except (ValueError, RecursionError):
            return None, "The data provider returned invalid JSON."

    async def _cached(self, key, ttl, method, url, *, expected="list", **kwargs):
        if not self.offline:
            cached = self.store.cache_get(key)
            if isinstance(cached, dict) and "error" in cached:
                return cached.get("data"), cached["error"]
        data, error = await self._fetch(method, url, **kwargs)
        valid = isinstance(data, list) if expected == "list" else isinstance(data, dict) and isinstance(data.get("elements"), list)
        if not error and not valid:
            data, error = None, "The data provider returned an unexpected format."
        if not self.offline:
            self.store.cache_set(key, {"data": data if not error else None, "error": error}, ttl if not error else 60)
        return data, error

    async def _open311(self, path, field):
        token = os.getenv("OPEN311_API_KEY", "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data, error = await self._cached(f"open311:{path}:auth={bool(token)}", 3600 if field == "services" else 60,
                                         "GET", f"{CITY_BASE}/{path}", headers=headers)
        reason = None
        if error:
            reason = ("311 API access was denied; authentication or website protection may be involved. "
                      "Use the official 311 website or phone." if error in {"HTTP 401", "HTTP 403"}
                      else f"311 live data is unavailable ({error}). Use the official website or phone.")
        return {"available": not bool(error), field: [r for r in (data or []) if isinstance(r, dict)],
                "reason": reason, "sources": [{"title": "Edmonton 311", "url": CITY_SOURCE}],
                "warnings": [reason] if reason else []}

    async def service_catalog(self):
        result = await self._open311("services.json", "services")
        if result["available"] and not result["services"]:
            reason = "The 311 API returned no service catalog entries. Check approved API access; use the official 311 website or phone meanwhile."
            result.update(available=False, reason=reason, warnings=[reason])
        return result

    async def request_status(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id):
            return {"available": False, "requests": [], "reason": "Invalid service request ID.",
                    "sources": [], "warnings": ["Invalid service request ID."]}
        return await self._open311(f"requests/{request_id}.json", "requests")

    async def jurisdiction(self, lat, lng):
        lat, lng = _coordinates(lat, lng)
        data, error = await self._cached(
            f"boundary:{lat:.6f}:{lng:.6f}", 86400, "GET", BOUNDARY_URL,
            params={"$select": "id", "$where": f"intersects(the_geom, 'POINT({lng:.6f} {lat:.6f})')", "$limit": 1},
            headers=self._socrata_headers())
        if not error and any(not isinstance(row, dict) or "id" not in row for row in data):
            error = "Boundary data was malformed."
        return {"status": "unknown" if error else "inside" if data else "outside", "city": "Edmonton",
                "source_url": BOUNDARY_SOURCE, "warnings": [f"City boundary could not be checked: {error}"] if error else []}

    async def nearby_places(self, lat, lng, limit=3, max_walk_minutes=10):
        lat, lng = _coordinates(lat, lng)
        limit, max_walk_minutes = min(3, max(0, int(limit))), min(10, max(0, float(max_walk_minutes)))
        query = f"[out:json][timeout:5];nwr(around:850,{lat:.6f},{lng:.6f})[amenity=waste_basket];out body center 40;"
        (libraries, library_error), (osm, osm_error) = await asyncio.gather(
            self._cached("epl:branches:v1", 86400, "GET", EPL_URL,
                         params={"$limit": 100, "$select": "branch_id,branch,address,latitude,longitude"},
                         headers=self._socrata_headers()),
            self._cached(f"osm:bins:v2:{lat:.6f}:{lng:.6f}", 600, "POST", OVERPASS_URL,
                         expected="elements", data={"data": query}))
        warnings, sources, candidates = [], [], []
        if library_error:
            warnings.append(f"Library locations could not be retrieved: {library_error}")
        else:
            sources.append({"title": "Edmonton Public Library branch locations", "url": EPL_URL})
        if osm_error:
            warnings.append(f"Mapped public bins could not be retrieved: {osm_error}")
        else:
            sources.append({"title": "OpenStreetMap contributors: mapped waste baskets", "url": "https://www.openstreetmap.org/copyright"})
        for row in libraries or []:
            if isinstance(row, dict) and isinstance(row.get("branch"), str) and row["branch"].strip():
                candidates.append({"name": row["branch"].strip(), "kind": "library", "address": str(row.get("address") or ""),
                                   "lat": row.get("latitude"), "lng": row.get("longitude"), "bin_status": "not_verified",
                                   "source_url": EPL_URL, "_id": f"epl:{row.get('branch_id', row['branch'])}",
                                   "note": "Public library; bin availability, opening hours and access are unverified. Ask staff before using a bin."})
        if _distance(lat, lng, *CHURCHILL_SQUARE_SORTING) <= 800:
            candidates.append({
                "name": "Sir Winston Churchill Square / City Hall Fountain",
                "kind": "public_sorting_station", "address": "1 Sir Winston Churchill Square, Edmonton",
                "lat": CHURCHILL_SQUARE_SORTING[0], "lng": CHURCHILL_SQUARE_SORTING[1],
                "bin_status": "city_listed_sorting_station", "source_url": PUBLIC_SORTING_SOURCE,
                "_id": "city:churchill-square-public-sorting",
                "note": "City-listed public recycling, food scraps and garbage sorting station. Map pin represents the square, not the exact bin; check the station signs and current access.",
            })
            sources.append({"title": "City of Edmonton: public sorting stations", "url": PUBLIC_SORTING_SOURCE})
        for row in (osm or {}).get("elements", []):
            if not isinstance(row, dict) or not isinstance(row.get("tags"), dict):
                continue
            tags = row["tags"]
            if tags.get("amenity") != "waste_basket" or tags.get("access", "yes") not in {"yes", "public", "permissive", "designated"}:
                continue
            if tags.get("indoor") == "yes" or tags.get("waste", "") not in {"", "trash", "general", "mixed", "litter", "rubbish"}:
                continue
            point = row if "lat" in row else row.get("center", {})
            if not isinstance(point, dict) or row.get("type") not in {"node", "way", "relation"} or not str(row.get("id", "")).isdigit():
                continue
            osm_id = f"{row['type']}/{row['id']}"
            candidates.append({"name": str(tags.get("name") or "Mapped public waste basket"), "kind": "public_bin",
                               "address": str(tags.get("addr:street") or ""), "lat": point.get("lat"), "lng": point.get("lon"),
                               "bin_status": "mapped_bin", "source_url": f"https://www.openstreetmap.org/{osm_id}", "_id": osm_id,
                               "note": "Mapped bin; current condition and public access are unverified. Small incidental litter only, not household, bulky or hazardous waste."})
        nearby = []
        for place in candidates:
            try:
                place["lat"], place["lng"] = _coordinates(place["lat"], place["lng"])
            except ValueError:
                continue
            distance = _distance(lat, lng, place["lat"], place["lng"])
            if distance <= 800:
                place.update(distance_m=round(distance, 1), distance_basis="straight_line")
                nearby.append(place)
        nearby.sort(key=lambda p: p["distance_m"])
        unique, seen = [], set()
        for place in nearby:
            if place["_id"] in seen:
                continue
            seen.add(place["_id"])
            duplicate = next((i for i, p in enumerate(unique) if place["kind"] == p["kind"]
                              and (place["kind"] == "library" or place["name"].casefold() == p["name"].casefold())
                              and _distance(place["lat"], place["lng"], p["lat"], p["lng"]) < 20), None)
            if duplicate is None:
                unique.append(place)
            elif place["kind"] == "library":
                def priority(p):
                    return (p["_id"].upper() != "EPL:EPLMNA", p["_id"].upper() == "EPL:EPLMNJ"
                            or "children" in p["name"].casefold())
                if priority(place) < priority(unique[duplicate]):
                    unique[duplicate] = place
        unique.sort(key=lambda p: p["distance_m"])
        places = await self._walk(lat, lng, unique[:6], max_walk_minutes, warnings, sources)
        for place in places:
            place.pop("_id", None)
            place["maps_url"] = "https://www.google.com/maps/dir/?" + urlencode({
                "api": 1, "origin": f"{lat},{lng}", "destination": f"{place['lat']},{place['lng']}", "travelmode": "walking"})
        if len(places) < limit:
            warnings.append(f"Only {len(places)} eligible nearby location(s) were found in the available map data.")
        return {"places": places[:limit], "warnings": warnings, "sources": sources}

    async def _walk(self, lat, lng, candidates, minutes, warnings, sources):
        if not candidates:
            return []
        key = os.getenv("ORS_API_KEY", "").strip()
        matrix, error = None, None
        if key and not self.offline:
            matrix, error = await self._fetch("POST", ORS_URL, headers={"Authorization": key}, json={
                "locations": [[lng, lat], *[[p["lng"], p["lat"]] for p in candidates]],
                "sources": ["0"], "destinations": [str(i) for i in range(1, len(candidates) + 1)],
                "metrics": ["duration", "distance"], "units": "m"})
            valid = isinstance(matrix, dict) and all(
                isinstance(matrix.get(k), list) and len(matrix[k]) == 1 and isinstance(matrix[k][0], list)
                and len(matrix[k][0]) == len(candidates) for k in ("durations", "distances"))
            if not error and not valid:
                error = "Walking route data was malformed."
        if not key or self.offline or error:
            warnings.append("Walking routes are unverified; nearby suggestions use a distance-based estimate, not a confirmed ten-minute walk."
                            + (f" Routing provider: {error}" if error else ""))
            results = []
            for place in candidates:
                estimate = place["distance_m"] * 1.35 / 1.3 / 60
                if estimate <= minutes:
                    place.update(route_verified=False, walking_minutes=None, walking_minutes_estimate=round(estimate, 1),
                                 within_10_min_walk=None, walking_basis="distance_estimate")
                    results.append(place)
            return results
        sources.append({"title": "openrouteservice walking route estimates", "url": "https://openrouteservice.org/"})
        origins = matrix.get("sources")
        origin = origins[0] if isinstance(origins, list) and origins else {}
        origin_snap = _number(origin.get("snapped_distance")) if isinstance(origin, dict) else None
        origin_snap = origin_snap if origin_snap is not None and origin_snap >= 0 else None
        if origin_snap is not None and origin_snap > 100:
            warnings.append("Walking routes were excluded because the start snapped more than 100 m from the selected point.")
            return []
        destinations = matrix.get("destinations")
        destinations = destinations if isinstance(destinations, list) else []
        results = []
        for i, place in enumerate(candidates):
            duration, distance = _number(matrix["durations"][0][i]), _number(matrix["distances"][0][i])
            snap = destinations[i] if i < len(destinations) and isinstance(destinations[i], dict) else {}
            snapped = _number(snap.get("snapped_distance"))
            snapped = snapped if snapped is not None and snapped >= 0 else None
            # Null means unreachable: do not replace a known missing route with a geometric estimate.
            if duration is None or distance is None or duration < 0 or distance < 0 or (snapped is not None and snapped > 100):
                continue
            snap_allowance = (origin_snap or 0) + (snapped or 0)
            modeled_duration = duration + snap_allowance / 1.3
            if modeled_duration <= minutes * 60:
                place.update(distance_m=round(distance + snap_allowance, 1), distance_basis="walking_route", route_verified=True,
                             walking_minutes=round(modeled_duration / 60, 1), walking_minutes_estimate=None,
                             within_10_min_walk=True, walking_basis="routed_estimate", route_access_checked=False,
                             snap_distances_known=origin_snap is not None and snapped is not None)
                place["note"] += (" Walking estimate includes known endpoint snap distances; physical accessibility and weather are unchecked."
                                  if place["snap_distances_known"] else " Walking estimate has unknown endpoint snap distances; accessibility and weather are unchecked.")
                results.append(place)
        return sorted(results, key=lambda p: p["walking_minutes"])
