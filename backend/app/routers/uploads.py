import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from ..auth import current_user
from ..db import Photo, get_db
from ..schemas import PresignIn, PresignOut
from ..services import storage

router = APIRouter(prefix="/api/uploads", tags=["photos"])
ALLOWED = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic"}
MAX_BYTES = 15 * 1024 * 1024


@router.post("/presign", response_model=PresignOut)
def presign(body: PresignIn, user: str = Depends(current_user), db=Depends(get_db)):
    if body.content_type not in ALLOWED:
        raise HTTPException(415, f"content type must be one of {sorted(ALLOWED)}")
    photo = Photo(user_id=user, key="", content_type=body.content_type)
    db.add(photo)
    db.flush()
    photo.key = f"photos/{photo.id}.{ALLOWED[body.content_type]}"
    db.commit()
    url, headers = storage.presign_put(photo.key, body.content_type)
    return PresignOut(photo_id=photo.id, upload_url=url, headers=headers)


# Local-storage stand-ins for S3 presigned PUT / GET (dev only).
@router.put("/local/photos/{name}", status_code=204)
async def local_put(name: str, request: Request):
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file too large")
    path = storage.local_path(f"photos/{name}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


@router.get("/local/photos/{name}")
def local_get(name: str):
    path = storage.local_path(f"photos/{name}")
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path)
