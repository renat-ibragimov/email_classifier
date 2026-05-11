from fastapi import FastAPI

from app.routers.classify import router as classify_router

app = FastAPI(
    title="Email Classifier",
    description="REST API that classifies .eml files using LLM",
    version="0.1.0",
)

app.include_router(classify_router)


@app.get("/health")
async def health():
    return {"status": "ok"}