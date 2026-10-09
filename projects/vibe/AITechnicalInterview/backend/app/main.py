"""Точка входа FastAPI: REST API, WebSocket, CORS, создание таблиц при старте."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_auth import require_admin
from app.api.deps import voice_pipeline
from app.api.routes import employers_router, interviews_router, templates_router
from app.config import get_settings
from app.database import engine
from app.db_migrate import ensure_schema
from app.websocket.handler import ws_router
from app.services.voice_pipeline import SttUnavailableError


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(ensure_schema)
    try:
        await asyncio.wait_for(voice_pipeline.warmup_stt(), timeout=300)
    except SttUnavailableError as exc:
        logging.getLogger("uvicorn.error").warning("STT warmup skipped: %s", exc)
    except asyncio.TimeoutError:
        logging.getLogger("uvicorn.error").warning("STT warmup timed out after 300s")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.getLogger("uvicorn.error").info(
        "LLM model: %s provider=%s (mock_ai=%s) | STT=%s",
        settings.llm_model,
        settings.llm_provider,
        settings.mock_ai,
        settings.stt_provider,
    )
    app = FastAPI(
        title="AI Technical Interview Platform",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(employers_router, prefix="/api/v1")
    app.include_router(templates_router, prefix="/api/v1")
    app.include_router(interviews_router, prefix="/api/v1")
    app.include_router(ws_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/admin/me")
    async def admin_me(username: str = Depends(require_admin)):
        """Проверка логина/пароля админки."""
        return {"ok": True, "username": username}

    return app


app = create_app()
