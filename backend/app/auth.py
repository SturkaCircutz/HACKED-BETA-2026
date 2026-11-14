"""Authentication.

Production: Bearer JWT (e.g. issued by Cognito / Entra) verified with JWT_SECRET.
Dev mode (JWT_SECRET empty): the caller is taken from the X-User-Id header, default "demo".
"""
import jwt
from fastapi import Header, HTTPException

from .config import get_settings


def current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        return x_user_id or "demo"
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        claims = jwt.decode(
            authorization.split(" ", 1)[1],
            settings.jwt_secret,
            algorithms=["HS256", "RS256"],
            audience=settings.jwt_audience or None,
            options={"verify_aud": bool(settings.jwt_audience)},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, f"invalid token: {exc}") from exc
    return str(claims["sub"])
