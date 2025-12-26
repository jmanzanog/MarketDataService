"""Pydantic models for API request/response schemas."""

from pydantic import BaseModel, Field


class InstrumentResponse(BaseModel):
    """Response model for instrument search."""

    isin: str = Field(..., description="ISIN code of the instrument")
    symbol: str = Field(..., description="Trading symbol (ticker)")
    name: str = Field(..., description="Instrument name")
    type: str = Field(..., description="Instrument type (stock, etf)")
    currency: str = Field(..., description="Trading currency")
    exchange: str = Field(..., description="Stock exchange")


class QuoteResponse(BaseModel):
    """Response model for quote data."""

    symbol: str = Field(..., description="Trading symbol")
    price: str = Field(..., description="Current price as string for precision")
    currency: str = Field(..., description="Price currency")
    time: str = Field(..., description="Quote timestamp in ISO format")


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")


class ErrorResponse(BaseModel):
    """Response model for errors."""

    error: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Additional error details")


# Batch request models
class BatchSearchRequest(BaseModel):
    """Request model for batch ISIN search."""

    isins: list[str] = Field(..., description="List of ISIN codes to search")


class BatchQuoteRequest(BaseModel):
    """Request model for batch quote retrieval."""

    symbols: list[str] = Field(..., description="List of trading symbols")


# Batch error item models
class SearchErrorItem(BaseModel):
    """Error item for batch search response."""

    isin: str = Field(..., description="ISIN that failed")
    error: str = Field(..., description="Error message")


class QuoteErrorItem(BaseModel):
    """Error item for batch quote response."""

    symbol: str = Field(..., description="Symbol that failed")
    error: str = Field(..., description="Error message")


# Batch response models
class BatchSearchResponse(BaseModel):
    """Response model for batch ISIN search."""

    results: list[InstrumentResponse] = Field(
        default_factory=list, description="Successful search results"
    )
    errors: list[SearchErrorItem] = Field(default_factory=list, description="Failed search items")


class BatchQuoteResponse(BaseModel):
    """Response model for batch quote retrieval."""

    results: list[QuoteResponse] = Field(
        default_factory=list, description="Successful quote results"
    )
    errors: list[QuoteErrorItem] = Field(default_factory=list, description="Failed quote items")
