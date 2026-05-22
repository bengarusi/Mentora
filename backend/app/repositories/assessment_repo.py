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
            .order_by(AssessmentQuestion.difficulty.asc())
            .all()
        )

    def count_checked_answers(self, session_id: int) -> int:
        return (
            self.db.query(AssessmentQuestion)
            .filter(
                AssessmentQuestion.session_id == session_id,
                AssessmentQuestion.is_correct.isnot(None),
            )
            .count()
        )
