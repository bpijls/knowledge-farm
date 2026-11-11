"""The job queue: lifecycle, cancellation, claiming, recovery, endpoints.

Jobs are run by awaiting `run_job` directly, so nothing here needs a worker process.
"""
import asyncio

import pytest

from app.config import settings
from app.services import jobs
from app.services.jobs import Job


async def _queue(factory, kind, params=None, **kwargs) -> str:
    async with factory() as db:
        return (await jobs.enqueue(db, kind, params, **kwargs)).id


async def _get(factory, job_id) -> Job:
    # Under the queue's own lock: the test database is one shared connection, so a read that
    # overlaps a job's write would share its transaction.
    async with jobs._lock(), factory() as db:
        return await db.get(Job, job_id)


@pytest.fixture
def kinds():
    """Register throwaway job kinds for one test."""
    before = dict(jobs._registry)
    yield jobs.job
    jobs._registry.clear()
    jobs._registry.update(before)


# --- lifecycle --------------------------------------------------------------

async def test_job_runs_to_done_with_progress_and_log(factory, kinds):
    @kinds("count")
    async def count(ctx, upto):
        await ctx.set_total(upto)
        await ctx.progress("Counting")
        for i in range(upto):
            await ctx.step(f"  {i + 1}")
        return {"counted": upto}

    job_id = await _queue(factory, "count", {"upto": 3})
    await jobs.run_job(job_id, factory)

    row = await _get(factory, job_id)
    assert (row.status, row.done, row.total) == ("done", 3, 3)
    assert row.result == {"counted": 3}
    assert row.progress == ""
    assert row.log_text.splitlines() == ["Counting", "  1", "  2", "  3", "Done."]
    assert row.started_at and row.finished_at


async def test_exception_marks_job_failed(factory, kinds):
    @kinds("boom")
    async def boom(ctx):
        raise RuntimeError("vonk is down")

    job_id = await _queue(factory, "boom")
    await jobs.run_job(job_id, factory)   # must not raise

    row = await _get(factory, job_id)
    assert row.status == "failed"
    assert row.error == "RuntimeError: vonk is down"
    assert "Job failed: RuntimeError: vonk is down" in row.log_text


async def test_unknown_kind_cannot_be_queued(factory):
    async with factory() as db:
        with pytest.raises(ValueError, match="No job registered"):
            await jobs.enqueue(db, "nope")


async def test_cancel_stops_the_job_at_its_next_gate(factory, kinds, client):
    reached = []

    @kinds("slow")
    async def slow(ctx):
        for i in range(5):
            async with ctx.gate("llm"):
                reached.append(i)
            if i == 1:   # the user cancels while the job is mid-run
                assert (await client.post(f"/api/jobs/{ctx.job_id}/cancel")).status_code == 200
            await ctx.step(f"  {i}")

    job_id = await _queue(factory, "slow")
    await jobs.run_job(job_id, factory)

    row = await _get(factory, job_id)
    assert row.status == "cancelled"
    assert reached == [0, 1]              # the third gate refused entry
    assert row.log_text.endswith("Cancelled.\n")
    assert row.finished_at


async def test_cancelled_while_queued_never_runs(factory, kinds, client):
    ran = []

    @kinds("never")
    async def never(ctx):
        ran.append(True)

    job_id = await _queue(factory, "never")
    assert (await client.post(f"/api/jobs/{job_id}/cancel")).json()["status"] == "cancelled"
    assert await jobs.claim(factory) is None
    await jobs.run_job(job_id, factory)
    assert ran == []


async def test_gate_limits_concurrency(factory, kinds):
    inside = peak = 0

    @kinds("fanout")
    async def fanout(ctx):
        async def one():
            nonlocal inside, peak
            async with ctx.gate("narrow", size=2):
                inside += 1
                peak = max(peak, inside)
                await asyncio.sleep(0.01)
                inside -= 1
        await jobs.run_all(one() for _ in range(8))

    job_id = await _queue(factory, "fanout")
    await jobs.run_job(job_id, factory)
    assert (await _get(factory, job_id)).status == "done"
    assert peak == 2


# --- claiming and recovery --------------------------------------------------

async def test_claim_takes_oldest_first_and_never_twice(factory, kinds):
    @kinds("noop")
    async def noop(ctx):
        pass

    first = await _queue(factory, "noop")
    second = await _queue(factory, "noop")

    assert await jobs.claim(factory) == first
    assert await jobs.claim(factory) == second
    assert await jobs.claim(factory) is None
    assert (await _get(factory, first)).status == "running"


async def test_recovery_fails_running_jobs_and_keeps_queued_ones(factory, kinds):
    @kinds("noop")
    async def noop(ctx):
        pass

    interrupted = await _queue(factory, "noop")
    waiting = await _queue(factory, "noop")
    assert await jobs.claim(factory) == interrupted   # the old worker had started this one

    assert await jobs.recover_orphans(factory) == 1

    assert (await _get(factory, interrupted)).status == "failed"
    assert (await _get(factory, interrupted)).error == jobs.INTERRUPTED
    assert (await _get(factory, waiting)).status == "queued"


async def test_worker_loop_runs_queued_jobs_until_stopped(factory, kinds, monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_jobs", 1)
    order = []

    @kinds("ordered")
    async def ordered(ctx, n):
        order.append(n)

    ids = [await _queue(factory, "ordered", {"n": n}) for n in range(3)]
    stop = asyncio.Event()
    loop = asyncio.create_task(jobs.worker_loop(factory, stop, poll_seconds=0.01))
    for _ in range(200):
        if all([(await _get(factory, i)).status == "done" for i in ids]):
            break
        await asyncio.sleep(0.01)
    stop.set()
    await loop

    assert order == [0, 1, 2]


async def test_stopping_the_worker_fails_the_job_it_was_running(factory, kinds):
    started = asyncio.Event()

    @kinds("endless")
    async def endless(ctx):
        started.set()
        await asyncio.sleep(60)

    job_id = await _queue(factory, "endless")
    stop = asyncio.Event()
    loop = asyncio.create_task(jobs.worker_loop(factory, stop, poll_seconds=0.01))
    await asyncio.wait_for(started.wait(), 2)
    stop.set()
    await loop

    row = await _get(factory, job_id)
    assert (row.status, row.error) == ("failed", jobs.INTERRUPTED)


# --- ephemeral values -------------------------------------------------------

async def test_ephemeral_values_need_inline_mode(factory, kinds, monkeypatch):
    seen = {}

    @kinds("secret")
    async def secret(ctx):
        seen.update(ctx.secrets)

    async with factory() as db:
        with pytest.raises(ValueError, match="JOBS_INLINE"):
            await jobs.enqueue(db, "secret", ephemeral={"token": "t"})

    monkeypatch.setattr(settings, "jobs_inline", True)
    job_id = await _queue(factory, "secret", ephemeral={"token": "t"})
    assert (await _get(factory, job_id)).params == {}     # never stored
    await jobs.run_job(job_id, factory)
    assert seen == {"token": "t"}
    assert job_id not in jobs._ephemeral                  # and dropped afterwards


# --- endpoints --------------------------------------------------------------

async def test_list_get_and_retry(factory, kinds, client):
    @kinds("flaky")
    async def flaky(ctx):
        raise RuntimeError("first try")

    job_id = await _queue(factory, "flaky", subject="thing-1")
    other = await _queue(factory, "flaky", subject="thing-2")

    assert (await client.post(f"/api/jobs/{job_id}/retry")).status_code == 409   # still queued
    await jobs.run_job(job_id, factory)

    listed = (await client.get("/api/jobs", params={"subject": "thing-1"})).json()
    assert [j["id"] for j in listed] == [job_id]
    assert "log_text" not in listed[0]
    assert {j["id"] for j in (await client.get("/api/jobs")).json()} == {job_id, other}

    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    assert detail["status"] == "failed" and "first try" in detail["log_text"]

    retried = await client.post(f"/api/jobs/{job_id}/retry")
    assert retried.status_code == 202
    assert retried.json()["id"] != job_id
    assert (retried.json()["status"], retried.json()["subject"]) == ("queued", "thing-1")

    assert (await client.get("/api/jobs/missing")).status_code == 404
