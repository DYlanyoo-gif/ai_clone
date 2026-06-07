from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # LLM Provider
    llm_provider: str = "mock"  # mock | deepseek | openai
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""

    # Model selection: analysis model (portrait + style card) and chat model
    llm_model_name: str = ""  # legacy compatibility; analysis/chat model fields are preferred
    analysis_model: str = "deepseek-chat"
    chat_model: str = "deepseek-chat"

    # LLM call parameters
    llm_timeout_seconds: int = 120
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # Embedding (for future vector search upgrade)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model_name: str = "text-embedding-3-small"

    # Optional vector retrieval (Qdrant local + FastEmbed)
    vector_enabled: bool = False
    vector_provider: str = "qdrant"
    vector_embedding_provider: str = "fastembed"
    vector_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    vector_collection_prefix: str = "ai_clone_profile"
    vector_qdrant_path: str = "../data/qdrant"
    vector_top_k: int = 8

    # mem0 optional memory configuration (kept optional, not product mainline)
    mem0_enabled: bool = False
    mem0_provider: str = "local"
    mem0_collection_prefix: str = "ai_clone_profile"

    # MinerU document parsing
    mineru_enabled: bool = True
    mineru_timeout_seconds: int = 300
    mineru_output_dir: str = "../data/mineru_output"
    mineru_backend: str = "pipeline"       # pipeline | hybrid-auto-engine
    mineru_method: str = "auto"            # auto | ocr | txt
    mineru_lang: str = "ch"               # ch | en
    mineru_start_page: int | None = None
    mineru_end_page: int | None = None
    mineru_formula: bool = True
    mineru_table: bool = True
    mineru_image_analysis: bool = False    # off by default — avoid slow analysis for normal docs

    # App
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    data_dir: str = "../data"

    @property
    def is_mock(self) -> bool:
        """Mock mode: when provider is explicitly 'mock' OR no API key is set."""
        return self.llm_provider == "mock" or not self.llm_api_key

    @property
    def provider_name(self) -> str:
        if self.is_mock:
            return "mock"
        return self.llm_provider

    @property
    def db_path(self) -> str:
        return str(Path(self.data_dir).resolve() / "ai_clone.db")

    @property
    def upload_dir(self) -> str:
        p = Path(self.data_dir).resolve() / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
