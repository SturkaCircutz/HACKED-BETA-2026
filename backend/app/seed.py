"""Load seed contacts into the knowledge base.

    python -m app.seed [path/to/contacts.json]

Seed rows are stored UNVERIFIED: confirm each one against its source_url (then set
verified=true via POST /api/kb/contacts) before relying on it.
"""
import json
import sys
from pathlib import Path

from sqlalchemy import select

from .db import Contact, SessionLocal, init_db
from .services.embeddings import embed
from .tools.rag import contact_text


def load(path: Path) -> int:
    init_db()
    rows = json.loads(path.read_text())
    added = 0
    with SessionLocal() as db:
        for row in rows:
            exists = db.scalar(select(Contact).where(Contact.jurisdiction_id == row["jurisdiction_id"],
                                                     Contact.category == row["category"], Contact.name == row["name"],
                                                     Contact.phone == row.get("phone")))
            if exists:
                continue
            c = Contact(**row, verified=0)
            c.embedding = embed(contact_text(c))
            db.add(c)
            added += 1
        db.commit()
    return added


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / "seed" / "contacts.json"
    print(f"added {load(Path(sys.argv[1]) if len(sys.argv) > 1 else default)} contacts")
