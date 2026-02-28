"""Wiki browsing endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.schemas.wikis import (
    CodeEntityResponse,
    CodeEntityRelationships,
    DiagramData,
    DiagramEdge,
    DiagramNode,
    DiagramsResponse,
    ModuleResponse,
    WikiPageResponse,
    WikiResponse,
)
from src.models.code_entity import CodeEntity, Module
from src.models.wiki import Wiki, WikiPage
from src.storage import graph_db
from src.wiki.page_builders.diagrams import build_diagrams

router = APIRouter(prefix="/wikis", tags=["wikis"])


def _wiki_to_response(wiki: Wiki) -> WikiResponse:
    # Home page is first page with page_type=home
    home_page = next((p for p in wiki.pages if p.page_type == "home"), None)
    return WikiResponse(
        id=UUID(wiki.id),
        repository_id=UUID(wiki.repository_id),
        home_page_id=UUID(home_page.id) if home_page else None,
        structure_version=wiki.version,
        module_count=wiki.module_count,
        page_count=wiki.page_count,
        status="ready",
        generated_at=wiki.created_at,
        updated_at=wiki.updated_at,
    )


def _page_to_response(page: WikiPage) -> WikiPageResponse:
    return WikiPageResponse(
        id=UUID(page.id),
        wiki_id=UUID(page.wiki_id),
        page_type=page.page_type.value if hasattr(page.page_type, "value") else str(page.page_type),
        title=page.title,
        slug=page.slug,
        content=page.content or {},
        related_page_ids=[],
        source_files=page.source_files or [],
        commit_hash=page.commit_hash,
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


def _module_to_response(module: Module) -> ModuleResponse:
    return ModuleResponse(
        id=UUID(module.id),
        wiki_id=UUID(module.wiki_id),
        name=module.name,
        slug=module.slug,
        file_paths=module.file_paths or [],
        file_count=module.file_count,
        line_count=module.line_count,
        description=module.description,
        detection_confidence=module.detection_confidence,
        dependencies_module_ids=[UUID(d) for d in (module.dependency_module_ids or [])],
        created_at=module.created_at,
    )


def _get_wiki_for_repo(db: Session, repository_id: UUID) -> Wiki:
    wiki = db.query(Wiki).filter_by(repository_id=str(repository_id)).first()
    if not wiki:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wiki not found for this repository",
        )
    return wiki


@router.get("/{repository_id}", response_model=WikiResponse)
async def get_wiki(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> WikiResponse:
    """Get wiki for a repository."""
    wiki = _get_wiki_for_repo(db, repository_id)
    return _wiki_to_response(wiki)


@router.get("/{repository_id}/pages", response_model=list[WikiPageResponse])
async def list_wiki_pages(
    repository_id: UUID,
    page_type: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[WikiPageResponse]:
    """List all wiki pages for a repository."""
    wiki = _get_wiki_for_repo(db, repository_id)
    q = db.query(WikiPage).filter_by(wiki_id=wiki.id)
    if page_type:
        q = q.filter(WikiPage.page_type == page_type)
    pages = q.order_by(WikiPage.created_at).all()
    return [_page_to_response(p) for p in pages]


@router.get("/{repository_id}/pages/{page_slug}", response_model=WikiPageResponse)
async def get_wiki_page(
    repository_id: UUID,
    page_slug: str,
    db: Session = Depends(get_db),
) -> WikiPageResponse:
    """Get a wiki page by slug."""
    wiki = _get_wiki_for_repo(db, repository_id)
    page = db.query(WikiPage).filter_by(wiki_id=wiki.id, slug=page_slug).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return _page_to_response(page)


@router.get("/{repository_id}/modules", response_model=list[ModuleResponse])
async def list_modules(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> list[ModuleResponse]:
    """List detected modules for a repository."""
    wiki = _get_wiki_for_repo(db, repository_id)
    modules = db.query(Module).filter_by(wiki_id=wiki.id).order_by(Module.name).all()
    return [_module_to_response(m) for m in modules]


@router.get("/{repository_id}/modules/{module_slug}", response_model=ModuleResponse)
async def get_module(
    repository_id: UUID,
    module_slug: str,
    db: Session = Depends(get_db),
) -> ModuleResponse:
    """Get module details."""
    wiki = _get_wiki_for_repo(db, repository_id)
    module = db.query(Module).filter_by(wiki_id=wiki.id, slug=module_slug).first()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    return _module_to_response(module)


@router.get("/{repository_id}/diagrams", response_model=DiagramsResponse)
async def get_diagrams(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> DiagramsResponse:
    """Return diagram data (architecture, dependency-graph, module-relationships) for a repository."""
    wiki = _get_wiki_for_repo(db, repository_id)
    raw = build_diagrams(db, wiki)

    def _to_diagram_data(d: dict) -> DiagramData:
        nodes = [DiagramNode(**n) for n in d.get("nodes", [])]
        edges = [
            DiagramEdge(from_=e.get("from", ""), to=e.get("to", ""), **{k: v for k, v in e.items() if k not in ("from", "to")})
            for e in d.get("edges", [])
        ]
        return DiagramData(nodes=nodes, edges=edges)

    return DiagramsResponse(
        architecture=_to_diagram_data(raw["architecture"]),
        dependency_graph=_to_diagram_data(raw["dependency_graph"]),
        module_relationships=_to_diagram_data(raw["module_relationships"]),
    )


@router.get(
    "/{repository_id}/entities/{entity_qualified_name:path}",
    response_model=CodeEntityResponse,
)
async def get_code_entity(
    repository_id: UUID,
    entity_qualified_name: str,
    db: Session = Depends(get_db),
) -> CodeEntityResponse:
    """Get code entity details by qualified name, including Neo4j relationships."""
    wiki = _get_wiki_for_repo(db, repository_id)

    # Find entity across all modules in this wiki
    entity = (
        db.query(CodeEntity)
        .join(Module, CodeEntity.module_id == Module.id)
        .filter(Module.wiki_id == wiki.id, CodeEntity.qualified_name == entity_qualified_name)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    # Fetch relationships from Neo4j
    relationships = CodeEntityRelationships()
    try:
        driver = graph_db.get_driver()
        with driver.session() as neo_session:
            result = neo_session.run(
                """
                MATCH (n {qualified_name: $qname})
                OPTIONAL MATCH (n)-[:CALLS]->(callee)
                OPTIONAL MATCH (n)-[:IMPORTS]->(imported)
                OPTIONAL MATCH (n)-[:INHERITS_FROM]->(parent)
                RETURN
                  collect(DISTINCT callee.qualified_name) AS calls,
                  collect(DISTINCT imported.qualified_name) AS imports,
                  collect(DISTINCT parent.qualified_name) AS inherits_from
                """,
                qname=entity_qualified_name,
            )
            row = result.single()
            if row:
                relationships = CodeEntityRelationships(
                    calls=[c for c in row["calls"] if c],
                    imports=[i for i in row["imports"] if i],
                    inherits_from=[p for p in row["inherits_from"] if p],
                )
    except Exception:
        pass  # Neo4j unavailable — return empty relationships

    visibility = "private" if entity.name.startswith("_") else "public"

    return CodeEntityResponse(
        id=UUID(entity.id),
        module_id=UUID(entity.module_id),
        entity_type=entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type),
        name=entity.name,
        qualified_name=entity.qualified_name,
        file_path=entity.file_path or "",
        line_number=entity.line_start or 0,
        signature=entity.signature,
        description=entity.description,
        docstring=entity.docstring,
        visibility=visibility,
        relationships=relationships,
    )
