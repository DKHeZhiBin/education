from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings


class InvalidProblemImage(ValueError):
    """中文：定义“invalid·题目·图片”类，封装该职责相关的数据与行为。
    English: Defines the invalid problem image class and encapsulates data and behavior for that responsibility.
    """
    pass


class ProblemImageTooLarge(ValueError):
    """中文：定义“题目·图片·too·large”类，封装该职责相关的数据与行为。
    English: Defines the problem image too large class and encapsulates data and behavior for that responsibility.
    """
    pass


@dataclass(frozen=True)
class StoredProblemImage:
    """中文：定义“stored·题目·图片”类，封装该职责相关的数据与行为。
    English: Defines the stored problem image class and encapsulates data and behavior for that responsibility.
    """
    storage_key: str
    mime_type: str
    size_bytes: int
    content_sha256: str


class LocalProblemImageStorage:
    """中文：定义“local·题目·图片·storage”类，封装该职责相关的数据与行为。
    English: Defines the local problem image storage class and encapsulates data and behavior for that responsibility.
    """
    CHUNK_BYTES = 1024 * 1024

    def __init__(self) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        configured = Path(settings.problem_image_storage_dir)
        self.root = configured if configured.is_absolute() else Path.cwd() / configured

    async def save(self, upload: UploadFile, owner_user_id: str, asset_id: str) -> StoredProblemImage:
        """中文：处理“保存”相关操作。
        English: Handles the save operation.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        owner_dir = self.root / owner_user_id
        owner_dir.mkdir(parents=True, exist_ok=True)
        temporary = owner_dir / f".{asset_id}.upload"
        size = 0
        digest = sha256()
        header = b""
        try:
            with temporary.open("xb") as target:
                while chunk := await upload.read(self.CHUNK_BYTES):
                    size += len(chunk)
                    if size > settings.problem_image_max_bytes:
                        raise ProblemImageTooLarge("problem image exceeds configured size limit")
                    if len(header) < 16:
                        header = (header + chunk)[:16]
                    digest.update(chunk)
                    target.write(chunk)
            if size == 0:
                raise InvalidProblemImage("problem image is empty")
            mime_type, extension = self._detect_type(header)
            final_path = owner_dir / f"{asset_id}{extension}"
            temporary.replace(final_path)
            return StoredProblemImage(
                storage_key=str(final_path.relative_to(self.root)),
                mime_type=mime_type,
                size_bytes=size,
                content_sha256=digest.hexdigest(),
            )
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    def delete(self, storage_key: str) -> None:
        """中文：处理“删除”相关操作。
        English: Handles the delete operation.
        """
        candidate = (self.root / storage_key).resolve()
        root = self.root.resolve()
        if candidate.is_relative_to(root):
            candidate.unlink(missing_ok=True)

    def read(self, storage_key: str) -> bytes:
        """中文：从受控存储根目录读取待识别图片。
        English: Reads an image for recognition from the controlled storage root.
        """
        candidate = (self.root / storage_key).resolve()
        root = self.root.resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise FileNotFoundError("problem image is missing")
        return candidate.read_bytes()

    def delete_owner(self, owner_user_id: str) -> None:
        """中文：处理“删除·owner”相关操作。
        English: Handles the delete owner operation.
        """
        root = self.root.resolve()
        owner_dir = (root / owner_user_id).resolve()
        if owner_dir.parent != root:
            raise ValueError("invalid problem image owner")
        if owner_dir.exists():
            rmtree(owner_dir)

    @staticmethod
    def _detect_type(header: bytes) -> tuple[str, str]:
        """中文：处理“detect·type”相关操作。
        English: Handles the detect type operation.
        """
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png", ".png"
        if header.startswith(b"\xff\xd8\xff"):
            return "image/jpeg", ".jpg"
        if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            return "image/webp", ".webp"
        raise InvalidProblemImage("only JPEG, PNG and WebP images are supported")


problem_image_storage = LocalProblemImageStorage()
