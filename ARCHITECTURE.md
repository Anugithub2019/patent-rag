# Patent RAG System — Architecture

> **Living document** — This file is automatically updated whenever the project structure changes. Last updated: 2026-04-08.

## Overview

This project is a Retrieval-Augmented Generation (RAG) system that helps determine whether a new invention is already covered by existing patents. It uses the **Hashtag AI knowledge graph API** to search patent databases using natural language invention descriptions, identify similar patents and prior art, compare invention features with patent claims, and generate explainable novelty assessments.

## Directory Structure

```
patent-rag/
├── api/                          # Vercel serverless functions
│   ├── health.js                 # Health check endpoint
│   └── search.js                 # Synchronous search proxy to Hashtag /query API
│
├── backend/                      # Query processing (frontend search pipeline)
│   ├── __init__.py               # Package marker
│   ├── celery_app.py             # Celery app config (Redis broker/backend)
│   ├── config.py                 # Shared config (API key, base URL, Redis/Celery)
│   ├── hashtag_client.py         # Hashtag /query API client
│   ├── query_builder.py          # Wraps raw user input into a well-formed question
│   ├── similarity.py             # Parses/transforms Hashtag API response
│   └── tasks.py                  # Celery async query task
│
├── kg_builder/                   # Knowledge graph building (file upload pipeline)
│   ├── __init__.py               # Package marker
│   ├── db.py                     # SQLite tracking for upload dedup/status
│   ├── uploader.py               # Uploads patent files to Hashtag /process API
│   └── uploader_config.json      # Uploader config (input dir, corpus name)
│
├── frontend/                     # Static HTML frontend
│   ├── report.html               # Report page
│   └── search.html               # Main search page
│
├── servers/                      # Local development servers
│   ├── flask_server.py           # Flask server (Redis + Celery async queries)
│   └── node_server.mjs           # Node.js server (in-memory job store)
│
├── scripts/                      # Utility scripts
│   ├── extract_answers.py        # Extract answers from test results → xlsx
│   ├── query.sh                  # Quick Hashtag API query tester
│   ├── run_tests.sh              # Test multiple projects against questions
│   └── xml_split.py              # Split USPTO XML into per-patent JSON files
│
├── .gitignore
├── ARCHITECTURE.md               # This file
├── package.json                  # npm scripts (build, start, celery, redis)
├── README.md
└── vercel.json                   # Vercel deployment config
```

## Component Breakdown

### `backend/` — Query Processing

Handles the **frontend search pipeline**: takes user query text, sends it to the Hashtag `/query` API, and parses the response for display.

| File | Purpose |
|---|---|
| `config.py` | Loads `HASHTAG_API_KEY` from env, defines `BASE_URL` (`https://kg-api.hashtag.ai/test_two_patents`), Redis URL, Celery broker/backend URLs, cache TTL. |
| `query_builder.py` | Wraps raw user input into a well-formed question. If input already starts with a question word (e.g., "what", "find", "is there"), it's used as-is. Otherwise it's wrapped as: `"Is there any novelty in this technology? Technology draft: {text}"`. |
| `hashtag_client.py` | Thin wrapper around the Hashtag `/query` endpoint. Handles auth headers (`x-api-key`), request formatting, and error handling. |
| `similarity.py` | Parses the raw Hashtag API response into a structured, frontend-friendly format. Extracts chunk details, sources, answer, and contexts. Sorts results by similarity score descending. |
| `tasks.py` | Celery background task for async query processing. Computes a cache key from query text for deduplication, calls `query_hashtag()`, parses via `process_query_response()`, stores result in Redis. |
| `celery_app.py` | Celery app instance using Redis as both message broker and result backend. |

### `kg_builder/` — Knowledge Graph Building

Handles the **file upload pipeline**: reads patent text files, uploads them to the Hashtag `/process` API to build the knowledge graph, and tracks upload status in SQLite.

| File | Purpose |
|---|---|
| `uploader.py` | Main uploader script. Reads `.txt` files from the input directory, computes SHA-256 hash for dedup, uploads each file to the Hashtag `/process` endpoint, and records results in SQLite. Supports `--list`, `--failed`, `--stats` CLI flags. |
| `db.py` | SQLite database for tracking upload attempts. Tables: `upload_records` (file_name, file_path, file_hash, file_size, corpus, status, uploaded_at, error_message). Database file lives at project root: `upload_records.db`. |
| `uploader_config.json` | Configuration for the uploader: `input_dir` (e.g., `patents_5`) and `corpus_name` (e.g., `patents_json_5`). |

### `api/` — Vercel Serverless Functions

| File | Purpose |
|---|---|
| `search.js` | POST endpoint that proxies search queries to the Hashtag `/query` API. Includes query building, response parsing, and 120s timeout handling. |
| `health.js` | GET endpoint returning `{ status: 'ok' }`. |

### `servers/` — Local Development Servers

| File | Purpose |
|---|---|
| `flask_server.py` | Flask server with Redis + Celery async query processing. Endpoints: `GET /` (serve frontend), `GET /report.html`, `POST /api/query` (returns job_id), `GET /api/result/<job_id>` (poll result), `POST /api/search` (legacy sync), `GET /api/health`. |
| `node_server.mjs` | Node.js HTTP server with in-memory job store. Endpoints: `GET /`, `GET /report.html`, `GET /api/health`, `POST /api/search` (sync), `POST /api/query` (async), `GET /api/result/<job_id>`. |

### `frontend/` — Static HTML

| File | Purpose |
|---|---|
| `search.html` | Main search page for submitting patent novelty queries. |
| `report.html` | Report page for displaying search results. |

### `scripts/` — Utility Scripts

| File | Purpose |
|---|---|
| `run_tests.sh` | Tests multiple Hashtag AI projects against the same set of questions. Saves results to `tests/<project>/q<N>.json`. |
| `query.sh` | Quick shell script to test a single query against the Hashtag API. |
| `xml_split.py` | Splits a USPTO bulk XML file into individual per-patent JSON files. |
| `extract_answers.py` | Extracts the `answer` field from test result JSON files and compiles them into an Excel spreadsheet. |

## Data Flow

### Query Flow (Frontend Search)

```
User Input (text)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend (search.html)                                     │
│  POST /api/query  →  { "text": "..." }                      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Server (flask_server.py or node_server.mjs)                │
│  1. Generate job_id, store "pending" in Redis/in-memory     │
│  2. Enqueue Celery task (Flask) or fire async fetch (Node)  │
│  3. Return 202 { job_id }                                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  backend/tasks.py (Celery) or node_server.mjs               │
│  1. Check Redis cache for identical query                   │
│  2. Call backend.hashtag_client.query_hashtag(text)         │
│  3. Parse response via backend.similarity.process_query_response() │
│  4. Store result in Redis under job:<job_id>                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Hashtag AI API                                             │
│  POST {BASE_URL}/query                                      │
│  Headers: x-api-key, Content-Type: application/json         │
│  Body: { "question": "<built query>" }                      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Frontend polls GET /api/result/<job_id> until status = "complete"
```

### Knowledge Graph Build Flow (File Upload)

```
Patent Text Files (.txt)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  kg_builder/uploader.py                                     │
│  1. Read file, compute SHA-256 hash                         │
│  2. Check kg_builder/db.py is_uploaded(hash) for dedup      │
│  3. POST to Hashtag /process API                            │
│  4. Record result in SQLite (upload_records table)          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Hashtag AI API                                             │
│  POST {BASE_URL}/process                                    │
│  Headers: x-api-key, Content-Type: application/json         │
│  Body: { "type": "text", "url": "<file content>" }          │
└─────────────────────────────────────────────────────────────┘
```

## External Dependencies

| Service | Purpose | Config |
|---|---|---|
| **Hashtag AI API** | Knowledge graph storage, query, and processing | `HASHTAG_API_KEY` env var; `BASE_URL = https://kg-api.hashtag.ai/test_two_patents` |
| **Redis** | Celery broker/result backend, job status storage, query cache | `REDIS_URL` env var (default: `redis://localhost:6379/0`) |
| **Celery** | Async task queue for query processing | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| **SQLite** | Upload dedup/status tracking | `upload_records.db` at project root |

## Key Configuration

| Setting | Value | Location |
|---|---|---|
| Hashtag API base URL | `https://kg-api.hashtag.ai/test_two_patents` | `backend/config.py` |
| API key | `HASHTAG_API_KEY` env var | `.env` file |
| Redis URL | `redis://localhost:6379/0` (default) | `backend/config.py` |
| Cache TTL | 3600 seconds (1 hour) | `backend/config.py` |
| Uploader input dir | `patents_5` | `kg_builder/uploader_config.json` |
| Uploader corpus name | `patents_json_5` | `kg_builder/uploader_config.json` |
| Flask server port | 3000 (default) | `servers/flask_server.py` |
| Node server port | 3000 (default) | `servers/node_server.mjs` |

## npm Scripts

| Script | Command | Purpose |
|---|---|---|
| `build` | `mkdir -p public && cp frontend/*.html public/` | Build static frontend for Vercel |
| `start` | `python servers/flask_server.py` | Start Flask server |
| `start:node` | `node servers/node_server.mjs` | Start Node.js server |
| `celery:worker` | `celery -A backend.celery_app worker --loglevel=info` | Start Celery worker |
| `redis:start` | `brew services start redis` | Start Redis |

## Change Log

| Date | Change |
|---|---|
| 2026-04-08 | Moved knowledge graph building files from `backend/` to new `kg_builder/` folder. `backend/` now contains only query processing files. |