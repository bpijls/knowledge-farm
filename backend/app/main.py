from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import models  # noqa: F401 - registers the tables
from app.config import settings
from app.database import Base, engine
from app.routers import access as access_router
from app.routers import graphs, reports
from app.routers import jobs as jobs_router
from app.services import access, jobs
from app.services import report as report_job  # noqa: F401 - registers the grow_report job


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fine for a prototype; swap for Alembic once the schema starts moving.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all never alters an existing table: columns added later are added here.
        if conn.dialect.name == "postgresql":
            await conn.execute(text(
                "ALTER TABLE reports ADD COLUMN IF NOT EXISTS style VARCHAR(32) "
                "NOT NULL DEFAULT 'prose'"))
    # Normally the `worker` container runs the jobs; with JOBS_INLINE=true this process does.
    inline_worker = await jobs.start_inline_worker()
    yield
    await jobs.stop_inline_worker(inline_worker)


app = FastAPI(title="knowledge-farm", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_access_key(request: Request, call_next):
    """Every /api route except the login ones needs the access key (see services/access.py)."""
    path = request.url.path
    if (path.startswith("/api/") and path not in access.OPEN_PATHS
            and request.method != "OPTIONS" and not access.authorised(request)):
        return JSONResponse({"detail": "Access key required"}, status_code=401)
    return await call_next(request)


app.include_router(access_router.router)
app.include_router(graphs.router)
app.include_router(reports.router)
app.include_router(jobs_router.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
