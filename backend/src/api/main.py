"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.health import router as health_router
from src.api.routes.chat import router as chat_router
from src.api.routes.repositories import router as repositories_router
from src.api.routes.search import router as search_router
from src.api.routes.webhooks import router as webhooks_router
from src.api.routes.wikis import router as wikis_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    yield


app = FastAPI(
    title="Code Wiki API",
    description="AI-powered code documentation platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3010",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"code": "NOT_FOUND", "message": "Resource not found"},
    )


@app.exception_handler(422)
async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"code": "VALIDATION_ERROR", "message": str(exc)},
    )


# Routers
app.include_router(health_router)
app.include_router(repositories_router, prefix="/v1")
app.include_router(wikis_router, prefix="/v1")
app.include_router(chat_router, prefix="/v1")
app.include_router(search_router, prefix="/v1")
app.include_router(webhooks_router, prefix="/v1")
