"""Pydantic schemas for search endpoints."""

from typing import Optional

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    type: str  # page | entity | module
    id: str
    title: str
    snippet: Optional[str] = None
    score: Optional[float] = None


class SearchResultsResponse(BaseModel):
    query: str
    total_results: int
    results: list[SearchResultItem]
