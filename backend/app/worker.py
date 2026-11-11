"""The job worker: `python -m app.worker`. Runs queued jobs until it is told to stop.

It does not hot-reload. After changing job code: `docker compose restart worker`.
"""
import asyncio
import logging
import signal

from app import main  # noqa: F401 - importing the app registers every job kind
from app.config import settings
from app.database import SessionLocal
from app.services import jobs

log = logging.getLogger("app.worker")


async def run() -> None:
    if settings.jobs_inline:
        log.info("JOBS_INLINE=true: the API runs the jobs itself, nothing to do here.")
        return
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    orphans = await jobs.recover_orphans(SessionLocal)
    if orphans:
        log.warning("marked %d interrupted job(s) as failed", orphans)
    log.info("worker ready (max %d job(s) at once)", settings.max_concurrent_jobs)
    await jobs.worker_loop(SessionLocal, stop)
    log.info("worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())
