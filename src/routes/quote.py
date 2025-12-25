"""Quote endpoint for getting current stock prices."""

import logging

from fastapi import APIRouter, HTTPException

from src.models.schemas import ErrorResponse, QuoteResponse
from src.services.yahoo_finance import yahoo_finance_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quote", tags=["quote"])


@router.get(
    "/{symbol}",
    response_model=QuoteResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Quote not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get quote by symbol",
    description="Get current price quote for a trading symbol.",
)
async def get_quote(symbol: str) -> QuoteResponse:
    """
    Get current quote for a trading symbol.

    Args:
        symbol: The trading symbol (e.g., AAPL, RR.L).

    Returns:
        QuoteResponse with current price data.

    Raises:
        HTTPException: 404 if quote not found, 500 on error.
    """
    try:
        result = yahoo_finance_service.get_quote(symbol)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"No quote found for symbol: {symbol}",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quote for {symbol}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get quote: {str(e)}",
        ) from e
