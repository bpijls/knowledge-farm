# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Recursive concept-graph generator. Seed concepts are expanded by an LLM into related ideas over N iterations; the result is explored as an interactive force-directed graph. Cross-branch deduplication makes the output a graph, not a tree.

```
frontend (Vite+React, :5173) ──SSE──▶ backend (FastAPI, :8000) ──▶ LLM proxy (vonk, :4000, OpenAI-compatible)
```

## Commands

Backend (`backend/`):
```bash
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend (`frontend/`):
```bash
npm install
npm run dev      # :5173
npm run build    # tsc -b && vite build
npm run lint     # eslint
```

Full stack via Docker: `docker-compose up` (needs `.env` with `APP_DOMAIN` + `CADDY_NETWORK`; frontend served behind Caddy).

## Architecture notes

- **Streaming is the primary path.** The frontend uses `GET /api/generate/stream` (SSE) exclusively — `streamGraph` in `frontend/src/api.ts`, consumed in `App.tsx`. The graph accumulates client-side as iteration deltas arrive, so it grows layer by layer. `POST /api/generate` exists (buffers all deltas into one response) but is not used by the UI.

- **Graph expansion** (`backend/graph.py::expand_graph`) is an async generator yielding one `IterationDelta` per iteration. Each iteration fans out concurrent `expand_concept` calls over the current frontier, bounded by a semaphore (`MAX_CONCURRENCY`). Nodes are deduped by `normalize()` (trimmed/lowercased, collapsed whitespace) — this normalized string is the node `id`. Edges are stored as `frozenset` pairs (undirected, deduped). `depth` = iteration at which a node was first discovered.

- **The normalized key is the contract between front and back.** `App.tsx` recomputes seed ids with the same `trim().toLowerCase().replace(/\s+/g, " ")` logic so it can match streamed node ids back to the original seeds. Keep these two normalizations in sync.

- **LLM calls** (`backend/llm.py`): single shared `httpx.AsyncClient`, OpenAI-compatible `/v1/chat/completions`. The model is told to return raw JSON `{"concepts": [...]}`; `_strip_fences` defensively removes code fences and `<think>...</think>` blocks before `json.loads`. `expand_concept` retries once on any failure and returns `[]` rather than raising, so one bad call never aborts an iteration.

- **GraphView hit-testing is custom and deliberate.** `frontend/src/components/GraphView.tsx` disables react-force-graph's built-in pointer interaction (`enablePointerInteraction={false}`, `enableNodeDrag={false}`) and does its own drag/click/hover hit-testing in graph coordinates via `screen2GraphCoords`. This is a workaround for Brave's canvas "farbling" corrupting the library's offscreen shadow-canvas lookup — see the long comment in the pointer `useEffect`. Don't re-enable the built-in interaction handlers.

- **Selecting a node** runs a BFS to the nearest seed (`pathToRoot` in `App.tsx`); the path is highlighted and non-path nodes are dimmed.

## Config

Backend env (`backend/.env`, see `.env.example`): `LLM_BASE_URL`, `LLM_MODEL` (default `google/gemma-4-26B-A4B-it`), `LLM_API_KEY`, `MAX_CONCURRENCY`. Defaults point at the local `vonk` LLM proxy. (Note: the README's env table lists a stale `LLM_MODEL` default — trust `llm.py` / `.env.example`.)

Vite dev proxy (`vite.config.ts`) forwards `/api` and `/health` to `http://backend:8000` — the Docker service name. Running the frontend dev server outside Docker requires either resolving `backend` to localhost or setting `VITE_API_BASE`.

## Ignore

`test-env/` is a throwaway Python venv (Playwright/PIL for browser testing) — not application code.
