"""Pydantic schemas for wiki, module, and code entity endpoints."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class WikiResponse(BaseModel):
    id: UUID
    repository_id: UUID
    home_page_id: Optional[UUID] = None
    structure_version: Optional[int] = None
    module_count: Optional[int] = None
    page_count: Optional[int] = None
    status: str  # generating | ready | updating
    generated_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WikiPageResponse(BaseModel):
    id: UUID
    wiki_id: Optional[UUID] = None
    page_type: str  # home | module | getting_started | function_index | glossary | api_reference
    title: str
    slug: str
    content: dict[str, Any]
    related_page_ids: list[UUID] = []
    source_files: list[str] = []
    commit_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ModuleResponse(BaseModel):
    id: UUID
    wiki_id: Optional[UUID] = None
    wiki_page_id: Optional[UUID] = None
    name: str
    slug: str
    file_paths: list[str]
    file_count: Optional[int] = None
    line_count: Optional[int] = None
    description: Optional[str] = None
    detection_confidence: Optional[float] = None
    dependencies_module_ids: list[UUID] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DiagramNode(BaseModel):
    id: str
    label: str
    sublabel: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    tier: Optional[str] = None
    file_count: Optional[int] = None
    slug: Optional[str] = None
    call_count: Optional[int] = None


class DiagramEdge(BaseModel):
    from_: str
    to: str
    label: Optional[str] = None
    rel_type: Optional[str] = None
    weight: Optional[int] = None

    model_config = {"populate_by_name": True}


class DiagramData(BaseModel):
    nodes: list[DiagramNode] = []
    edges: list[DiagramEdge] = []


class DiagramsResponse(BaseModel):
    architecture: DiagramData = DiagramData()
    dependency_graph: DiagramData = DiagramData()
    module_relationships: DiagramData = DiagramData()


class CodeEntityRelationships(BaseModel):
    calls: list[str] = []
    imports: list[str] = []
    inherits_from: list[str] = []


class CodeEntityResponse(BaseModel):
    id: UUID
    module_id: Optional[UUID] = None
    entity_type: str  # function | class | method | module | file | variable
    name: str
    qualified_name: str
    file_path: str
    line_number: int
    signature: Optional[str] = None
    description: Optional[str] = None
    docstring: Optional[str] = None
    visibility: Optional[str] = None  # public | private | protected
    relationships: Optional[CodeEntityRelationships] = None

    model_config = {"from_attributes": True}
