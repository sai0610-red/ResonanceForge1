"""Lexical retrieval over document chunks: a small pure-Python BM25 (Okapi).

No embeddings model and no extra dependency. BM25 is a reasonable baseline for
SOPs and system notes, which use the same vocabulary as the checklist and the
situation text. The `Retriever` interface is the swap point for a dense index.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be but by can do for from has have how i if in into is it
    its of on or our so that the their them then there these they this to was we were
    what when where which who will with you your not no yes all any each per than""".split()
)


def tokenize(text: str) -> list[str]:
    return [
        t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS and len(t) > 1
    ]


@dataclass(frozen=True)
class IndexedChunk:
    doc_label: str  # "D1"
    filename: str
    chunk: int  # 1-based
    text: str

    @property
    def ref(self) -> str:
        return f"{self.doc_label}:C{self.chunk}"


@dataclass(frozen=True)
class Hit:
    item: IndexedChunk
    score: float


class Retriever:
    """BM25 over a fixed set of chunks. Build once per assessment; cheap to rebuild."""

    def __init__(self, chunks: Sequence[IndexedChunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self._tfs = [Counter(tokenize(c.text)) for c in self.chunks]
        self._lens = [sum(tf.values()) for tf in self._tfs]
        self._avgdl = (sum(self._lens) / len(self._lens)) if self._lens else 0.0
        df: Counter[str] = Counter()
        for tf in self._tfs:
            df.update(tf.keys())
        n = len(self.chunks)
        # BM25+ style idf floor: never negative, so very common terms just add little.
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def __len__(self) -> int:
        return len(self.chunks)

    def search(self, query: str, k: int = 4) -> list[Hit]:
        terms = set(tokenize(query))
        if not terms or not self.chunks or k <= 0:
            return []
        hits: list[Hit] = []
        for item, tf, dl in zip(self.chunks, self._tfs, self._lens):
            score = 0.0
            for t in terms:
                f = tf.get(t)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1.0))
                score += self._idf.get(t, 0.0) * f * (self.k1 + 1) / denom
            if score > 0:
                hits.append(Hit(item=item, score=score))
        # Stable tie-break on document order so results are deterministic.
        order = {id(c): i for i, c in enumerate(self.chunks)}
        hits.sort(key=lambda h: (-h.score, order[id(h.item)]))
        return hits[:k]


def build_query(*parts: str | None, extra: Iterable[str] = ()) -> str:
    return " ".join([p for p in parts if p] + [e for e in extra if e])


def format_passages(hits: Sequence[Hit]) -> str:
    """Prompt block. Labels are the only valid citation targets for this call."""
    if not hits:
        return ""
    lines = [
        "Customer documents (retrieved passages). When a claim relies on a passage, "
        "cite it inline as [D1:C2] using only the labels below. Never invent a label. "
        "If the passages do not support a claim, do not cite.",
    ]
    for h in hits:
        lines.append(f"\n[{h.item.ref}] ({h.item.filename})\n{h.item.text}")
    return "\n".join(lines)
