import json

import httpx
import pytest

from app.helpers.enums import LanguageEnum
from bot.api import (
    ClassifierClient,
    InvalidEmailError,
    RateLimitedError,
    ServiceUnavailableError,
)

PAYLOAD = {"id": "1", "status": "classified", "category": "spam", "confidence": 0.9}
EML = b"From: a@b.com\r\nSubject: s\r\n\r\nbody\r\n"


def _client(handler):
    transport = httpx.MockTransport(handler)
    return ClassifierClient("http://api.test", client=httpx.AsyncClient(transport=transport))


def _responder(status, payload=PAYLOAD, recorder=None):
    def handler(request):
        if recorder is not None:
            recorder.append(request)
        return httpx.Response(status, json=payload)

    return handler


class TestClassify:
    async def test_201_is_a_new_classification(self):
        outcome = await _client(_responder(201)).classify(EML)

        assert outcome.is_duplicate is False
        assert outcome.payload == PAYLOAD

    async def test_200_is_a_duplicate(self):
        outcome = await _client(_responder(200)).classify(EML)

        assert outcome.is_duplicate is True

    async def test_request_shape(self):
        requests = []
        await _client(_responder(201, recorder=requests)).classify(EML, LanguageEnum.UK)

        request = requests[0]
        assert request.method == "POST"
        assert str(request.url) == "http://api.test/classify/"
        body = request.content
        assert b'name="file"; filename="message.eml"' in body
        assert EML in body
        assert b'name="language"' in body
        assert b"uk" in body

    async def test_language_defaults_to_ukrainian(self):
        requests = []
        await _client(_responder(201, recorder=requests)).classify(EML)

        assert b"uk" in requests[0].content

    async def test_force_becomes_a_query_flag(self):
        requests = []
        await _client(_responder(201, recorder=requests)).classify(EML, force=True)

        assert requests[0].url.params["force"] == "true"

    async def test_no_force_query_by_default(self):
        requests = []
        await _client(_responder(201, recorder=requests)).classify(EML)

        assert "force" not in requests[0].url.params

    async def test_trailing_slash_in_base_url_is_normalised(self):
        requests = []
        transport = httpx.MockTransport(_responder(201, recorder=requests))
        client = ClassifierClient("http://api.test/", client=httpx.AsyncClient(transport=transport))

        await client.classify(EML)

        assert str(requests[0].url) == "http://api.test/classify/"


class TestErrorMapping:
    async def test_422_is_an_invalid_email(self):
        with pytest.raises(InvalidEmailError):
            await _client(_responder(422, {"detail": "File must be a valid .eml file"})).classify(EML)

    async def test_429_is_rate_limited(self):
        with pytest.raises(RateLimitedError):
            await _client(_responder(429, {"detail": "rate limited"})).classify(EML)

    @pytest.mark.parametrize("status", [500, 502, 503])
    async def test_5xx_is_unavailable(self, status):
        with pytest.raises(ServiceUnavailableError):
            await _client(_responder(status, {"detail": "boom"})).classify(EML)

    async def test_unexpected_status_is_unavailable(self):
        with pytest.raises(ServiceUnavailableError):
            await _client(_responder(404, {"detail": "nope"})).classify(EML)

    async def test_network_failure_is_unavailable(self):
        def handler(request):
            raise httpx.ConnectError("no route to host")

        with pytest.raises(ServiceUnavailableError):
            await _client(handler).classify(EML)

    async def test_timeout_is_unavailable(self):
        def handler(request):
            raise httpx.ReadTimeout("too slow")

        with pytest.raises(ServiceUnavailableError):
            await _client(handler).classify(EML)

    async def test_undecodable_body_is_unavailable(self):
        def handler(request):
            return httpx.Response(201, content=b"not json")

        with pytest.raises(ServiceUnavailableError):
            await _client(handler).classify(EML)

    async def test_errors_do_not_leak_api_detail(self):
        detail = "internal traceback detail"

        with pytest.raises(ServiceUnavailableError) as raised:
            await _client(_responder(500, {"detail": detail})).classify(EML)

        assert detail not in str(raised.value)


class TestLifecycle:
    async def test_close_closes_the_underlying_client(self):
        transport = httpx.MockTransport(_responder(201))
        inner = httpx.AsyncClient(transport=transport)
        client = ClassifierClient("http://api.test", client=inner)

        await client.aclose()

        assert inner.is_closed

    async def test_payload_is_returned_verbatim(self):
        rich = {**PAYLOAD, "signals": ["a", "b"], "reasoning": "why"}

        outcome = await _client(_responder(201, rich)).classify(EML)

        assert outcome.payload == json.loads(json.dumps(rich))
