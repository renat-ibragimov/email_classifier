from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.helpers.enums import ClassificationStatusEnum
from app.models.classification import ClassificationRecord
from app.services.classifier import classify_email
from app.services.hasher import compute_hash
from app.services.parser import parse_email


class ClassificationService:
    """Orchestrates email classification: dedup, parse, classify, persist."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, record_id) -> ClassificationRecord | None:
        """Fetch a classification record by ID.

        Args:
            record_id: UUID of the record.

        Returns:
            ClassificationRecord or None if not found.
        """
        result = await self.session.execute(
            select(ClassificationRecord).where(ClassificationRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    async def classify(self, content: bytes) -> tuple[ClassificationRecord, bool]:
        """Classify email content. Returns existing record if duplicate.

        Handles concurrent duplicates via unique constraint on content_hash.
        Re-classifies records stuck in pending or failed state.

        Args:
            content: Raw .eml file bytes.

        Returns:
            Tuple of (record, is_new). is_new=False means duplicate.
        """
        content_hash = compute_hash(content)

        # Check for existing classification
        existing = await self._find_by_hash(content_hash)
        if existing:
            if existing.status == ClassificationStatusEnum.CLASSIFIED:
                return existing, False
            # Re-classify pending or failed records
            return await self._do_classify(existing, content), False

        # New record
        record = ClassificationRecord(content_hash=content_hash)
        self.session.add(record)

        try:
            await self.session.flush()
        except IntegrityError:
            # Concurrent request already created this record
            await self.session.rollback()
            existing = await self._find_by_hash(content_hash)
            if existing and existing.status == ClassificationStatusEnum.CLASSIFIED:
                return existing, False
            return await self._do_classify(existing, content), False

        return await self._do_classify(record, content), True

    async def _do_classify(self, record: ClassificationRecord, content: bytes) -> ClassificationRecord:
        """Run LLM classification and update the record.

        Args:
            record: Existing DB record to update.
            content: Raw .eml file bytes for parsing.

        Returns:
            Updated ClassificationRecord.
        """
        parsed = parse_email(content)

        try:
            result = await classify_email(parsed)
            record.status = ClassificationStatusEnum.CLASSIFIED
            record.category = result.category
            record.confidence = result.confidence
            record.reasoning = result.reasoning
            record.signals = result.signals
            record.reviewed = result.reviewed
        except Exception:
            record.status = ClassificationStatusEnum.FAILED
            await self.session.commit()
            raise

        await self.session.commit()
        await self.session.refresh(record)

        return record

    async def _find_by_hash(self, content_hash: str) -> ClassificationRecord | None:
        """Find existing record by content hash.

        Args:
            content_hash: SHA-256 hex digest.

        Returns:
            ClassificationRecord or None.
        """
        result = await self.session.execute(
            select(ClassificationRecord).where(ClassificationRecord.content_hash == content_hash)
        )
        return result.scalar_one_or_none()
