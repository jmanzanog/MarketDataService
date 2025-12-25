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
