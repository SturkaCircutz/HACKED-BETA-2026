import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import account, actions, agent, geo, kb, reports, uploads

logging.basicConfig(level=logging.INFO)
settings = get_settings()
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(os.path.dirname(os.path.abspath(settings.checkpoint_path)), exist_ok=True)
init_db()

app = FastAPI(title="Eco311 API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
                   allow_credentials=True)
for r in (reports, geo, uploads, agent, actions, kb, account):
    app.include_router(r.router)

# Single-container demo deploy: serve the built frontend from the same origin as the API.
# Mounted last so /api/* and /healthz keep priority.
if os.getenv("STATIC_DIR") and os.path.isdir(os.environ["STATIC_DIR"]):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=os.environ["STATIC_DIR"], html=True), name="web")
