"""
StorageService
──────────────
Abstract base + local filesystem implementation.

To swap to S3: subclass BaseStorageService and inject it into the router.
"""
import os
import uuid
from abc import ABC, abstractmethod

import aiofiles


class BaseStorageService(ABC):
    @abstractmethod
    async def save(self, user_id: int, original_filename: str, data: bytes) -> tuple[str, str]:
        """
        Persist *data* and return (stored_filename, relative_file_path).
        relative_file_path is stored in the DB; it is relative to the storage root.
        """

    @abstractmethod
    async def delete(self, file_path: str) -> None:
        """Remove file at the given relative path. Silently ignore missing files."""

    @abstractmethod
    def absolute_path(self, file_path: str) -> str:
        """Resolve a relative file_path to an absolute filesystem path."""


class LocalStorageService(BaseStorageService):
    """Stores files under  <base_dir>/<user_id>/<uuid><ext>"""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = os.path.abspath(base_dir)

    async def save(self, user_id: int, original_filename: str, data: bytes) -> tuple[str, str]:
        ext = os.path.splitext(original_filename)[1].lower() or ""
        stored_filename = f"{uuid.uuid4().hex}{ext}"
        user_dir = os.path.join(self.base_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

        rel_path = f"{user_id}/{stored_filename}"
        abs_path = os.path.join(self.base_dir, rel_path)

        async with aiofiles.open(abs_path, "wb") as fh:
            await fh.write(data)

        return stored_filename, rel_path

    async def delete(self, file_path: str) -> None:
        abs_path = os.path.join(self.base_dir, file_path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)

    def absolute_path(self, file_path: str) -> str:
        return os.path.join(self.base_dir, file_path)

