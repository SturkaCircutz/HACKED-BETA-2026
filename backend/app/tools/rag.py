"""rag_search: (query, jurisdiction, category, k) -> contacts[] with score, source_url, last_verified.

Retrieval = hard filter by jurisdiction (incl. parent levels) + category, then vector
similarity on the story.
"""
from sqlalchemy import select

from ..db import Contact, SessionLocal
from ..services.embeddings import cosine, embed
from .geo import jurisdiction_chain


def contact_text(c: Contact) -> str:
    return f"{c.name}. {c.category}. {c.description}"


def contact_dict(c: Contact, score: float | None = None) -> dict:
    d = {
        "id": c.id, "jurisdiction_id": c.jurisdiction_id, "category": c.category, "name": c.name,
        "description": c.description, "email": c.email, "phone": c.phone, "hours": c.hours,
        "source_url": c.source_url, "verified": bool(c.verified),
        "last_verified": c.last_verified.isoformat() if c.last_verified else None, "flags": c.flags,
    }
    if score is not None:
        d["score"] = round(score, 4)
    return d


def rag_search(query: str, jurisdiction: str | None, category: str | None, k: int = 5) -> list[dict]:
    stmt = select(Contact).where(Contact.flags < 3)
    chain = jurisdiction_chain(jurisdiction)
    if jurisdiction is not None:
        stmt = stmt.where(Contact.jurisdiction_id.in_(chain or ["__none__"]))
    if category:
        stmt = stmt.where(Contact.category.in_([category, "general"]))
    with SessionLocal() as db:
        rows = db.scalars(stmt).all()
    q = embed(query or category or "")
    scored = []
    for c in rows:
        score = cosine(q, c.embedding or [])
        score += 0.15 if c.category == category else 0.0  # exact category beats "general"
        score += 0.05 * (len(chain) - chain.index(c.jurisdiction_id)) if c.jurisdiction_id in chain else 0.0
        score -= 0.1 * c.flags
        scored.append((score, c))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [contact_dict(c, s) for s, c in scored[:k]]
