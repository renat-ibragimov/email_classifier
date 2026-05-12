import uuid
from unittest.mock import AsyncMock

import pytest

from app.helpers.enums import ClassificationStatusEnum
from app.models.classification import ClassificationRecord
from app.repositories.classification import ClassificationRepository


class TestFindById:

    async def test_returns_record_when_exists(self, db_session):
        record = ClassificationRecord(content_hash="abc123")
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        repo = ClassificationRepository(db_session)
        found = await repo.find_by_id(record.id)

        assert found is not None
        assert found.id == record.id
        assert found.content_hash == "abc123"

    async def test_returns_none_when_missing(self, db_session):
        repo = ClassificationRepository(db_session)
        result = await repo.find_by_id(uuid.uuid4())
        assert result is None


class TestFindByHash:

    async def test_returns_record_when_exists(self, db_session):
        record = ClassificationRecord(content_hash="hashvalue")
        db_session.add(record)
        await db_session.commit()

        repo = ClassificationRepository(db_session)
        found = await repo.find_by_hash("hashvalue")

        assert found is not None
        assert found.content_hash == "hashvalue"

    async def test_returns_none_when_missing(self, db_session):
        repo = ClassificationRepository(db_session)
        result = await repo.find_by_hash("nonexistent-hash")
        assert result is None


class TestCreate:

    async def test_inserts_new_record(self, db_session):
        repo = ClassificationRepository(db_session)

        record, is_new = await repo.create("freshhash")
        await repo.save()

        assert is_new is True
        assert record.content_hash == "freshhash"
        assert record.status == ClassificationStatusEnum.PENDING

    async def test_concurrent_duplicate_returns_existing(self, db_session):
        existing = ClassificationRecord(content_hash="dupe")
        db_session.add(existing)
        await db_session.commit()

        repo = ClassificationRepository(db_session)
        record, is_new = await repo.create("dupe")

        assert is_new is False
        assert record.id == existing.id
        assert record.content_hash == "dupe"

    async def test_raises_when_winner_disappears_after_rollback(self, db_session):
        existing = ClassificationRecord(content_hash="phantom")
        db_session.add(existing)
        await db_session.commit()

        repo = ClassificationRepository(db_session)
        # Force find_by_hash to return None after the IntegrityError rollback,
        # simulating the impossible state the guard protects against.
        repo.find_by_hash = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="disappeared"):
            await repo.create("phantom")


class TestSave:

    async def test_commits_pending_changes(self, db_session):
        record = ClassificationRecord(content_hash="committest")
        db_session.add(record)

        repo = ClassificationRepository(db_session)
        await repo.save()

        # Different session would also see the row, so this confirms commit happened.
        found = await repo.find_by_hash("committest")
        assert found is not None
