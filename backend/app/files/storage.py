from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings

log = logging.getLogger("app.files.storage")


class FileStorageError(Exception):
    """Raised when a file cannot be written to or read from storage."""


class FileStorage(ABC):
    """Where uploaded bytes live. The DB stores only the returned key, so
    swapping local disk for S3/GCS means implementing this interface and
    changing the factory — no call-site changes."""

    @abstractmethod
    def save(self, data: bytes, *, student_id: int, filename: str) -> str:
        """Persist *data* and return an opaque storage key."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Return the bytes previously stored under *key*."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the object at *key*. Missing objects are not an error."""


class LocalFileStorage(FileStorage):
    """Stores uploads on the local filesystem under a per-student directory.

    Keys are `<student_id>/<uuid><ext>` — the random name avoids collisions and
    keeps the student's original filename out of the path, while the DB row
    keeps that name for display."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or settings.MATERIAL_STORAGE_DIR)

    def _path_for(self, key: str) -> Path:
        # Resolve and confirm the key stays inside the storage root, so a
        # crafted key ("../../etc/passwd") can never escape it.
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if not path.is_relative_to(root):
            raise FileStorageError("Invalid storage key")
        return path

    def save(self, data: bytes, *, student_id: int, filename: str) -> str:
        suffix = Path(filename).suffix[:16]  # cap absurd extensions
        key = f"{student_id}/{uuid.uuid4().hex}{suffix}"
        path = self._path_for(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            log.error("storage write failed key=%s error=%s", key, exc)
            raise FileStorageError(str(exc)) from exc
        log.info("stored material key=%s bytes=%d", key, len(data))
        return key

    def read(self, key: str) -> bytes:
        path = self._path_for(key)
        try:
            return path.read_bytes()
        except OSError as exc:
            log.error("storage read failed key=%s error=%s", key, exc)
            raise FileStorageError(str(exc)) from exc

    def delete(self, key: str) -> None:
        try:
            self._path_for(key).unlink(missing_ok=True)
        except (OSError, FileStorageError) as exc:  # deletion is best-effort
            log.warning("storage delete failed key=%s error=%s", key, exc)


def get_file_storage() -> FileStorage:
    """Dependency seam — tests and future backends override this."""
    return LocalFileStorage()
