from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.session import init_db
from app.api.routes import router
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    settings = get_settings()
    logger.info(f"Database: {settings.db_path}")
    logger.info(f"Retrieval: lightweight local (n-gram)")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"Mock mode: {settings.is_mock}")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="AI Clone MVP",
    description="AI 人物风格档案 / AI 记忆对话库",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-clone-backend"}
