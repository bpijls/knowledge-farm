# Recursive Concept Graph Generator

Seed an LLM with concepts, recursively expand each into related ideas (up to N iterations), and explore the result as an interactive force-directed graph. Nodes are colored and sized by depth; cross-branch deduplication produces a true graph rather than a tree.

## Architecture

```
frontend (Vite+React, :5173) ──SSE──▶ backend (FastAPI, :8000)
                                              │
                                       LLM proxy (OpenAI-compatible)
```

Each iteration fans out concurrent LLM calls (semaphore-bounded), deduplicates concepts by normalized key (trimmed / lowercased), and streams deltas to the frontend so the graph grows layer by layer in real time.

## Setup

### Backend

```bash
cd backend
cp .env.example .env          # edit if your LLM endpoint differs
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

## Environment variables (backend)

| Variable        | Default                  | Description                        |
|-----------------|--------------------------|------------------------------------|
| LLM_BASE_URL    | http://localhost:4000    | OpenAI-compatible LLM proxy base URL |
| LLM_MODEL       | (set in .env)            | Model ID passed to the proxy       |
| LLM_API_KEY     | (set in .env)            | Bearer token for the proxy       |
| MAX_CONCURRENCY | 8                        | Max parallel LLM calls per iteration |

## API

- `POST /api/generate` — `{ seeds, iterations, max_concepts? }` → `{ nodes, edges }`
- `GET  /api/generate/stream?seeds=a,b&iterations=2` — SSE stream of iteration deltas
- `GET  /health`
