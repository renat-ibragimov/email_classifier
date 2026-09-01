import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.helpers.enums import LanguageEnum
from app.rate_limit import CLASSIFY_RATE_LIMIT, limiter
from app.repositories.classification import ClassificationRepository
from app.schemas.classification import ClassificationResponse
from app.services.classification_service import ClassificationService

logger = logging.getLogger(__name__)

MAX_SIZE = 10 * 1024 * 1024

router = APIRouter(prefix="/classify", tags=["classify"])


def get_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClassificationRepository:
    """Build a ClassificationRepository bound to the current request's session."""
    return ClassificationRepository(session)


RepoDep = Annotated[ClassificationRepository, Depends(get_repo)]


@router.post(
    "/",
    response_model=ClassificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Classify an .eml file",
    description=(
        "Upload an `.eml` file as multipart form data.\n\n"
        "The optional `language` form field selects the language of the LLM-written parts "
        "of the answer (`reasoning` and `signals`): `en` (default) or `uk`. Any other value "
        "is rejected with `422`. The `category` value is always one of the English enum "
        "members regardless of the language.\n\n"
        "Deduplication is scoped to the language: the same file requested as `en` and then "
        "as `uk` produces two records, each classified once. Pass `?force=true` to re-run the "
        "classification and overwrite the stored record instead of returning the cached one; "
        "the record keeps its id and `created_at`."
    ),
    responses={
        status.HTTP_200_OK: {
            "model": ClassificationResponse,
            "description": "Duplicate of an already-classified file; returns the cached record.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Invalid `.eml`: wrong extension, file > 10 MB, or missing `From` header.",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": f"Rate limit exceeded (max {CLASSIFY_RATE_LIMIT} per client IP).",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Classification failed; the record is persisted with `status=failed` and can be retried.",
        },
    },
)
@limiter.limit(CLASSIFY_RATE_LIMIT)
async def post_classify(
    request: Request,  # ruff: ignore[unused-function-argument] (slowapi reads it)
    file: UploadFile,
    repo: RepoDep,
    language: Annotated[LanguageEnum, Form(description="Language of the reasoning and signals")] = LanguageEnum.EN,
    force: Annotated[bool, Query(description="Re-classify and overwrite the cached record")] = False,
) -> JSONResponse:
    """Accept an .eml file, classify it using LLM in the requested language, and store the result."""
    if not file.filename or not file.filename.endswith(".eml"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File must be a valid .eml file",
        )

    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File too large, maximum size is 10 MB",
        )

    service = ClassificationService(repo)

    try:
        record, is_new = await service.classify(content, language, force=force)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e
    except Exception as e:
        logger.exception("Classification failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Classification failed",
        ) from e

    response = ClassificationResponse.model_validate(record)
    status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK

    return JSONResponse(content=response.model_dump(mode="json"), status_code=status_code)


@router.get(
    "/{record_id}/",
    response_model=ClassificationResponse,
    summary="Get classification by ID",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "No record with this ID."},
    },
)
async def get_classify(
    record_id: uuid.UUID,
    repo: RepoDep,
) -> ClassificationResponse:
    """Retrieve a classification record by its ID."""
    record = await repo.find_by_id(record_id)

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    return ClassificationResponse.model_validate(record)
