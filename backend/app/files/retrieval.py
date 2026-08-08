from __future__ import annotations

import logging
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.enums import MaterialKind, MaterialStatus
from app.models.material import MaterialChunk, StudyMaterial

log = logging.getLogger("app.files.retrieval")

# Very common words carry no signal for ranking; dropping them stops a query
# like "can you explain the fractions" from matching on "the" and "you".
_STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those is are was were be been
    being am do does did doing have has had having i me my we our you your he she
    it they them his her its their what which who whom when where why how all any
    both each few more most other some such no nor not only own same so too very
    can will just should now of to in on at by for with about into over after
    please tell explain show help want need me learn about know understand
    work works working out find finds finding mean means get gets got make makes
    use uses using way ways give gives like would could okay yeah hi hello thanks
    thing things something anything lot bit really actually maybe sure
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    ]


@dataclass
class RetrievedChunk:
    """One relevant passage plus enough provenance to cite it to the student."""

    material_id: int
    material_title: str
    chunk_index: int
    content: str
    score: float


class MaterialRetriever(ABC):
    """Selects the passages a tutor turn should actually see.

    This is the guard against dumping every upload into the prompt: callers ask
    for what is relevant to *this* question, and get back a ranked, bounded set.
    A vector-search implementation swaps in here by reading the `embedding`
    column that `MaterialChunk` already carries."""

    @abstractmethod
    def retrieve(
        self,
        db: Session,
        *,
        student_id: int,
        query: str,
        subject: str | None = None,
        topic: str | None = None,
        limit: int = 4,
    ) -> list[RetrievedChunk]:
        """Return at most *limit* chunks relevant to *query*, best first."""


class KeywordMaterialRetriever(MaterialRetriever):
    """TF-IDF-style lexical ranking over the student's own study materials.

    Deliberately dependency-free so retrieval works today without an embedding
    provider or vector database. Scoring favours chunks that share rare query
    terms, with a bonus for materials already tagged with the lesson's topic —
    metadata narrows the candidate set, and the text decides the order."""

    #: Minimum share of the question's retrievable information a chunk must
    #: cover. Scores are normalised (see `retrieve`) so this threshold means the
    #: same thing whether the student has two files or two hundred.
    MIN_SCORE = 0.30
    #: A chunk must share at least this fraction of the question's meaningful
    #: terms. Stops a single incidental word from dragging a document in.
    MIN_COVERAGE = 0.34
    #: Keep only chunks scoring within this fraction of the best hit. The tutor
    #: needs the passage that answers the question, not a long tail of
    #: loosely-related ones competing for its attention.
    RELATIVE_CUTOFF = 0.55
    #: Material the student filed under this lesson's topic is what they meant
    #: to study here.
    SAME_TOPIC_BOOST = 2.0
    #: Material explicitly filed under a *different* topic still surfaces, but
    #: only when it is a genuinely strong match — an off-topic handout must not
    #: outrank the one the student filed for this lesson.
    OTHER_TOPIC_PENALTY = 0.4
    #: Distinct query terms a chunk must match before material filed under a
    #: *different* topic is allowed in at all. One shared word is too weak a
    #: reason to reach outside the lesson's own topic — it is how a throwaway
    #: "thanks, that makes sense" drags in an unrelated worksheet.
    MIN_TERMS_FOR_OTHER_TOPIC = 2

    def _base_query(self, db: Session, *, student_id: int, subject: str | None):
        query = (
            db.query(MaterialChunk, StudyMaterial)
            .join(StudyMaterial, MaterialChunk.material_id == StudyMaterial.id)
            .filter(
                StudyMaterial.student_id == student_id,
                # Homework belongs to its own session's context, never to
                # general lesson retrieval.
                StudyMaterial.kind == MaterialKind.STUDY_MATERIAL.value,
                StudyMaterial.status == MaterialStatus.READY.value,
            )
        )
        if subject:
            # Materials with no subject stay eligible — an untagged upload is
            # still the student's, just less specific.
            query = query.filter(
                (StudyMaterial.subject == subject) | (StudyMaterial.subject.is_(None))
            )
        return query

    def _candidate_chunks(
        self,
        db: Session,
        *,
        student_id: int,
        subject: str | None,
        terms: set[str],
    ) -> tuple[list[tuple[MaterialChunk, StudyMaterial]], int]:
        """Chunks worth scoring, plus the true corpus size for IDF.

        Only chunks containing at least one query term are loaded: the rest
        cannot score above zero, so fetching and tokenising them is pure cost.
        This keeps a turn's retrieval proportional to what actually matches
        rather than to the size of the student's whole library — retrieval runs
        before the first token of the reply, so it is latency the student feels.

        Document frequencies are unaffected: a chunk with no query term
        contributes nothing to any query term's count. The true corpus size is
        counted separately so IDF keeps its meaning.
        """
        base = self._base_query(db, student_id=student_id, subject=subject)
        total_docs = base.count()
        if total_docs == 0:
            return [], 0

        # Substring prefilter — deliberately a superset (it will also match
        # "add" inside "ladder"); the tokeniser below makes the exact decision.
        # Terms come from a strict [a-z0-9] tokeniser, so they carry no LIKE
        # wildcards to escape.
        matches_any = or_(
            *(func.lower(MaterialChunk.content).like(f"%{term}%") for term in terms)
        )
        return base.filter(matches_any).all(), total_docs

    def retrieve(
        self,
        db: Session,
        *,
        student_id: int,
        query: str,
        subject: str | None = None,
        topic: str | None = None,
        limit: int = 4,
    ) -> list[RetrievedChunk]:
        terms = set(_tokenize(query))
        if not terms:
            return []

        rows, total_docs = self._candidate_chunks(
            db, student_id=student_id, subject=subject, terms=terms
        )
        if not rows:
            return []

        # Term counts per chunk: document frequency decides how informative a
        # term is, term frequency breaks ties between chunks that both mention it.
        doc_counts = [Counter(_tokenize(chunk.content)) for chunk, _ in rows]
        doc_freq: Counter[str] = Counter()
        for counts in doc_counts:
            doc_freq.update(terms & set(counts))

        # A term appearing in every chunk (e.g. "fraction" across a fractions
        # folder) pins nothing down; a rare one identifies the right passage.
        idf = {
            term: math.log(1 + total_docs / (1 + doc_freq[term])) for term in terms
        }
        # Normalise against the information actually available in the corpus, so
        # a score reads as "share of the question this chunk answers" — the same
        # 0-1 scale for a two-file library and a two-hundred-file one. Terms that
        # appear nowhere are excluded: they are unanswerable, not evidence.
        norm = sum(idf[term] for term in terms if doc_freq[term] > 0)
        if norm <= 0:
            return []  # nothing in the corpus speaks to this question at all

        topic_terms = set(_tokenize(topic)) if topic else set()
        lesson_topic = topic.lower().strip() if topic else None

        scored: list[RetrievedChunk] = []
        for (chunk, material), counts in zip(rows, doc_counts):
            overlap = terms & set(counts)
            # Require the chunk to cover a real share of the question, not just
            # collide on one word.
            if len(overlap) / len(terms) < self.MIN_COVERAGE:
                continue

            # Sublinear term frequency: repeated mentions signal the passage is
            # about the term, without letting repetition dominate.
            score = (
                sum(
                    idf[term] * (1 + math.log(counts[term])) for term in overlap
                )
                / norm
            )

            material_topic = (material.topic or "").lower().strip()
            if lesson_topic and material_topic:
                if material_topic == lesson_topic:
                    score *= self.SAME_TOPIC_BOOST
                elif len(overlap) < self.MIN_TERMS_FOR_OTHER_TOPIC:
                    continue  # too thin a match to justify leaving the topic
                else:
                    score *= self.OTHER_TOPIC_PENALTY
            elif topic_terms & set(counts):
                # Untagged material that talks about this topic anyway.
                score *= 1.15

            if score < self.MIN_SCORE:
                continue
            scored.append(
                RetrievedChunk(
                    material_id=material.id,
                    material_title=material.title or material.filename,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    score=round(score, 4),
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        # Drop the weak tail relative to the best hit: passages far behind the
        # leader are noise, and every one we keep costs prompt budget.
        if scored:
            floor = scored[0].score * self.RELATIVE_CUTOFF
            scored = [c for c in scored if c.score >= floor]
        top = scored[:limit]
        log.info(
            "material retrieval student_id=%s candidates=%d matched=%d returned=%d",
            student_id,
            total_docs,
            len(scored),
            len(top),
        )
        return top


def get_material_retriever() -> MaterialRetriever:
    """Dependency seam — swap in an embedding-backed retriever here."""
    return KeywordMaterialRetriever()
