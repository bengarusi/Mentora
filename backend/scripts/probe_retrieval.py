"""Manual RAG probe: run a query through the real material retriever and print
the ranked chunks with their scores.

Usage (from backend/, venv active):
    python -m scripts.probe_retrieval --student 1 "how do I solve 2x + 3 = 11"
    python -m scripts.probe_retrieval --student 1 --topic Algebra --limit 6 "..."
    python -m scripts.probe_retrieval --list --student 1

This talks to whatever DATABASE_URL points at, so run it against your local /
QA database only.
"""

from __future__ import annotations

import argparse

from app.db.database import SessionLocal
from app.files.retrieval import get_material_retriever
from app.models.material import MaterialChunk, StudyMaterial


def _list(db, student_id: int) -> None:
    rows = (
        db.query(StudyMaterial)
        .filter(StudyMaterial.student_id == student_id)
        .order_by(StudyMaterial.id)
        .all()
    )
    if not rows:
        print(f"no study materials for student {student_id}")
        return
    for m in rows:
        n = (
            db.query(MaterialChunk)
            .filter(MaterialChunk.material_id == m.id)
            .count()
        )
        print(
            f"  #{m.id:<4} {m.filename:<30} kind={m.kind:<14} "
            f"topic={m.topic or '-':<12} status={m.status:<10} chunks={n}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--student", type=int, required=True)
    ap.add_argument("--subject", default=None)
    ap.add_argument("--topic", default=None)
    ap.add_argument("--limit", type=int, default=4)
    ap.add_argument("--list", action="store_true", help="list materials and exit")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.list:
            _list(db, args.student)
            return
        if not args.query:
            ap.error("query is required unless --list is given")

        _list(db, args.student)
        print(f"\nquery: {args.query!r}  topic={args.topic}  limit={args.limit}\n")

        chunks = get_material_retriever().retrieve(
            db,
            student_id=args.student,
            query=args.query,
            subject=args.subject,
            topic=args.topic,
            limit=args.limit,
        )
        if not chunks:
            print("=> no chunks passed the relevance thresholds")
            return
        for i, c in enumerate(chunks, 1):
            preview = " ".join(c.content.split())[:200]
            print(
                f"[{i}] score={c.score:.3f}  material#{c.material_id} "
                f"({c.material_title}) chunk {c.chunk_index}"
            )
            print(f"    {preview}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
