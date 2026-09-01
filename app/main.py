from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.rate_limit import limiter, rate_limit_handler
from app.routers.classify import router as classify_router
from app.routers.health import router as health_router

STATIC_DIR = Path(__file__).parent / "static"
SAMPLES_DIR = STATIC_DIR / "samples"

# "no-cache" (not "no-store"): the browser may keep the file but must check with
# the server before reusing it, so an edit here shows up without a hard refresh.
# These two are small and change often; the .eml samples behind them stay cacheable.
NO_CACHE = {"Cache-Control": "no-cache"}

app = FastAPI(
    title="Email Classifier",
    description="REST API that classifies .eml files using LLM",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.include_router(health_router)
app.include_router(classify_router)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Serve the single-page demo frontend, never from a stale browser cache."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html", headers=NO_CACHE)


@app.get("/static/samples/samples.json", include_in_schema=False)
async def samples_manifest() -> FileResponse:
    """Serve the samples manifest uncached.

    Declared before the /static mount so it wins the route match. Only the
    manifest is special-cased; the .eml files behind it stay cacheable.
    """
    return FileResponse(SAMPLES_DIR / "samples.json", media_type="application/json", headers=NO_CACHE)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
