from fastapi import APIRouter, Query

from ..tools.geo import forward_geocode, reverse_geocode

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("/reverse")
def reverse(lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180)):
    return reverse_geocode(lat, lng)


@router.get("/search")
def search(q: str = Query(..., min_length=2)):
    return forward_geocode(q)
