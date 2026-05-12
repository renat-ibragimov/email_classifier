import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.repositories.classification import ClassificationRepository
from app.schemas.classification import ClassificationResponse
from app.services.classification_service import ClassificationService

logger = logging.getLogger(__name__)

MAX_SIZE = 10 * 1024 * 1024

router = APIRouter(prefix="/classify", tags=["classify"])


@router.post(
    "/",
    response_model=ClassificationResponse,
    summary="Classify an .eml file",
)
async def post_classify(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
):
    """Accept an .eml file, classify it using LLM, and store the result.

    - **201 Created**: new file, classification performed.
    - **200 OK**: duplicate file, returns existing record.
    - **422 Unprocessable Entity**: file is not a valid .eml.
    """
    if not file.filename or not file.filename.endswith(".eml"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File must be a valid .eml file",
        )

    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File too large, maximum size is 10 MB",
        )

    repo = ClassificationRepository(session)
    service = ClassificationService(repo)

    try:
        record, is_new = await service.classify(content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.exception(f"Classification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Classification failed",
        )

    response = ClassificationResponse.model_validate(record)
    status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK

    return JSONResponse(content=response.model_dump(mode="json"), status_code=status_code)


@router.get(
    "/{record_id}/",
    response_model=ClassificationResponse,
    summary="Get classification by ID",
)
async def get_classify(
    record_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Retrieve a classification record by its ID.

    - **200 OK**: record found.
    - **404 Not Found**: no record with this ID.
    """
    repo = ClassificationRepository(session)
    record = await repo.find_by_id(record_id)

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    return ClassificationResponse.model_validate(record)
