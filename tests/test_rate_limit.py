from unittest.mock import MagicMock

from app.rate_limit import get_client_ip


def _request(headers=None, client_host="10.0.0.1"):
    request = MagicMock()
    request.headers = headers or {}
    request.client = MagicMock(host=client_host) if client_host else None
    return request


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
