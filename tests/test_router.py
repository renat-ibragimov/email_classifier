import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.helpers.dto import ClassificationResult
from app.helpers.enums import EmailCategoryEnum
from app.main import app

VALID_EML = (
    b"From: sender@example.com\r\n"
    b"To: to@example.com\r\n"
    b"Subject: s\r\n"
    b"\r\n"
    b"body\r\n"
)


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


async def _post(eml_bytes, filename="email.eml"):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/classify/",
            files={"file": (filename, eml_bytes, "application/octet-stream")},
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

    async def test_duplicate_returns_200(self, db_session, mock_classifier):
        r1 = await _post(VALID_EML)
        assert r1.status_code == 201

        r2 = await _post(VALID_EML)
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]
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


class TestGetClassify:

    async def test_returns_existing(self, db_session):
        r1 = await _post(VALID_EML)
        record_id = r1.json()["id"]

        r2 = await _get(record_id)
        assert r2.status_code == 200
        body = r2.json()
        assert body["id"] == record_id
        assert body["category"] == "spam"

    async def test_returns_404_for_missing(self, db_session):
        response = await _get(uuid.uuid4())
        assert response.status_code == 404
        assert response.json()["detail"] == "Record not found"

    async def test_invalid_uuid_returns_422(self, db_session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/classify/not-a-uuid/")
        assert response.status_code == 422
