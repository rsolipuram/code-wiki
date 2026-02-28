"""Pydantic schemas for repository endpoints."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl

from src.api.schemas.common import Pagination


class RepositoryCreate(BaseModel):
    url: str
    access_token: Optional[str] = None
    branch: str = "main"


class RepositoryResponse(BaseModel):
    id: UUID
    url: str
    name: str
    owner: str
    primary_languages: list[str] = []
    size_lines: Optional[int] = None
    size_files: Optional[int] = None
    last_analyzed_commit: Optional[str] = None
    last_analyzed_at: Optional[datetime] = None
    branch: Optional[str] = None
    status: str  # pending | analyzing | ready | error
    error_message: Optional[str] = None
    progress: Optional[dict] = None
    access_level: Optional[str] = None  # public | private
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RepositoryListResponse(BaseModel):
    repositories: list[RepositoryResponse]
    pagination: Pagination


class UpdateEventResponse(BaseModel):
    id: UUID
    repository_id: UUID
    commit_hash: str
    changed_files: list[str] = []
    affected_module_ids: list[UUID] = []
    status: str  # pending | processing | completed | failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}
