"""In-memory, per-client-IP rate limiting for the public API."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

CLASSIFY_RATE_LIMIT = "10/minute"


def get_client_ip(request: Request) -> str:
    """Resolve the caller's IP, trusting `X-Forwarded-For` from the reverse proxy.

    The app runs behind Caddy, so `request.client` is always the proxy. The first
    entry of `X-Forwarded-For` is the original client.

    Args:
        request: Incoming request.

    Returns:
        Client IP address, or "unknown" when it cannot be determined.

    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_client_ip)


def rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Render `RateLimitExceeded` as a JSON 429 matching the API's error shape.

    Args:
        _request: Incoming request; unused, but part of the handler signature.
        exc: The raised rate-limit error carrying the exceeded limit.

    Returns:
        429 response with a `detail` field.

    """
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers={"Retry-After": "60"},
    )
