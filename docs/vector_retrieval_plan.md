# Vector Retrieval Plan

Last updated: 2026-06-04

## Current State

The project now supports an optional semantic retrieval layer:

- **Default retrieval**: keyword-based n-gram + Jaccard scoring, zero dependency fallback.
- **Optional retrieval**: Qdrant local on-disk vector store + FastEmbed embeddings.
- **Source of truth**: SQLite `chunks` table remains authoritative.
- **Failure behavior**: if Qdrant/FastEmbed is not installed, disabled, or fails to initialize, the app automatically falls back to keyword retrieval.

Implementation:

- Keyword fallback: `backend/app/services/document_processor.py` → `search_chunks_local()`
- Vector adapter: `backend/app/integrations/vector_adapter.py`
- Status: `GET /api/integrations/vector/status`
- Rebuild: `POST /api/profiles/{id}/vector/rebuild`
- Search test: `GET /api/profiles/{id}/vector/search?query=...`

## Why Vector Retrieval?

Keyword retrieval works reliably, but it cannot fully capture semantic similarity. Vector retrieval improves:

- paraphrased queries,
- emotional or behavioral synonyms,
- evidence hit quality in RAG chat,
- evidence-map chunk selection when資料表述与问题不完全同词。

## Selected Integration

### Qdrant Local On-Disk

- Project: `qdrant/qdrant-client`
- Mode: local path storage, no external Qdrant service required
- Default path: `../data/qdrant`
- Collection naming: `ai_clone_profile_{profile_id}`

### FastEmbed

- Project: `qdrant/fastembed`
- Default model: `BAAI/bge-small-zh-v1.5`
- Runs locally, no DeepSeek/OpenAI embedding API key needed

## Configuration

Add to `.env`:

```env
VECTOR_ENABLED=true
VECTOR_PROVIDER=qdrant
VECTOR_EMBEDDING_PROVIDER=fastembed
VECTOR_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
VECTOR_COLLECTION_PREFIX=ai_clone_profile
VECTOR_QDRANT_PATH=../data/qdrant
VECTOR_TOP_K=8
```

Defaults in `.env.example` keep `VECTOR_ENABLED=false`.

## Installation

Do not install these dependencies unless you want semantic retrieval:

```bash
pip install qdrant-client fastembed
```

Windows project venv:

```bash
backend\venv\Scripts\python.exe -m pip install qdrant-client fastembed
```

Then restart the backend and verify:

```bash
curl http://localhost:8000/api/integrations/vector/status
```

Expected when enabled and available:

```json
{
  "installed": true,
  "enabled": true,
  "available": true,
  "provider": "qdrant",
  "embedding_model": "BAAI/bge-small-zh-v1.5"
}
```

## Indexing Flow

1. Uploaded documents are parsed and chunked into SQLite as before.
2. If vector retrieval is enabled and available, the newly created chunks are upserted into Qdrant.
3. Vector write failures are logged as warnings and do not fail document upload.
4. Existing profiles can be indexed with:

```bash
curl -X POST http://localhost:8000/api/profiles/1/vector/rebuild
```

Each point payload includes:

- profile_id
- document_id
- chunk_id
- filename
- chunk_index
- parser
- char_count
- created_at
- content

## Retrieval Flow

The service uses a vector-first retrieval policy:

1. Try `search_chunks_vector(profile_id, query, top_k)`.
2. If unavailable or empty, fall back to `search_chunks_local()`.
3. Returned chunks include `retrieval_method`:
   - `vector`
   - `keyword`
4. Vector results include `similarity_score`.

Chat prompts tell the LLM when evidence chunks came from semantic retrieval and ask it to prefer high-similarity chunks.

## What This Does Not Affect

- DeepSeek API keys or provider configuration
- MinerU parsing configuration
- mem0 optional memory
- SQLite chunk storage
- Existing uploaded files and profiles

## Manual Acceptance

1. Do not install qdrant/fastembed. Start the project and confirm original features still work.
2. Open `/api/integrations/vector/status`; confirm it reports not installed or disabled without 500.
3. Install `qdrant-client fastembed`.
4. Set `VECTOR_ENABLED=true` and restart backend.
5. Confirm `/api/integrations/vector/status` returns `available=true`.
6. Choose an existing profile and click “重建向量索引”.
7. Run analysis and confirm evidence modal shows `vector` and `similarity_score`.
8. Open chat page and confirm sidebar shows vector retrieval enabled.
9. Ask a資料相关问题 and confirm the answer uses closer evidence.
