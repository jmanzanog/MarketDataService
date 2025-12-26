"""Search endpoint for finding instruments by ISIN."""

import logging

from fastapi import APIRouter, HTTPException

from src.models.schemas import (
    BatchSearchRequest,
    BatchSearchResponse,
    ErrorResponse,
    InstrumentResponse,
    SearchErrorItem,
)
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


@router.post(
    "/batch",
    response_model=BatchSearchResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Batch search instruments by ISIN",
    description="Search for multiple financial instruments using their ISIN codes in parallel.",
)
async def batch_search_by_isins(request: BatchSearchRequest) -> BatchSearchResponse:
    """
    Search for multiple instruments by their ISIN codes.

    Args:
        request: BatchSearchRequest containing list of ISIN codes.

    Returns:
        BatchSearchResponse with successful results and individual errors.
    """
    try:
        results, errors = await yahoo_finance_service.batch_search_by_isins(request.isins)

        error_items = [SearchErrorItem(isin=isin, error=error) for isin, error in errors]

        return BatchSearchResponse(results=results, errors=error_items)

    except Exception as e:
        logger.error(f"Failed to perform batch search: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to perform batch search: {str(e)}",
        ) from e
