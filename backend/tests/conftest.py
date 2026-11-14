import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/app.db",
    "CHECKPOINT_PATH": f"{_tmp}/cp.db",
    "UPLOAD_DIR": f"{_tmp}/uploads",
    "LLM_MODEL": "",
    "EMBEDDING_MODEL": "",
    "TAVILY_API_KEY": "",
    "JWT_SECRET": "",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db as dbmod  # noqa: E402
from app.main import app  # noqa: E402

EDMONTON = {"address": "Whyte Ave, Edmonton, Alberta", "city": "Edmonton", "region": "Alberta",
            "country": "CA", "jurisdiction_id": "ca-ab-edmonton"}


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    dbmod.Base.metadata.drop_all(dbmod.engine)
    dbmod.Base.metadata.create_all(dbmod.engine)
    monkeypatch.setattr("app.agent.nodes.reverse_geocode", lambda lat, lng: dict(EDMONTON))
    yield


@pytest.fixture
def client():
    return TestClient(app, headers={"X-User-Id": "alice"})


def point(lng=-113.5, lat=53.52):
    return {"type": "Point", "coordinates": [lng, lat]}
