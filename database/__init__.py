"""Small, persistent RAG index and bounded cache; no user stories are stored here."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class Store:
    """SQLite FTS5/BM25 retrieval, with a token-overlap fallback on older SQLite."""

    def __init__(self, path: str | Path | None = None,
                 knowledge_path: str | Path | None = None) -> None:
        base = Path(__file__).resolve().parent
        self.path = str(path if path is not None else
                        os.getenv("ECO311_DB_PATH", str(base / "eco311.sqlite3")))
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self.path = str(Path(self.path).expanduser())
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, category TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS api_cache (
                key TEXT PRIMARY KEY, payload TEXT NOT NULL,
                expires_at REAL NOT NULL, updated_at REAL NOT NULL);
        """)
        try:
            self._db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                USING fts5(doc_id UNINDEXED, title, body, keywords, tokenize='unicode61')""")
            self.fts_available = True
        except sqlite3.OperationalError as exc:
            if "no such module" not in str(exc).lower():
                self._db.close()
                raise
            self.fts_available = False
        try:
            self._seed(Path(knowledge_path) if knowledge_path is not None else base / "knowledge.json")
        except Exception:
            self._db.close()
            raise

    def _seed(self, path: Path) -> None:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw + str(self.fts_available).encode()).hexdigest()
        with self._lock, self._db:
            previous = self._db.execute(
                "SELECT value FROM metadata WHERE key='knowledge_hash'").fetchone()
            if previous and previous["value"] == digest:
                return
            data = json.loads(raw)
            documents = data["documents"]
            ids = [d["id"] for d in documents]
            if len(ids) != len(set(ids)):
                raise ValueError("Knowledge document IDs must be unique")
            self._db.execute("DELETE FROM documents")
            if self.fts_available:
                self._db.execute("DELETE FROM documents_fts")
            for document in documents:
                # Preserve all source fields, including future schema additions.
                payload = json.dumps(document, ensure_ascii=False, allow_nan=False)
                self._db.execute("INSERT INTO documents VALUES (?, ?, ?)",
                                 (document["id"], document["category"], payload))
                if self.fts_available:
                    self._db.execute("INSERT INTO documents_fts VALUES (?, ?, ?, ?)",
                                     (document["id"], document["title"], document["text"],
                                      " ".join(document.get("keywords", []))))
            self._db.execute("INSERT OR REPLACE INTO metadata VALUES ('knowledge_hash', ?)",
                             (digest,))

    @staticmethod
    def _tokens(text: str) -> list[str]:
        # SQL is parameterized; token quoting also removes FTS query operators.
        return list(dict.fromkeys(re.findall(r"[^\W_]+", text[:4000].lower())))[:48]

    def retrieve(self, query: str, limit: int = 4,
                 category: str | None = None) -> list[dict[str, Any]]:
        limit = max(0, min(int(limit), 20))
        if not limit:
            return []
        tokens = self._tokens(query)
        where = ""
        params: list[Any] = []
        if category is not None:
            where = " AND (d.category = ? OR d.category IN ('general', '311') OR d.id = '311')"
            params.append(category)
        with self._lock:
            if self.fts_available and tokens:
                match = " OR ".join('"' + token + '"' for token in tokens)
                rows = self._db.execute(
                    "SELECT d.payload FROM documents_fts JOIN documents d "
                    "ON d.id = documents_fts.doc_id WHERE documents_fts MATCH ?" + where +
                    " ORDER BY bm25(documents_fts, 0.0, 4.0, 1.0, 3.0), d.id LIMIT ?",
                    [match, *params, limit]).fetchall()
                if rows:
                    return [json.loads(row["payload"]) for row in rows]
            rows = self._db.execute(
                "SELECT d.payload FROM documents d WHERE 1=1" + where + " ORDER BY d.id",
                params).fetchall()
        documents = [json.loads(row["payload"]) for row in rows]
        wanted = set(tokens)

        def rank(document: dict[str, Any]) -> tuple[int, int, str]:
            content = " ".join([document["title"], document["text"],
                                *document.get("keywords", [])])
            overlap = len(wanted.intersection(self._tokens(content)))
            preferred = document["category"] == category if category else (
                document["category"] in {"general", "311"} or document["id"] == "311")
            return (-overlap, -int(preferred), document["id"])

        return sorted(documents, key=rank)[:limit]

    def document(self, doc_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT payload FROM documents WHERE id = ?",
                                   (doc_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def cache_get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock, self._db:
            row = self._db.execute("SELECT payload, expires_at FROM api_cache WHERE key = ?",
                                   (key,)).fetchone()
            if not row:
                return None
            if row["expires_at"] <= now:
                self._db.execute("DELETE FROM api_cache WHERE key = ?", (key,))
                return None
            return json.loads(row["payload"])

    def cache_set(self, key: str, value: Any, ttl_seconds: float) -> None:
        ttl_seconds = float(ttl_seconds)
        if not math.isfinite(ttl_seconds):
            raise ValueError("Cache TTL must be finite")
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
        # A single unusually large provider response must not inflate this small cache.
        if len(payload.encode("utf-8")) > 512 * 1024:
            return
        now = time.time()
        with self._lock, self._db:
            self._db.execute("DELETE FROM api_cache WHERE expires_at <= ?", (now,))
            if ttl_seconds <= 0:
                self._db.execute("DELETE FROM api_cache WHERE key = ?", (key,))
                return
            self._db.execute("INSERT OR REPLACE INTO api_cache VALUES (?, ?, ?, ?)",
                             (key, payload, now + ttl_seconds, now))
            self._db.execute("""DELETE FROM api_cache WHERE key IN
                (SELECT key FROM api_cache ORDER BY updated_at DESC, key DESC LIMIT -1 OFFSET 256)""")
            total = self._db.execute(
                "SELECT COALESCE(SUM(length(CAST(payload AS BLOB))), 0) FROM api_cache").fetchone()[0]
            while total > 8 * 1024 * 1024:
                oldest = self._db.execute("""SELECT key, length(CAST(payload AS BLOB)) AS size
                    FROM api_cache ORDER BY updated_at, key LIMIT 1""").fetchone()
                self._db.execute("DELETE FROM api_cache WHERE key = ?", (oldest["key"],))
                total -= oldest["size"]

    def close(self) -> None:
        with self._lock:
            self._db.close()
