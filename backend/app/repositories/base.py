from typing import Generic, Type, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Generic data access. Repositories flush but never commit — the service
    owns the transaction boundary (one commit per request)."""

    def __init__(self, db: Session, model: Type[ModelT]):
        self.db = db
        self.model = model

    def get(self, id_: int) -> ModelT | None:
        return self.db.get(self.model, id_)

    def list(self, **filters) -> list[ModelT]:
        query = self.db.query(self.model)
        if filters:
            query = query.filter_by(**filters)
        return query.all()

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.db.delete(obj)
        self.db.flush()
