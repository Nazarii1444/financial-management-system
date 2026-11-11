"""
StorageService
──────────────
Abstract base + local filesystem and database implementations.
`get_storage()` picks one by FILE_STORAGE: "local" (UPLOAD_DIR) or "database" (bytes in
Postgres — for hosts without a persistent disk, such as Render's free tier).
"""
import os
import uuid
from abc import ABC, abstractmethod

import aiofiles
from sqlalchemy import delete as sa_delete, select

from src.config import FILE_STORAGE, UPLOAD_DIR
from src.database import AsyncSessionLocal
from src.models import ReceiptFile


class BaseStorageService(ABC):
    @abstractmethod
    async def save(self, user_id: int, original_filename: str, data: bytes) -> tuple[str, str]:
        """
        Persist *data* and return (stored_filename, relative_file_path).
        relative_file_path is stored in the DB; it is relative to the storage root.
        """

    @abstractmethod
    async def read(self, file_path: str) -> bytes:
        """Return the bytes stored at the given relative path. Raises FileNotFoundError."""

    @abstractmethod
    async def delete(self, file_path: str) -> None:
        """Remove file at the given relative path. Silently ignore missing files."""


def _new_filename(original_filename: str) -> str:
    ext = os.path.splitext(original_filename)[1].lower() or ""
    return f"{uuid.uuid4().hex}{ext}"


class LocalStorageService(BaseStorageService):
    """Stores files under  <base_dir>/<user_id>/<uuid><ext>"""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = os.path.abspath(base_dir)

    async def save(self, user_id: int, original_filename: str, data: bytes) -> tuple[str, str]:
        stored_filename = _new_filename(original_filename)
        user_dir = os.path.join(self.base_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

        rel_path = f"{user_id}/{stored_filename}"
        abs_path = os.path.join(self.base_dir, rel_path)

        async with aiofiles.open(abs_path, "wb") as fh:
            await fh.write(data)

        return stored_filename, rel_path

    async def read(self, file_path: str) -> bytes:
        async with aiofiles.open(self.absolute_path(file_path), "rb") as fh:
            return await fh.read()

    async def delete(self, file_path: str) -> None:
        abs_path = os.path.join(self.base_dir, file_path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)

    def absolute_path(self, file_path: str) -> str:
        return os.path.join(self.base_dir, file_path)


class DatabaseStorageService(BaseStorageService):
    """Stores file bytes in the receipt_files table, keyed by  <user_id>/<uuid><ext>"""

    async def save(self, user_id: int, original_filename: str, data: bytes) -> tuple[str, str]:
        stored_filename = _new_filename(original_filename)
        rel_path = f"{user_id}/{stored_filename}"
        async with AsyncSessionLocal() as session:
            session.add(ReceiptFile(user_id=user_id, file_path=rel_path, data=data))
            await session.commit()
        return stored_filename, rel_path

    async def read(self, file_path: str) -> bytes:
        async with AsyncSessionLocal() as session:
            data = (await session.execute(
                select(ReceiptFile.data).where(ReceiptFile.file_path == file_path)
            )).scalar_one_or_none()
        if data is None:
            raise FileNotFoundError(file_path)
        return data

    async def delete(self, file_path: str) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(sa_delete(ReceiptFile).where(ReceiptFile.file_path == file_path))
            await session.commit()


def get_storage() -> BaseStorageService:
    if FILE_STORAGE == "database":
        return DatabaseStorageService()
    return LocalStorageService(UPLOAD_DIR)
