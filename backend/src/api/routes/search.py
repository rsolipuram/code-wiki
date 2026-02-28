"""Search endpoints — hybrid keyword + semantic search."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.schemas.search import SearchResultItem, SearchResultsResponse
from src.models.code_entity import CodeEntity, Module
from src.models.wiki import Wiki, WikiPage

router = APIRouter(tags=["search"])


def _keyword_search(
    db: Session,
    wiki_id: str,
    q: str,
    search_type: str,
    limit: int,
) -> list[SearchResultItem]:
    """PostgreSQL ILIKE keyword search across pages, modules, and entities."""
    results: list[SearchResultItem] = []
    pattern = f"%{q}%"

    if search_type in ("all", "pages"):
        pages = (
            db.query(WikiPage)
            .filter(
                WikiPage.wiki_id == wiki_id,
                or_(
                    WikiPage.title.ilike(pattern),
                    WikiPage.summary.ilike(pattern),
                ),
            )
            .limit(limit)
            .all()
        )
        for page in pages:
            snippet = page.summary or page.title
            results.append(
                SearchResultItem(
                    type="page",
                    id=page.id,
                    title=page.title,
                    snippet=snippet[:200] if snippet else None,
                    score=1.0,
                )
            )

    if search_type in ("all", "modules"):
        modules = (
            db.query(Module)
            .filter(
                Module.wiki_id == wiki_id,
                or_(
                    Module.name.ilike(pattern),
                    Module.description.ilike(pattern),
                ),
            )
            .limit(limit)
            .all()
        )
        for mod in modules:
            results.append(
                SearchResultItem(
                    type="module",
                    id=mod.id,
                    title=mod.name,
                    snippet=mod.description[:200] if mod.description else None,
                    score=1.0,
                )
            )

    if search_type in ("all", "entities"):
        entities = (
            db.query(CodeEntity)
            .join(Module, CodeEntity.module_id == Module.id)
            .filter(
                Module.wiki_id == wiki_id,
                or_(
                    CodeEntity.name.ilike(pattern),
                    CodeEntity.qualified_name.ilike(pattern),
                    CodeEntity.docstring.ilike(pattern),
                ),
            )
            .limit(limit)
            .all()
        )
        for ent in entities:
            results.append(
                SearchResultItem(
                    type="entity",
                    id=ent.id,
                    title=f"{ent.qualified_name} ({ent.entity_type})",
                    snippet=(ent.docstring or ent.signature or "")[:200] or None,
                    score=1.0,
                )
            )

    return results


def _semantic_search(
    wiki_id: str,
    q: str,
    limit: int,
) -> list[SearchResultItem]:
    """Qdrant semantic search over code entities (best-effort; returns empty on failure)."""
    try:
        from src.llm.embeddings import embed
        from src.storage.vector_db import search, COLLECTION_CODE_ENTITIES

        vector = embed(q)
        hits = search(
            collection=COLLECTION_CODE_ENTITIES,
            vector=vector,
            limit=limit,
            filters={"wiki_id": wiki_id},
            score_threshold=0.3,
        )
        return [
            SearchResultItem(
                type="entity",
                id=h["payload"].get("entity_id", h["id"]),
                title=h["payload"].get("qualified_name", h["id"]),
                snippet=h["payload"].get("docstring", "")[:200] or None,
                score=h["score"],
            )
            for h in hits
        ]
    except Exception:
        return []


@router.get("/search/{repository_id}", response_model=SearchResultsResponse)
async def search_wiki(
    repository_id: UUID,
    q: str = Query(..., description="Search query"),
    search_type: str = Query("all", alias="type"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SearchResultsResponse:
    """Hybrid keyword + semantic search across wiki pages, modules, and entities."""
    if not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'q' must not be empty",
        )

    wiki = db.query(Wiki).filter_by(repository_id=str(repository_id)).first()
    if not wiki:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wiki not found for this repository",
        )

    # Keyword results from PostgreSQL
    keyword_results = _keyword_search(db, wiki.id, q, search_type, limit)

    # Semantic results from Qdrant (best-effort)
    semantic_results = _semantic_search(wiki.id, q, limit // 2)

    # Merge: keyword first, then unique semantic results
    seen_ids: set[str] = {r.id for r in keyword_results}
    merged: list[SearchResultItem] = list(keyword_results)
    for item in semantic_results:
        if item.id not in seen_ids:
            merged.append(item)
            seen_ids.add(item.id)

    # Sort by score descending, cap at limit
    merged.sort(key=lambda r: r.score or 0, reverse=True)
    merged = merged[:limit]

    return SearchResultsResponse(
        query=q,
        total_results=len(merged),
        results=merged,
    )
