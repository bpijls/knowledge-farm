"""Background jobs on the project's own database: no Redis, no second source of truth.

A job is a row in `jobs` (queued → running → done | failed | cancelled) carrying its own
progress counter and log. Work is a decorated coroutine:

    @job("generate_things")
    async def generate_things(ctx: JobContext, topic: str) -> dict:
        await ctx.set_total(3)
        async with ctx.gate("llm"):          # caps vonk calls in flight, notices a cancel
            text = await ai.chat(topic)
        async with ctx.db() as db:           # short, serialised write
            db.add(Thing(body=text)); await db.commit()
        await ctx.step("wrote one")
        return {"created": 1}

Start one from a request with `await enqueue(db, "generate_things", {"topic": "x"})`.
`worker_loop()` claims and runs them, in the `worker` container by default or inside the API
when JOBS_INLINE=true. Exactly one process may run the loop: recovery after a restart assumes it.
"""
import asyncio
import logging
import uuid
import weakref
from collections.abc import Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.database import Base, SessionLocal

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class Job(Base):
    """One background job. The row is both the queue entry and the progress report."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    # Free-form reference to whatever the job belongs to (a wiki id, a roadmap id, …).
    subject: Mapped[str | None] = mapped_column(String(128), index=True, default=None)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), index=True, default="queued")
    progress: Mapped[str] = mapped_column(String(255), default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    log_text: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


ACTIVE = ("queued", "running")
INTERRUPTED = "Interrupted by a worker restart. Start it again."

_registry: dict[str, Callable[..., Awaitable[dict | None]]] = {}
# Values that must never be stored (an access token, say). Inline mode only: see enqueue().
_ephemeral: dict[str, dict] = {}
# Locks and semaphores bind to an event loop, so keep one set per loop (tests use several).
_per_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict]" = weakref.WeakKeyDictionary()


class Cancelled(Exception):
    """Raised inside a job once its row is no longer `running`."""


def job(kind: str):
    """Register a coroutine as the worker for jobs of this kind."""

    def register(fn):
        _registry[kind] = fn
        return fn

    return register


def _loop_state() -> dict:
    return _per_loop.setdefault(asyncio.get_running_loop(), {})


def _lock() -> asyncio.Lock:
    """Progress writes come from many coroutines at once; one at a time keeps them ordered."""
    return _loop_state().setdefault("lock", asyncio.Lock())


def _semaphore(name: str, size: int) -> asyncio.Semaphore:
    state = _loop_state()
    if name not in state:
        state[name] = asyncio.Semaphore(max(1, size))
    return state[name]


async def _update(factory, job_id: str, *where, **values) -> int:
    async with _lock(), factory() as db:
        result = await db.execute(update(Job).where(Job.id == job_id, *where).values(**values))
        await db.commit()
        return result.rowcount


def _appended(line: str):
    return func.coalesce(Job.log_text, "") + line + "\n"


class JobContext:
    """What a job function gets: progress reporting, cancellation, and database access."""

    def __init__(self, job_id: str, factory, secrets: dict | None = None):
        self.job_id = job_id
        self.factory = factory
        self.secrets = secrets or {}

    async def log(self, line: str, **values) -> None:
        await _update(self.factory, self.job_id, log_text=_appended(line), **values)

    async def step(self, line: str) -> None:
        """One unit of work finished: bump the counter and log it."""
        await self.log(line, done=Job.done + 1)

    async def set_total(self, total: int) -> None:
        await _update(self.factory, self.job_id, total=total)

    async def progress(self, label: str) -> None:
        """Short description of the current phase, shown next to the progress bar."""
        await self.log(label, progress=label)

    async def check_cancelled(self) -> None:
        async with _lock(), self.factory() as db:
            status = await db.scalar(select(Job.status).where(Job.id == self.job_id))
        if status != "running":   # cancelled, or deleted from under us
            raise Cancelled

    @asynccontextmanager
    async def gate(self, name: str = "llm", size: int | None = None):
        """Limit how many coroutines are inside this block at once, across all running jobs.

        Checks for cancellation on entry, so a cancelled job stops before its next model call.
        """
        async with _semaphore(name, size or settings.generation_concurrency):
            await self.check_cancelled()
            yield

    @asynccontextmanager
    async def db(self):
        """A short-lived session for one write. Never hold it across a model call, and do not
        call log()/step() inside the block: they take the same lock."""
        async with _lock(), self.factory() as session:
            yield session


async def run_all(coros: Iterable[Awaitable]) -> None:
    """gather() that cancels the siblings when one fails, and re-raises that one failure."""
    try:
        async with asyncio.TaskGroup() as group:
            for coro in coros:
                group.create_task(coro)
    except BaseExceptionGroup as eg:
        raise eg.exceptions[0] from None


async def enqueue(
    db: AsyncSession, kind: str, params: dict | None = None, *,
    subject: str | None = None, ephemeral: dict | None = None,
) -> Job:
    """Queue a job. `params` must be JSON-serialisable: it is stored and passed as keyword args.

    `ephemeral` values reach the job as `ctx.secrets` without ever being stored. They live in
    this process only, so they need JOBS_INLINE=true and are lost if the API restarts first.
    """
    if kind not in _registry:
        raise ValueError(f"No job registered for kind {kind!r}")
    if ephemeral and not settings.jobs_inline:
        raise ValueError("ephemeral values need JOBS_INLINE=true: a separate worker cannot see them")
    row = Job(kind=kind, params=params or {}, subject=subject)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    if ephemeral:
        _ephemeral[row.id] = ephemeral
    return row


async def claim(factory) -> str | None:
    """Take the oldest queued job, mark it running, and return its id."""
    async with _lock(), factory() as db:
        row = await db.scalar(
            select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.status, row.started_at = "running", _now()
        await db.commit()
        return row.id


async def run_job(job_id: str, factory) -> None:
    """Run one job to a final state. Never raises, except to pass on a task cancellation."""
    async with _lock(), factory() as db:
        row = await db.get(Job, job_id)
        if row is None or row.status not in ACTIVE:
            return   # cancelled or deleted while it waited
        kind, params = row.kind, dict(row.params or {})
    await _update(factory, job_id, Job.status == "queued", status="running", started_at=_now())

    ctx = JobContext(job_id, factory, _ephemeral.get(job_id))
    try:
        fn = _registry.get(kind)
        if fn is None:
            raise RuntimeError(f"No job registered for kind {kind!r}")
        result = await fn(ctx, **params)
        finished = await _update(
            factory, job_id, Job.status == "running",
            status="done", progress="", result=result, finished_at=_now(), log_text=_appended("Done."),
        )
        if not finished:
            raise Cancelled
    except Cancelled:
        # Only if the row is still there and cancelled; a deleted job has nothing to update.
        await _update(factory, job_id, Job.status == "cancelled",
                      progress="", finished_at=_now(), log_text=_appended("Cancelled."))
    except asyncio.CancelledError:
        # The worker is shutting down. Say so now rather than leaving it to the next start.
        await asyncio.shield(_fail(factory, job_id, INTERRUPTED))
        raise
    except Exception as e:  # the job's last line of defence; surface it on the row
        log.exception("job %s (%s) failed", job_id, kind)
        await _fail(factory, job_id, f"{type(e).__name__}: {e}"[:1000])
    finally:
        _ephemeral.pop(job_id, None)


async def _fail(factory, job_id: str, message: str) -> None:
    await _update(factory, job_id, Job.status == "running", status="failed", progress="",
                  error=message, finished_at=_now(), log_text=_appended(f"Job failed: {message}"))


async def recover_orphans(factory) -> int:
    """Call once when the worker starts: whatever is still `running` died with the last process.

    Queued jobs are left alone and simply get picked up.
    """
    async with _lock(), factory() as db:
        result = await db.execute(
            update(Job).where(Job.status == "running").values(
                status="failed", progress="", error=INTERRUPTED, finished_at=_now(),
                log_text=_appended(f"Job failed: {INTERRUPTED}"))
        )
        await db.commit()
        return result.rowcount


async def worker_loop(factory, stop: asyncio.Event, poll_seconds: float = 1.0) -> None:
    """Claim and run queued jobs, at most MAX_CONCURRENT_JOBS at a time, until `stop` is set."""
    running: set[asyncio.Task] = set()   # strong references: asyncio itself keeps only weak ones
    while not stop.is_set():
        try:
            while len(running) < settings.max_concurrent_jobs:
                job_id = await claim(factory)
                if job_id is None:
                    break
                task = asyncio.create_task(run_job(job_id, factory))
                running.add(task)
                task.add_done_callback(running.discard)
        except Exception:  # a database blip must not end the loop
            log.exception("could not claim a job; retrying")
        try:
            await asyncio.wait_for(stop.wait(), poll_seconds)
        except TimeoutError:
            pass
    for task in list(running):
        task.cancel()
    await asyncio.gather(*running, return_exceptions=True)


async def start_inline_worker(factory=SessionLocal) -> tuple[asyncio.Event, asyncio.Task] | None:
    """For the API's lifespan: run the worker loop in this process when JOBS_INLINE=true."""
    if not settings.jobs_inline:
        return None
    await recover_orphans(factory)
    stop = asyncio.Event()
    return stop, asyncio.create_task(worker_loop(factory, stop))


async def stop_inline_worker(handle: tuple[asyncio.Event, asyncio.Task] | None) -> None:
    if handle:
        stop, task = handle
        stop.set()
        await task
