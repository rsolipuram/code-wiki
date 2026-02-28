"""Common Pydantic schemas shared across all API responses."""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Pagination(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    pagination: Pagination


class Error(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None
