"""Text embeddings for the contact knowledge base.

EMBEDDING_MODEL set -> real embeddings via LangChain. Empty -> a hashing bag-of-words
vector, which is good enough to rank a few hundred filtered KB rows offline.
"""
import hashlib
import math
import re
from functools import lru_cache

from ..config import get_settings

DIM = 256


@lru_cache
def _provider():
    model = get_settings().embedding_model
    if not model:
        return None
    from langchain.embeddings import init_embeddings

    return init_embeddings(model)


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        vec[h % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> list[float]:
    p = _provider()
    return p.embed_query(text) if p else _hash_embed(text)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
