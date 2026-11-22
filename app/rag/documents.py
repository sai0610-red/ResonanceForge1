"""Customer document intake: type/size limits, text extraction, chunking.

Only extracted text is kept (in SQLite). The uploaded bytes are not written to disk.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import PurePath

ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}


class DocumentError(ValueError):
    """A client-side problem with an uploaded document. `status` is the HTTP code."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Chunk:
    index: int  # 1-based, shown to users and cited as C<index>
    text: str


def safe_filename(name: str | None) -> str:
    """Basename only, printable characters, capped length. Never used as a path."""
    base = PurePath((name or "").replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._\- ]+", "_", base).strip(" .")
    return (base or "document")[:120]


def extension_of(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def check_extension(filename: str) -> str:
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentError(
            f"{filename}: unsupported type '{ext or 'none'}'. Allowed: .txt, .md, .pdf",
            status=415,
        )
    return ext


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from txt/md/pdf bytes. Raises DocumentError on bad input."""
    ext = check_extension(filename)
    if ext == ".pdf":
        text = _pdf_text(filename, data)
    else:
        if b"\x00" in data[:4096]:
            raise DocumentError(f"{filename}: looks like a binary file, not text")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
    text = normalize(text)
    if not text:
        raise DocumentError(f"{filename}: no extractable text")
    return text


def _pdf_text(filename: str, data: bytes) -> str:
    if not data.startswith(b"%PDF"):
        raise DocumentError(f"{filename}: not a valid PDF")
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError(f"{filename}: encrypted PDFs are not supported")
        pages = [(page.extract_text() or "") for page in reader.pages]
    except DocumentError:
        raise
    except Exception as exc:  # pypdf raises many types on malformed files
        raise DocumentError(
            f"{filename}: could not read PDF ({exc.__class__.__name__})"
        ) from exc
    return "\n\n".join(pages)


def normalize(text: str) -> str:
    """Collapse runs of spaces, keep paragraph breaks, drop control characters."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_chars: int = 800, overlap: int = 120) -> list[Chunk]:
    """Split text into ~chunk_chars pieces on paragraph, then word, boundaries.

    Paragraphs are packed together until the next one would overflow. A paragraph
    longer than chunk_chars is cut on word boundaries with `overlap` characters of
    carry-over so a sentence split across two chunks is still findable.
    """
    chunk_chars = max(200, int(chunk_chars))
    overlap = max(0, min(int(overlap), chunk_chars // 2))
    pieces: list[str] = []
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if len(para) <= chunk_chars:
            pieces.append(para)
        else:
            pieces.extend(_split_long(para, chunk_chars, overlap))

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + 2 + len(piece) <= chunk_chars:
            current = f"{current}\n\n{piece}"
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return [Chunk(index=i, text=t) for i, t in enumerate(chunks, 1)]


def _split_long(para: str, size: int, overlap: int) -> list[str]:
    out: list[str] = []
    start = 0
    n = len(para)
    while start < n:
        end = min(n, start + size)
        if end < n:
            space = para.rfind(" ", start + size // 2, end)
            if space > start:
                end = space
        out.append(para[start:end].strip())
        if end >= n:
            break
        nxt = end - overlap
        if overlap:
            space = para.find(" ", nxt, end)
            nxt = space + 1 if space != -1 else nxt
        start = max(nxt, start + 1)
    return [p for p in out if p]
