from sqlalchemy.orm import Session

from app.models.performance import Performance
from app.repositories.base import BaseRepository


class PerformanceRepository(BaseRepository[Performance]):
    def __init__(self, db: Session):
        super().__init__(db, Performance)

    def get_specific_session_performance(self, session_id: int) -> Performance | None:
        return (
            self.db.query(Performance)
            .filter(Performance.session_id == session_id)
            .first()
        )
