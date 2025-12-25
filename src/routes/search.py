"""Search endpoint for finding instruments by ISIN."""

import logging

from fastapi import APIRouter, HTTPException

from src.models.schemas import ErrorResponse, InstrumentResponse
from src.services.yahoo_finance import yahoo_finance_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.get(
    "/{isin}",
    response_model=InstrumentResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Instrument not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Search instrument by ISIN",
    description="Search for a financial instrument using its ISIN code.",
)
async def search_by_isin(isin: str) -> InstrumentResponse:
    """
    Search for an instrument by its ISIN code.

    Args:
        isin: The ISIN code (e.g., US0378331005 for Apple).

    Returns:
        InstrumentResponse with instrument details.

    Raises:
        HTTPException: 404 if instrument not found, 500 on error.
    """
    try:
        result = yahoo_finance_service.search_by_isin(isin)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"No instrument found for ISIN: {isin}",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search for ISIN {isin}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search for instrument: {str(e)}",
        ) from e
