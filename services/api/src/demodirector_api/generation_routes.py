from typing import Annotated

from demodirector_contracts import DemoGenerationResult
from fastapi import APIRouter, Depends, HTTPException, Request, status

from demodirector_api.auth_routes import bearer_token
from demodirector_api.generation import (
    DemoGenerationConflict,
    DemoGenerationError,
    DemoGenerationService,
)


def get_generation_service(request: Request) -> DemoGenerationService:
    service = request.app.state.generation_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configure Gemini before generating a demo.",
        )
    return service  # type: ignore[no-any-return]


Generation = Annotated[DemoGenerationService, Depends(get_generation_service)]
router = APIRouter(tags=["generation"])


@router.post(
    "/projects/{project_id}/generate",
    response_model=DemoGenerationResult,
    status_code=status.HTTP_200_OK,
)
def generate_demo(
    project_id: str,
    generation: Generation,
    request: Request,
) -> DemoGenerationResult:
    try:
        return generation.generate(
            project_id,
            capture_session_token=bearer_token(request.headers.get("authorization")),
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        ) from error
    except DemoGenerationConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except DemoGenerationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
