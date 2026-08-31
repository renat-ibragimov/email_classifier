from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from app.rate_limit import limiter, rate_limit_handler
from app.routers.classify import router as classify_router
from app.routers.health import router as health_router

app = FastAPI(
    title="Email Classifier",
    description="REST API that classifies .eml files using LLM",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.include_router(health_router)
app.include_router(classify_router)
