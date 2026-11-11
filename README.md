# Knowledge Farm

Plant one word and watch a concept graph grow from it, then grow an illustrated report from
that graph.

1. **Plant**: seed concepts are expanded by a local LLM (vonk) into related concepts over a few
   generations. The graph streams in and grows layer by layer. Branches that meet are merged,
   so it is a graph, not a tree.
2. **Grow report**: a background job turns the seed's strongest branches into sections, writes
   them (English or Dutch) and illustrates them with vonk's `image-fast` model. Sections appear
   as they are written; images appear as they are drawn.
3. **Trace**: hover a section to see which concepts it grew from; click a concept to trace it
   back to the seed and jump to its section. Saved graphs and reports can be reopened, and a
   report downloads as Markdown.

## Run

```bash
./setup.sh                      # creates .env on first run; fill in VONK_KEY and DB_PASSWORD
docker compose up -d --build
```

Then open https://knowledge-farm.paws.home. Configuration lives in `.env` (see `.env.example`).

## Develop

```bash
cd backend && uv venv .venv && uv pip install -r requirements-dev.txt && .venv/bin/python -m pytest
cd frontend && npm install && npm test && npm run lint
```

Built on the house project template (FastAPI + Vite/React + Postgres + job worker). See
`CLAUDE.md` for the architecture and the report pipeline.
