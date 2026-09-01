import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.helpers.dto import ClassificationResult
from app.helpers.enums import EmailCategoryEnum, LanguageEnum
from app.main import app

VALID_EML = b"From: sender@example.com\r\nTo: to@example.com\r\nSubject: s\r\n\r\nbody\r\n"


def _result(category=EmailCategoryEnum.SPAM, reviewed=False):
    return ClassificationResult(
        category=category,
        confidence=0.95,
        reasoning="r",
        signals=["s"],
        reviewed=reviewed,
    )


@pytest.fixture(autouse=True)
def mock_classifier():
    """Patch classify_email so router tests never hit OpenAI."""
    with patch(
        "app.services.classification_service.classify_email",
        new=AsyncMock(return_value=_result()),
    ) as mock:
        yield mock


async def _post(eml_bytes, filename="email.eml", language=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/classify/",
            files={"file": (filename, eml_bytes, "application/octet-stream")},
            data={} if language is None else {"language": language},
        )


async def _get(record_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(f"/classify/{record_id}/")


class TestPostClassify:
    async def test_new_returns_201(self, db_session):
        response = await _post(VALID_EML)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "classified"
        assert body["category"] == "spam"
        assert body["confidence"] == 0.95
        assert body["reviewed"] is False
        assert body["model"] == settings.openai_model
        # created_at is set by the DB default and must parse as a real timestamp.
        assert datetime.fromisoformat(body["created_at"]).tzinfo is not None

    async def test_duplicate_returns_200(self, db_session, mock_classifier):
        r1 = await _post(VALID_EML)
        assert r1.status_code == 201

        r2 = await _post(VALID_EML)
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]
        assert r2.json()["created_at"] == r1.json()["created_at"]
        # Mock was only invoked for the first request.
        assert mock_classifier.call_count == 1

    async def test_wrong_extension_returns_422(self, db_session):
        response = await _post(VALID_EML, filename="email.txt")
        assert response.status_code == 422
        assert "valid .eml" in response.json()["detail"]

    async def test_oversized_returns_422(self, db_session):
        big = b"From: a@b.com\r\n\r\n" + b"x" * (10 * 1024 * 1024 + 1)
        response = await _post(big)
        assert response.status_code == 422
        assert "too large" in response.json()["detail"]

    async def test_invalid_eml_returns_422(self, db_session):
        no_from = b"To: x@y.com\r\n\r\nbody"
        response = await _post(no_from)
        assert response.status_code == 422
        assert "From header" in response.json()["detail"]

    async def test_classifier_failure_returns_500(self, db_session):
        with patch(
            "app.services.classification_service.classify_email",
            new=AsyncMock(side_effect=RuntimeError("api down")),
        ):
            response = await _post(VALID_EML)
        assert response.status_code == 500
        assert response.json()["detail"] == "Classification failed"


class TestLanguage:
    async def test_defaults_to_en(self, db_session, mock_classifier):
        response = await _post(VALID_EML)

        assert response.status_code == 201
        assert response.json()["language"] == "en"
        assert mock_classifier.call_args.args[1] == LanguageEnum.EN

    async def test_uk_reaches_the_classifier(self, db_session, mock_classifier):
        response = await _post(VALID_EML, language="uk")

        assert response.status_code == 201
        assert response.json()["language"] == "uk"
        assert mock_classifier.call_args.args[1] == LanguageEnum.UK

    async def test_same_file_in_two_languages_makes_two_records(self, db_session, mock_classifier):
        first = await _post(VALID_EML, language="en")
        second = await _post(VALID_EML, language="uk")

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] != second.json()["id"]
        assert mock_classifier.call_count == 2

    async def test_same_file_same_language_is_still_deduplicated(self, db_session, mock_classifier):
        first = await _post(VALID_EML, language="uk")
        second = await _post(VALID_EML, language="uk")

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert mock_classifier.call_count == 1

    async def test_unknown_language_returns_422(self, db_session):
        response = await _post(VALID_EML, language="de")

        assert response.status_code == 422


class TestGetClassify:
    async def test_returns_existing(self, db_session):
        r1 = await _post(VALID_EML)
        record_id = r1.json()["id"]

        r2 = await _get(record_id)
        assert r2.status_code == 200
        body = r2.json()
        assert body["id"] == record_id
        assert body["category"] == "spam"
        assert body["model"] == settings.openai_model
        assert body["created_at"] == r1.json()["created_at"]

    async def test_returns_404_for_missing(self, db_session):
        response = await _get(uuid.uuid4())
        assert response.status_code == 404
        assert response.json()["detail"] == "Record not found"

    async def test_invalid_uuid_returns_422(self, db_session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/classify/not-a-uuid/")
        assert response.status_code == 422


class TestHealth:
    async def test_returns_ok(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
