import logging
from dataclasses import dataclass
from http import HTTPStatus

import httpx

from app.helpers.enums import LanguageEnum

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 90.0
EML_FILENAME = "message.eml"


class ClassifierError(Exception):
    """Base class for every failure the bot can explain to a user."""


class InvalidEmailError(ClassifierError):
    """The API rejected the upload as not a usable .eml (422)."""


class RateLimitedError(ClassifierError):
    """The API rate limit was hit (429)."""


class ServiceUnavailableError(ClassifierError):
    """The API could not be reached or failed on its side (network, 5xx)."""


@dataclass(frozen=True)
class ClassificationOutcome:
    """One classification response.

    Attributes:
        payload: Decoded ClassificationResponse body.
        is_duplicate: True when the API answered 200, i.e. a cached record.

    """

    payload: dict
    is_duplicate: bool


class ClassifierClient:
    """Thin HTTP client for this repo's classification API.

    The bot is a pure API consumer: it never imports the classification
    service, so the only coupling is this request and the response schema.
    """

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    async def classify(
        self,
        eml: bytes,
        language: LanguageEnum = LanguageEnum.UK,
        force: bool = False,
    ) -> ClassificationOutcome:
        """Classify raw .eml bytes.

        Args:
            eml: Raw .eml file content.
            language: Language for the reasoning and signals.
            force: Bypass the API's cache and overwrite the stored record.

        Returns:
            ClassificationOutcome with the decoded body.

        Raises:
            InvalidEmailError: The API answered 422.
            RateLimitedError: The API answered 429.
            ServiceUnavailableError: Network failure, 5xx, or an undecodable body.

        """
        url = f"{self.base_url}/classify/"

        try:
            response = await self._client.post(
                url,
                files={"file": (EML_FILENAME, eml, "message/rfc822")},
                data={"language": language.value},
                params={"force": "true"} if force else None,
            )
        except httpx.HTTPError:
            logger.exception("Classification request to %s failed", url)
            raise ServiceUnavailableError from None

        # 422; named UNPROCESSABLE_CONTENT only from Python 3.13 on.
        if response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
            raise InvalidEmailError
        if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
            raise RateLimitedError
        if response.status_code not in {HTTPStatus.OK, HTTPStatus.CREATED}:
            logger.error("Classification request to %s returned %s", url, response.status_code)
            raise ServiceUnavailableError

        try:
            payload = response.json()
        except ValueError:
            logger.exception("Classification response from %s was not JSON", url)
            raise ServiceUnavailableError from None

        return ClassificationOutcome(payload=payload, is_duplicate=response.status_code == HTTPStatus.OK)

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()
