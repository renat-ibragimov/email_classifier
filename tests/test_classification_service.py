from unittest.mock import AsyncMock, patch

import pytest

from app.helpers.dto import ClassificationResult
from app.helpers.enums import ClassificationStatusEnum, EmailCategoryEnum
from app.models.classification import ClassificationRecord
from app.services.classification_service import ClassificationService

VALID_EML = (
    b"From: sender@example.com\r\n"
    b"To: to@example.com\r\n"
    b"Subject: s\r\n"
    b"\r\n"
    b"body\r\n"
)

INVALID_EML = b"no headers"


def _build_record(status=ClassificationStatusEnum.PENDING, content_hash="hash"):
    return ClassificationRecord(content_hash=content_hash, status=status)


def _classification_result(category=EmailCategoryEnum.SPAM, reviewed=False):
    return ClassificationResult(
        category=category,
        confidence=0.95,
        reasoning="r",
        signals=["s"],
        reviewed=reviewed,
    )


class TestClassify:

    async def test_existing_classified_returns_duplicate(self):
        existing = _build_record(status=ClassificationStatusEnum.CLASSIFIED)
        repo = AsyncMock()
        repo.find_by_hash = AsyncMock(return_value=existing)

        service = ClassificationService(repo)
        record, is_new = await service.classify(VALID_EML)

        assert record is existing
        assert is_new is False
        repo.create.assert_not_called()
        repo.save.assert_not_called()

    async def test_existing_pending_runs_classification(self):
        existing = _build_record(status=ClassificationStatusEnum.PENDING)
        repo = AsyncMock()
        repo.find_by_hash = AsyncMock(return_value=existing)
        with patch(
            "app.services.classification_service.classify_email",
            new=AsyncMock(return_value=_classification_result()),
        ):
            service = ClassificationService(repo)
            record, is_new = await service.classify(VALID_EML)

        assert record is existing
        assert is_new is False
        assert record.status == ClassificationStatusEnum.CLASSIFIED
        repo.save.assert_called_once()
        repo.create.assert_not_called()

    async def test_existing_failed_runs_classification(self):
        existing = _build_record(status=ClassificationStatusEnum.FAILED)
        repo = AsyncMock()
        repo.find_by_hash = AsyncMock(return_value=existing)
        with patch(
            "app.services.classification_service.classify_email",
            new=AsyncMock(return_value=_classification_result(EmailCategoryEnum.PERSONAL)),
        ):
            service = ClassificationService(repo)
            record, is_new = await service.classify(VALID_EML)

        assert is_new is False
        assert record.status == ClassificationStatusEnum.CLASSIFIED
        assert record.category == EmailCategoryEnum.PERSONAL

    async def test_new_record_classifies(self):
        new_record = _build_record(status=ClassificationStatusEnum.PENDING)
        repo = AsyncMock()
        repo.find_by_hash = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=(new_record, True))
        with patch(
            "app.services.classification_service.classify_email",
            new=AsyncMock(return_value=_classification_result(EmailCategoryEnum.NEWSLETTER)),
        ):
            service = ClassificationService(repo)
            record, is_new = await service.classify(VALID_EML)

        assert record is new_record
        assert is_new is True
        assert record.status == ClassificationStatusEnum.CLASSIFIED
        assert record.category == EmailCategoryEnum.NEWSLETTER
        # First save after create (commits PENDING), second after classification.
        assert repo.save.call_count == 2

    async def test_race_lost_with_classified_winner(self):
        winner = _build_record(status=ClassificationStatusEnum.CLASSIFIED)
        repo = AsyncMock()
        repo.find_by_hash = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=(winner, False))
        with patch("app.services.classification_service.classify_email") as mock_classify:
            service = ClassificationService(repo)
            record, is_new = await service.classify(VALID_EML)

        assert record is winner
        assert is_new is False
        mock_classify.assert_not_called()

    async def test_race_lost_with_pending_winner_runs_classification(self):
        winner = _build_record(status=ClassificationStatusEnum.PENDING)
        repo = AsyncMock()
        repo.find_by_hash = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=(winner, False))
        with patch(
            "app.services.classification_service.classify_email",
            new=AsyncMock(return_value=_classification_result()),
        ):
            service = ClassificationService(repo)
            record, is_new = await service.classify(VALID_EML)

        assert record is winner
        assert is_new is False
        assert record.status == ClassificationStatusEnum.CLASSIFIED

    async def test_invalid_eml_raises_before_db(self):
        repo = AsyncMock()
        service = ClassificationService(repo)

        with pytest.raises(ValueError, match="missing From header"):
            await service.classify(INVALID_EML)

        repo.find_by_hash.assert_not_called()
        repo.create.assert_not_called()
        repo.save.assert_not_called()

    async def test_llm_failure_marks_failed_and_reraises(self):
        new_record = _build_record(status=ClassificationStatusEnum.PENDING)
        repo = AsyncMock()
        repo.find_by_hash = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=(new_record, True))
        with patch(
            "app.services.classification_service.classify_email",
            new=AsyncMock(side_effect=RuntimeError("api down")),
        ):
            service = ClassificationService(repo)
            with pytest.raises(RuntimeError, match="api down"):
                await service.classify(VALID_EML)

        assert new_record.status == ClassificationStatusEnum.FAILED
        # save was called: once after create (PENDING), once when marking FAILED.
        assert repo.save.call_count == 2
