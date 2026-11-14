"""analyze_photo: (photo_id) -> issue_type, severity, description (vision model)."""
import base64
import os

from ..config import get_settings
from ..db import Photo, SessionLocal
from ..services import llm, storage


def _image_url(photo: Photo) -> str | None:
    if get_settings().storage_backend == "s3":
        return storage.public_url(photo.key)
    path = storage.local_path(photo.key)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:  # local dev: model can't reach localhost, so inline the bytes
        return f"data:{photo.content_type};base64,{base64.b64encode(f.read()).decode()}"


def analyze_photo(photo_id: str) -> dict:
    with SessionLocal() as db:
        photo = db.get(Photo, photo_id)
        if photo is None:
            return {"photo_id": photo_id, "error": "not found"}
        url = _image_url(photo)
        result = llm.ask_json("analyze_photo", {"photo_id": photo_id}, images=[url]) if url else None
        result = result or {"issue_type": None, "severity": "unknown", "description": ""}
        photo.analysis = result
        db.commit()
    return {"photo_id": photo_id, **result}
