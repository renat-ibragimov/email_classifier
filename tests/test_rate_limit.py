from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.helpers.dto import ClassificationResult
from app.helpers.enums import EmailCategoryEnum
from app.main import app
from app.rate_limit import CLASSIFY_RATE_LIMIT, get_client_ip

# "10/minute" -> 10; keeps the test honest if the configured limit changes.
LIMIT = int(CLASSIFY_RATE_LIMIT.split("/")[0])

VALID_EML = (
    b"From: sender@example.com\r\n"
    b"To: to@example.com\r\n"
    b"Subject: s\r\n"
    b"\r\n"
    b"body\r\n"
)


def _request(headers=None, client_host="10.0.0.1"):
    request = MagicMock()
    request.headers = headers or {}
    request.client = MagicMock(host=client_host) if client_host else None
    return request


@pytest.fixture(autouse=True)
def mock_classifier():
    """Patch classify_email so rate-limit tests never hit OpenAI."""
    with patch(
        "app.services.classification_service.classify_email",
        new=AsyncMock(
            return_value=ClassificationResult(
                category=EmailCategoryEnum.SPAM,
                confidence=0.95,
                reasoning="r",
                signals=["s"],
                reviewed=False,
            )
        ),
    ) as mock:
        yield mock


async def _post(client_ip):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/classify/",
            files={"file": ("email.eml", VALID_EML, "application/octet-stream")},
            headers={"X-Forwarded-For": client_ip},
        )


class TestGetClientIp:

    def test_prefers_first_forwarded_for_entry(self):
        request = _request({"x-forwarded-for": "203.0.113.5, 70.41.3.18, 150.172.238.178"})
        assert get_client_ip(request) == "203.0.113.5"

    def test_strips_whitespace(self):
        request = _request({"x-forwarded-for": "  203.0.113.5  "})
        assert get_client_ip(request) == "203.0.113.5"

    def test_falls_back_to_peer_address(self):
        assert get_client_ip(_request()) == "10.0.0.1"

    def test_returns_unknown_without_client(self):
        assert get_client_ip(_request(client_host=None)) == "unknown"


class TestClassifyRateLimit:
    """Integration coverage: the limit is enforced by the real app + middleware stack."""

    async def test_requests_up_to_the_limit_are_allowed(self, db_session):
        for _ in range(LIMIT):
            response = await _post("203.0.113.10")
            # 201 for the first upload, 200 for the deduplicated repeats.
            assert response.status_code in (200, 201)

    async def test_request_past_the_limit_returns_429(self, db_session):
        for _ in range(LIMIT):
            await _post("203.0.113.10")

        response = await _post("203.0.113.10")

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"

        body = response.json()
        assert "Rate limit exceeded" in body["detail"]
        assert CLASSIFY_RATE_LIMIT.split("/")[0] in body["detail"]

    async def test_limit_is_keyed_on_forwarded_client_ip(self, db_session):
        for _ in range(LIMIT + 1):
            await _post("203.0.113.10")

        # A different forwarded client still has its own budget.
        response = await _post("203.0.113.11")

        assert response.status_code == 200

    async def test_counters_are_isolated_between_tests(self, db_session):
        """The autouse reset_rate_limiter fixture must clear the IP exhausted above."""
        response = await _post("203.0.113.10")

        assert response.status_code != 429
        assert response.status_code in (200, 201)
