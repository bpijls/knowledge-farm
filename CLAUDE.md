# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Grow a concept graph from one word, then grow an illustrated report from that graph. Seeds are
expanded by an LLM into related concepts over N iterations and streamed to the browser, so the
graph visibly grows. A background job then writes a report whose sections are the seed's
strongest branches, with images drawn by vonk's `image-fast` model.

```
frontend (Vite+React, :3000) ──SSE /api/graphs/stream──▶ api (FastAPI, :8000) ──▶ vonk (chat)
          │                                                    │ saves the graph
          └── POST /api/graphs/{id}/reports ──▶ jobs row ──▶ worker: grow_report ──▶ vonk (chat, image-fast)
                    polls /api/reports/{id} ◀── reports row (sections appear one by one) + gen_images volume
```

## Running the stack

`./setup.sh` creates `.env` from `.env.example`, checks the required values and the Caddy
network, then brings the stack up. Or:

```bash
docker compose up -d --build     # first run / after dependency changes
docker compose up -d --build api # rebuild one service
docker compose logs -f api
docker compose restart worker    # after changing job code (report.py, images.py): no hot reload
docker compose logs -f worker    # report job failures land here and on the job's own log
docker compose down
```

`backend/app/` and `frontend/src/` are volume-mounted with hot reload; anything else
(`requirements.txt`, `package.json`, `vite.config.js`, Dockerfiles) needs a rebuild.
Frontend: https://knowledge-farm.paws.home · API: https://api.knowledge-farm.paws.home/api/health

## Tests

Backend (SQLite in memory, vonk faked — no Docker needed):
```bash
cd backend && uv venv .venv && uv pip install -r requirements-dev.txt   # once
cd backend && .venv/bin/python -m pytest
cd backend && .venv/bin/ruff check .
```
`tests/conftest.py` sets `DATABASE_URL`/`VONK_KEY` before importing the app, overrides `get_db`
and `get_session_factory`, and points `settings.image_dir` at a temp dir per test (`image_dir`
fixture). Jobs are run by awaiting `jobs.run_job` directly.

Frontend (Vitest + Testing Library; GraphView is mocked in App.test because it needs a canvas):
```bash
cd frontend && npm install && npm test && npm run lint
```

## Architecture

```
backend/app/
  main.py            App, lifespan (create_all), routers; imports services/report so the job registers
  config.py          Settings from .env: VONK_*, CONCEPTS_PER_NODE, GRAPH_CONCURRENCY, REPORT_*, IMAGE_*
  database.py        Engine, SessionLocal, get_db, get_session_factory (for the streaming response)
  models.py          Graph (seeds, params, nodes, edges as JSON) and Report (sections as JSON)
  schemas.py         Node, Edge, IterationDelta, GraphOut, Section, ReportOut
  routers/
    graphs.py        GET /api/graphs/stream (SSE, saves at the end), list / get / delete
    reports.py       POST /api/graphs/{id}/reports (queues grow_report), GET reports, …/markdown,
                     GET /api/images?spec= and /api/images/{name}
    jobs.py          Template: list / get / cancel / retry jobs
  services/
    ai.py            Shared AsyncVonk client (chat model + image model)
    graph.py         normalize, expand_concept (ai.json, never raises), expand_graph (async generator)
    report.py        outline() from the graph, prompts, text cleaning, the grow_report job
    images.py        gen: tags → PNGs: parse_spec, sha1 cache key, generate(); ported from my-vault
    jobs.py          Template job queue (do not hand-roll another)
  worker.py          Template: `python -m app.worker`

frontend/src/
  App.jsx            State: graph stream, saved graphs, report + its job, highlight logic
  api.js             All fetch/EventSource calls
  graph.js           normalize (mirror of the backend), pathToRoot, edge-key helpers
  markdown.js        markdown-it render; gen: tags → <figure> with /api/images?spec=
  components/
    ConceptForm.jsx  Seeds, generations, max concepts, temperature
    GraphView.jsx    react-force-graph-2d with custom hit-testing (see constraints)
    ReportView.jsx   The growing report, progress bar, image placeholders, hover/pin sections
    SavedGraphs.jsx  Reopen earlier graphs (and their latest report)
  useJobs.js / JobsPanel.jsx   Template job polling and panel (collapsed under "Jobs")
```

## The report pipeline

1. **Outline, no model involved** (`report.outline`): depth-1 neighbours of the seed, ranked by
   degree, top `REPORT_MAX_SECTIONS`. Each gets its depth-2 children (max 8) as material and a
   list of related sections (direct edge or shared child). The graph decides what the report is
   about; the model only writes.
2. Intro → sections in parallel (through `ctx.gate("llm")`) → conclusion. Each part is saved to
   the `reports` row as soon as it exists; the frontend polls it every 1.5 s.
3. Every part except the conclusion carries one `![alt](gen: English prompt | 1280x720)` tag
   (same rules as my-vault's `help/20-gen.md`). `keep_one_image` drops extras and
   `repair_image_tags` restores a forgotten `gen:` prefix.
4. Images are drawn last through `ctx.gate("image", IMAGE_CONCURRENCY)` and cached in the
   `gen_images` volume as `<slug>-<sha1(prompt|size)[:8]>.png` plus a `.json` sidecar. A failed
   image is logged and stays a pulsing placeholder; it never fails the job.
5. Style: `STYLES` in `report.py` (prose, business, poetic, flyer). Each sets the voice (system
   prompt), the length and shape of intro / section / conclusion, the conclusion's heading and
   the visual style appended to every image prompt. The style is stored on the `reports` row
   (`style` column, added by an `ALTER TABLE … IF NOT EXISTS` in `main.py`'s lifespan, since
   `create_all` never alters a table); the frontend styles the report per style
   (`.report-style-*`) and lists a graph's earlier reports in a version picker.
6. Language: the UI sends `English` or `Nederlands`; `model_language` maps the latter to
   "Dutch (Nederlands)". Every prompt ends with "write every sentence in …", and `write_text`
   retries once if the answer `looks_english` anyway (local models drift).

`source_node_ids` on each section drive the provenance highlight: hovering a section highlights
those nodes in the graph; clicking a node scrolls to the section that grew from it.

## Production (feib.nl)

Live at **https://knowledge-farm.feib.nl**: host `feib.nl` (ssh, user bpijls), checkout in
`~/knowledge-farm`, pulled from GitHub. It runs `docker-compose.prod.yml`: frontend built by
`frontend/Dockerfile.prod` and served by nginx (`nginx/default.conf`, which proxies `/api/` to
`knowledge-farm-api:8000` with buffering off for the SSE stream), api and worker without hot
reload or source mounts.

```bash
ssh feib.nl 'cd ~/knowledge-farm && git pull --ff-only && docker compose -f docker-compose.prod.yml up -d --build'
```

The server's `.env` is not in git. It differs from development in `APP_DOMAIN`
(knowledge-farm.feib.nl), `DB_PASSWORD`, `VONK_BASE_URL` (vonk's Tailscale address,
`http://100.67.143.38:4000/v1`: containers there cannot resolve `vonk`) and
`MAX_CONCURRENT_JOBS=1` / `GRAPH_CONCURRENCY=4` (2 CPUs, 3 GB, shared with other sites).
It also uses `VONK_IMAGE_MODEL=image`: the vonk key on feib.nl may only use `text`, `code`,
`embedding` and `image`, so `image-fast` returns 403 there. A report takes ~4.5 min instead of ~1.5.
A changed `.env` needs `up -d --force-recreate`. A rollout restarts the worker, which fails a
running report job; it can be grown again.

**There is no login.** Anyone who finds the URL can grow graphs and reports on vonk.

## Key constraints

- **The normalised key is the contract between front and back.** Node ids are
  `normalize(label)`; `frontend/src/graph.js::normalize` must match `services/graph.py::normalize`.
- **GraphView hit-testing is custom on purpose.** Built-in pointer interaction is disabled
  (`enablePointerInteraction={false}`, `enableNodeDrag={false}`) and drag/click/hover are done in
  graph coordinates, because Brave's canvas farbling breaks force-graph's shadow-canvas lookup.
  Don't re-enable the built-in handlers.
- GraphView passes its container size to ForceGraph2D (ResizeObserver); without it the canvas
  takes the window size and the graph sits off-centre when the report panel is open.
- The graph stream runs in the API, not as a job: watching it grow is the point. Reports are
  jobs because they take 1–2 minutes and must survive a closed tab.
- A report row can stay `growing` if the worker is killed mid-job; the job row (marked failed on
  worker restart) is the truth, and the frontend reads busy-ness from the job.
- `*.paws.home` is not reachable from containers. Browser tests through the shared Playwright
  service need `chromium.connect(ws, expose_network="*.paws.home")`.
