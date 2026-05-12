import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classification import ClassificationRecord


class ClassificationRepository:
    """Data access for ClassificationRecord rows."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, record_id: uuid.UUID) -> ClassificationRecord | None:
        """Fetch a classification record by primary key.

        Args:
            record_id: UUID of the record.

        Returns:
            ClassificationRecord or None if not found.
        """
        result = await self.session.execute(
            select(ClassificationRecord).where(ClassificationRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    async def find_by_hash(self, content_hash: str) -> ClassificationRecord | None:
        """Find a record by its content hash.

        Args:
            content_hash: SHA-256 hex digest of raw .eml bytes.

        Returns:
            ClassificationRecord or None if not found.
        """
        result = await self.session.execute(
            select(ClassificationRecord).where(ClassificationRecord.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def create(self, content_hash: str) -> tuple[ClassificationRecord, bool]:
        """Insert a new pending record, handling concurrent-duplicate races.

        On unique-constraint conflict the session is rolled back and the
        winning row is re-fetched.

        Args:
            content_hash: SHA-256 hex digest used as the dedup key.

        Returns:
            Tuple of (record, is_new). is_new=True for a freshly inserted row,
            False if a concurrent request had already inserted the same hash.

        Raises:
            RuntimeError: If the winning row disappeared between rollback and
                the re-fetch. This is an unexpected state — the row should
                still be there.
        """
        record = ClassificationRecord(content_hash=content_hash)
        self.session.add(record)

        try:
            await self.session.flush()
        except IntegrityError:
            # Unique constraint on content_hash tripped: a concurrent request
            # inserted the same hash. Rollback to recover the session, then
            # re-fetch the winner's row.
            await self.session.rollback()
            existing = await self.find_by_hash(content_hash)
            if existing is None:
                raise RuntimeError(
                    "Concurrent record disappeared after IntegrityError — unexpected state"
                )
            return existing, False

        return record, True

    async def save(self) -> None:
        """Commit the current transaction."""
        await self.session.commit()
