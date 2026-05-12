from app.helpers.dto import ParsedEmail
from app.helpers.enums import ClassificationStatusEnum
from app.models.classification import ClassificationRecord
from app.repositories.classification import ClassificationRepository
from app.services.classifier import classify_email
from app.services.hasher import compute_hash
from app.services.parser import parse_email


class ClassificationService:
    """Orchestrates email classification: dedup, parse, classify, persist."""

    def __init__(self, repo: ClassificationRepository) -> None:
        self.repo = repo

    async def classify(self, content: bytes) -> tuple[ClassificationRecord, bool]:
        """Classify email content. Returns existing record if duplicate.

        Parsing happens before any DB interaction so an invalid .eml never
        leaves a PENDING orphan behind. The PENDING row is committed before
        the LLM call so the unique-index lock isn't held while OpenAI runs.

        Args:
            content: Raw .eml file bytes.

        Returns:
            Tuple of (record, is_new). is_new=False means duplicate.

        Raises:
            ValueError: If content is not a valid .eml (no DB write happened).

        """
        content_hash = compute_hash(content)
        parsed = parse_email(content)

        existing = await self.repo.find_by_hash(content_hash)
        if existing:
            if existing.status == ClassificationStatusEnum.CLASSIFIED:
                return existing, False
            # Re-classify pending or failed records (no commit needed; SELECT-only tx).
            return await self._run_llm_classification(existing, parsed), False

        # Insert + commit PENDING immediately to release the unique-index lock
        # before the multi-second LLM call. Repo handles the concurrent-insert race.
        record, is_new = await self.repo.create(content_hash)
        await self.repo.save()

        if not is_new and record.status == ClassificationStatusEnum.CLASSIFIED:
            return record, False

        return await self._run_llm_classification(record, parsed), is_new

    async def _run_llm_classification(
        self, record: ClassificationRecord, parsed: ParsedEmail
    ) -> ClassificationRecord:
        """Call the LLM classifier and persist the result.

        Args:
            record: Existing DB record to update.
            parsed: Already-parsed email content.

        Returns:
            Updated ClassificationRecord.

        """
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
            await self.repo.save()
            raise

        await self.repo.save()
        return record
