from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select

from ..auth import current_user
from ..db import Contact, IngestJob, SessionLocal, get_db, utcnow
from ..schemas import ContactIn, ContactOut, FlagIn, IngestIn, KBSearchIn, ScoredContact
from ..services.embeddings import embed
from ..tools.rag import contact_text, rag_search

router = APIRouter(prefix="/api/kb", tags=["knowledge base"])


@router.post("/search", response_model=list[ScoredContact])
def search(body: KBSearchIn):
    return rag_search(body.query, body.jurisdiction_id, body.category, body.k)


@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(jurisdiction: str | None = None, category: str | None = None, db=Depends(get_db)):
    stmt = select(Contact).order_by(Contact.jurisdiction_id, Contact.category)
    if jurisdiction:
        stmt = stmt.where(Contact.jurisdiction_id == jurisdiction)
    if category:
        stmt = stmt.where(Contact.category == category)
    return db.scalars(stmt).all()


@router.post("/contacts", response_model=ContactOut)
def upsert_contact(body: ContactIn, user: str = Depends(current_user), db=Depends(get_db)):
    """Add or update a contact (admin). Add an admin check here once roles exist."""
    c = db.get(Contact, body.id) if body.id else None
    if c is None:
        c = Contact()
        db.add(c)
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(c, k, v)
    c.verified = int(body.verified)
    c.last_verified = utcnow() if body.verified else None
    c.flags = 0 if body.verified else c.flags or 0
    c.embedding = embed(contact_text(c))
    db.commit()
    return c


@router.post("/ingest", status_code=202)
def ingest(body: IngestIn, bg: BackgroundTasks, user: str = Depends(current_user), db=Depends(get_db)):
    job = IngestJob(url=body.url, jurisdiction_id=body.jurisdiction_id, category=body.category)
    db.add(job)
    db.commit()
    bg.add_task(run_ingest, job.id)
    return {"job_id": job.id, "status": job.status}


@router.get("/ingest/{job_id}")
def ingest_status(job_id: str, db=Depends(get_db)):
    job = db.get(IngestJob, job_id)
    if job is None:
        raise HTTPException(404)
    return {"job_id": job.id, "status": job.status, "result": job.result}


@router.post("/contacts/{contact_id}/flag", response_model=ContactOut)
def flag(contact_id: str, body: FlagIn, user: str = Depends(current_user), db=Depends(get_db)):
    """A user reports a wrong email or number. 3+ flags hide the row from retrieval."""
    c = db.get(Contact, contact_id)
    if c is None:
        raise HTTPException(404)
    c.flags += 1
    c.verified = 0
    db.commit()
    return c


def run_ingest(job_id: str) -> None:
    """Fetch a page and store any emails / phones found on it as unverified contacts."""
    import httpx

    from ..config import get_settings
    from ..tools.web import extract_contacts

    with SessionLocal() as db:
        job = db.get(IngestJob, job_id)
        job.status = "running"
        db.commit()
        try:
            r = httpx.get(job.url, headers={"User-Agent": get_settings().http_user_agent}, timeout=20,
                          follow_redirects=True)
            r.raise_for_status()
            import re

            text = re.sub(r"<[^>]+>", " ", r.text)
            title = (re.search(r"<title>(.*?)</title>", r.text, re.S | re.I) or [None, job.url])[1].strip()[:200]
            found = extract_contacts(text)
            for email in found["emails"][:10]:
                c = Contact(jurisdiction_id=job.jurisdiction_id, category=job.category, name=title, email=email,
                            source_url=job.url, verified=0, description=f"Ingested from {job.url}")
                c.embedding = embed(contact_text(c))
                db.add(c)
            for phone in found["phones"][:10]:
                c = Contact(jurisdiction_id=job.jurisdiction_id, category=job.category, name=title, phone=phone,
                            source_url=job.url, verified=0, description=f"Ingested from {job.url}")
                c.embedding = embed(contact_text(c))
                db.add(c)
            job.status, job.result = "done", found
        except Exception as exc:  # noqa: BLE001
            job.status, job.result = "failed", {"error": str(exc)}
        db.commit()
