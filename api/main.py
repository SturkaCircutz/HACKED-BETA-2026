"""Optional local test API. The existing app can mount router with its own auth.

The teammate's /api/agent/runs route is unchanged; see agent/README.md to connect it.
"""
import hmac
import os

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException

from agent import ReportInput, analyze_report

router = APIRouter(prefix="/api/agent", tags=["Eco311 recommendations"])


async def require_api_key(x_eco311_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("ECO311_API_KEY", "")
    if expected and (x_eco311_key is None or not hmac.compare_digest(x_eco311_key, expected)):
        raise HTTPException(status_code=401, detail="A valid X-Eco311-Key is required.")


@router.post("/analyze")
async def analyze(body: ReportInput) -> dict:
    ai_response = await analyze_report(**body.model_dump())
    return {"ai_response": ai_response}


app = FastAPI(title="Eco311 Agent", version="1.0.0")
app.include_router(router, dependencies=[Depends(require_api_key)])


@app.get("/healthz")
def health() -> dict:
    return {"status": "ok", "service": "eco311-agent", "direct_submission_enabled": False}
