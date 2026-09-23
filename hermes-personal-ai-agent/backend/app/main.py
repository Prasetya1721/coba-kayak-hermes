"""Hermes Personal AI Agent — FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import limiter
from app.db.seed import seed_builtin_templates
from app.db.session import close_redis, engine
from app.middleware.http import RequestContextMiddleware, SecurityHeadersMiddleware
from app.services.notification_scheduler import start_scheduler, stop_scheduler

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings.assert_production_safety()
    log.info("startup", environment=settings.environment, provider=settings.llm_provider)

    try:
        await seed_builtin_templates()
    except Exception as exc:  # noqa: BLE001
        log.warning("seed_templates_failed", error=str(exc))

    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()
    await engine.dispose()
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Middleware (order matters: outermost first).
    app.add_middleware(
        SecurityHeadersMiddleware, hsts=settings.is_production
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok", "service": settings.app_name}

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", None)
        log.error("unhandled_error", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "Terjadi kesalahan internal.", "request_id": request_id},
        )

    return app


app = create_app()
