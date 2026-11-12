"""Growing, saving and reopening concept graphs."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_session_factory
from app.models import Graph, Report
from app.schemas import GraphOut, GraphSummary
from app.services import images, jobs
from app.services.graph import expand_graph
from app.services.jobs import Job
from app.services.language import Language
from app.services.report import repair_image_tags

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


@router.get("/stream")
async def stream_graph(
    seeds: str,
    iterations: int = Query(default=2, ge=1, le=10),
    max_concepts: int = Query(default=500, ge=1, le=2000),
    temperature: float = Query(default=0.7, ge=0.0, le=2.0),
    language: Language = "English",
    factory=Depends(get_session_factory),
):
    """Server-sent events: one IterationDelta per iteration, then {"done", "graph_id"}.

    The graph grows in the browser as the deltas arrive; this is the demo, so it streams
    rather than running as a background job. Saved once complete.
    """
    seed_list = [s.strip() for s in seeds.split(",") if s.strip()]
    if not seed_list:
        raise HTTPException(422, "Give at least one seed concept.")

    async def events():
        nodes, edges = [], []
        async for delta in expand_graph(seed_list, iterations, max_concepts, temperature, language):
            nodes += [n.model_dump() for n in delta.nodes]
            edges += [e.model_dump() for e in delta.edges]
            yield f"data: {delta.model_dump_json()}\n\n"
        graph = Graph(seeds=seed_list, nodes=nodes, edges=edges,
                      params={"iterations": iterations, "max_concepts": max_concepts,
                              "temperature": temperature, "language": language})
        async with factory() as db:
            db.add(graph)
            await db.commit()
        yield f"data: {json.dumps({'done': True, 'graph_id': graph.id})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("", response_model=list[GraphSummary])
async def list_graphs(limit: int = 30, db: AsyncSession = Depends(get_db)):
    stmt = select(Graph).order_by(Graph.created_at.desc()).limit(max(1, min(limit, 200)))
    return list((await db.scalars(stmt)).all())


@router.get("/{graph_id}", response_model=GraphOut)
async def get_graph(graph_id: str, db: AsyncSession = Depends(get_db)):
    graph = await db.get(Graph, graph_id)
    if graph is None:
        raise HTTPException(404, "Graph not found")
    return graph


@router.delete("/{graph_id}", status_code=204)
async def delete_graph(graph_id: str, db: AsyncSession = Depends(get_db)):
    """The graph, its reports, its report jobs and the images no other report still uses."""
    graph = await db.get(Graph, graph_id)
    if graph is None:
        raise HTTPException(404, "Graph not found")
    # A report still growing is cancelled first; it stops at its next gate.
    for job in (await db.scalars(select(Job).where(Job.subject == f"graph:{graph_id}"))).all():
        if job.status in jobs.ACTIVE:
            job.status, job.progress = "cancelled", ""
    reports = (await db.scalars(select(Report).where(Report.graph_id == graph_id))).all()
    doomed = {s for r in reports for s in _report_specs(r)}
    for r in reports:
        await db.delete(r)
    await db.delete(graph)
    await db.commit()

    kept = {s for r in (await db.scalars(select(Report))).all() for s in _report_specs(r)}
    for spec in doomed - kept:
        try:
            png = images.cached_path(spec)
        except images.ImageError:
            continue
        png.unlink(missing_ok=True)
        png.with_suffix(".json").unlink(missing_ok=True)


def _report_specs(report: Report) -> set[str]:
    return {spec for s in report.sections or [] for spec in images.gen_specs(repair_image_tags(s.get("markdown", "")))}
