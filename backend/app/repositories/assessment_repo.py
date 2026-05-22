from sqlalchemy.orm import Session

from app.models.assessment import AssessmentQuestion
from app.repositories.base import BaseRepository


class AssessmentRepository(BaseRepository[AssessmentQuestion]):
    def __init__(self, db: Session):
        super().__init__(db, AssessmentQuestion)

    def get_specific_session_questions(
        self, session_id: int
    ) -> list[AssessmentQuestion]:
        return (
            self.db.query(AssessmentQuestion)
            .filter(AssessmentQuestion.session_id == session_id)
            .order_by(AssessmentQuestion.set_number.asc(), AssessmentQuestion.difficulty.asc())
            .all()
        )

    def get_practice_set_questions(
        self, session_id: int, set_number: int
    ) -> list[AssessmentQuestion]:
        return (
            self.db.query(AssessmentQuestion)
            .filter(
                AssessmentQuestion.session_id == session_id,
                AssessmentQuestion.set_number == set_number,
            )
            .order_by(AssessmentQuestion.difficulty.asc())
            .all()
        )

    def get_latest_set_number(self, session_id: int) -> int:
        """Return the highest set_number stored for this session (0 if none)."""
        from sqlalchemy import func as sqlfunc
        result = (
            self.db.query(sqlfunc.max(AssessmentQuestion.set_number))
            .filter(AssessmentQuestion.session_id == session_id)
            .scalar()
        )
        return result or 0

    def count_answered_in_set(self, session_id: int, set_number: int) -> int:
        return (
            self.db.query(AssessmentQuestion)
            .filter(
                AssessmentQuestion.session_id == session_id,
                AssessmentQuestion.set_number == set_number,
                AssessmentQuestion.is_correct.isnot(None),
            )
            .count()
        )

    def count_checked_answers(self, session_id: int) -> int:
        """Total graded answers across all sets (kept for compat)."""
        return (
            self.db.query(AssessmentQuestion)
            .filter(
                AssessmentQuestion.session_id == session_id,
                AssessmentQuestion.is_correct.isnot(None),
            )
            .count()
        )
