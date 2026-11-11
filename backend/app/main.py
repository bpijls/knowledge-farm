from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401 - registers the tables
from app.config import settings
from app.database import Base, engine
from app.routers import graphs, reports
from app.routers import jobs as jobs_router
from app.services import jobs
from app.services import report as report_job  # noqa: F401 - registers the grow_report job


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fine for a prototype; swap for Alembic once the schema starts moving.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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

app.include_router(graphs.router)
app.include_router(reports.router)
app.include_router(jobs_router.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
