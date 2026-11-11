"""Growing, saving and reopening concept graphs."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_session_factory
from app.models import Graph
from app.schemas import GraphOut, GraphSummary
from app.services.graph import expand_graph

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


@router.get("/stream")
async def stream_graph(
    seeds: str,
    iterations: int = Query(default=2, ge=1, le=10),
    max_concepts: int = Query(default=500, ge=1, le=2000),
    temperature: float = Query(default=0.7, ge=0.0, le=2.0),
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
        async for delta in expand_graph(seed_list, iterations, max_concepts, temperature):
            nodes += [n.model_dump() for n in delta.nodes]
            edges += [e.model_dump() for e in delta.edges]
            yield f"data: {delta.model_dump_json()}\n\n"
        graph = Graph(seeds=seed_list, nodes=nodes, edges=edges,
                      params={"iterations": iterations, "max_concepts": max_concepts,
                              "temperature": temperature})
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
    graph = await db.get(Graph, graph_id)
    if graph is not None:
        await db.delete(graph)
        await db.commit()
