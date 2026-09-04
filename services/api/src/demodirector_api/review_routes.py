from typing import Annotated

from demodirector_contracts.quality import VideoReview
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from demodirector_api.video_reviews import ReviewConflict, VideoReviewService

router = APIRouter(tags=["video quality"])


def service(request: Request) -> VideoReviewService:
    result: VideoReviewService | None = request.app.state.video_review_service
    if result is None:
        raise HTTPException(503, "Configure Gemini before reviewing videos.")
    return result


Reviews = Annotated[VideoReviewService, Depends(service)]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retry: bool = False


@router.post("/projects/{project_id}/exports/{export_id}/reviews", response_model=VideoReview)
def review(
    project_id: str, export_id: str, payload: ReviewRequest, reviews: Reviews
) -> VideoReview:
    try:
        return reviews.create(project_id, export_id, retry=payload.retry)
    except KeyError as error:
        raise HTTPException(404, "Export not found") from error
    except ReviewConflict as error:
        raise HTTPException(409, str(error)) from error


@router.get("/projects/{project_id}/exports/{export_id}/reviews/latest", response_model=VideoReview)
def latest(project_id: str, export_id: str, reviews: Reviews) -> VideoReview:
    try:
        result = reviews.latest(project_id, export_id)
    except KeyError as error:
        raise HTTPException(404, "Review not found") from error
    if result is None:
        raise HTTPException(404, "Review not found")
    return result
