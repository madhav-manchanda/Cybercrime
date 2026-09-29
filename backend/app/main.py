"""Application entrypoint: FastAPI factory, middleware, routes, handlers.

The development/local configuration bootstraps the SQLite schema on startup so
the prototype runs out of the box.  Production (Postgres) relies on Alembic
migrations instead; ``init_sync_schema`` is a no-op guard there.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.database import close_db_engine, init_sync_schema, is_postgres
from app.core.errors import (
    ValidationError_,
    error_payload,
    format_traceback,
    request_id_of,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from app.ml.model_registry import registry

logger = structlog.get_logger("app")


@asynccontextmanager
async def _lifecycle(app: FastAPI):
    configure_logging()
    if not is_postgres(settings.async_database_url):
        init_sync_schema()
    registry.clear_cache()
    logger.info(
        "api_startup",
        app=settings.app_slug,
        version=settings.app_version,
        database="postgres" if is_postgres(settings.async_database_url) else "sqlite",
    )
    yield
    await close_db_engine()
    registry.clear_cache()
    logger.info("api_shutdown", app=settings.app_slug)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=_lifecycle,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        description=(
            "Cybercrime predictive cash-out intelligence platform (prototype). "
            "All metrics, predictions and analytics are generated from explicitly "
            "tagged synthetic data unless stated otherwise."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins or ["http://localhost:3000"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "app": settings.app_name,
            "slug": settings.app_slug,
            "version": settings.app_version,
            "docs": "/docs",
        }

    @app.get("/health", tags=["system"])
    async def health(request: Request) -> dict[str, Any]:
        return {
            "status": "ok",
            "request_id": request_id_of(request),
            "database": "postgres" if is_postgres(settings.async_database_url) else "sqlite",
        }

    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    from app.core.errors import AppError

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc, request_id_of(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "loc": list(err.get("loc") or []),
                "msg": err.get("msg"),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        err = ValidationError_("One or more request fields are invalid.", code="VALIDATION_ERROR")
        err.details = {"fields": details}
        return JSONResponse(
            status_code=err.status_code,
            content=error_payload(err, request_id_of(request)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        error_id = str(uuid.uuid4())
        logger.error(
            "unhandled_exception",
            request_id=request_id_of(request),
            error_id=error_id,
            path=getattr(request, "url", None) and str(request.url),
            exc_info=format_traceback(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred.",
                    "request_id": request_id_of(request),
                    "details": {"error_id": error_id},
                }
            },
        )


app = create_app()

__all__ = ["app", "create_app"]
