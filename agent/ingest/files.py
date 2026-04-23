"""File ingestion: PDF, DOCX, TXT."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent import sources
from agent.config import TRUST_BY_TYPE
from agent.ingest.pipeline import ingest_source
from agent.models import Source


def _read_pdf(path: Path) -> tuple[str, bytes]:
    from pypdf import PdfReader

    raw = path.read_bytes()
    reader = PdfReader(path)
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(p for p in parts if p.strip()), raw


def _read_docx(path: Path) -> tuple[str, bytes]:
    import docx

    raw = path.read_bytes()
    doc = docx.Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(parts), raw


def _read_txt(path: Path) -> tuple[str, bytes]:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8"), raw
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace"), raw


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ingest_file(file_path: str) -> dict:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        content, raw = _read_pdf(path)
        ext = "pdf"
    elif suffix in {".docx"}:
        content, raw = _read_docx(path)
        ext = "docx"
    elif suffix in {".txt", ".md"}:
        content, raw = _read_txt(path)
        ext = suffix.lstrip(".")
    else:
        raise ValueError(
            f"Unsupported file type {suffix!r}. Supported: .pdf .docx .txt .md"
        )

    if not content.strip():
        raise RuntimeError(f"No text extracted from {path}")

    source_id = sources.mint_source_id()
    raw_path = sources.save_raw_bytes(source_id, raw, ext)
    src = Source(
        source_id=source_id,
        type="file",
        location=str(path),
        fetched_at=_now(),
        raw_content_path=str(raw_path),
        content_hash=sources.content_hash(raw),
        trust=TRUST_BY_TYPE["file"],
        derived_fact_ids=[],
        ingestion_summary={},
    )
    sources.save_source(src)

    summary = ingest_source(src, content)
    return {"source_id": source_id, "summary": summary}
