import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

load_dotenv()

from graph import expand_graph
from llm import close_client
from models import Edge, GenerateRequest, GenerateResponse, IterationDelta, Node


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(title="Concept Graph Generator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    all_nodes: list[Node] = []
    all_edges: list[Edge] = []

    async for delta in expand_graph(
        req.seeds, req.iterations, req.max_concepts, req.temperature
    ):
        all_nodes.extend(delta.nodes)
        all_edges.extend(delta.edges)

    return GenerateResponse(nodes=all_nodes, edges=all_edges)


@app.get("/api/generate/stream")
async def generate_stream(
    seeds: str,
    iterations: int = 2,
    max_concepts: int = 500,
    temperature: float = Query(default=0.7, ge=0.0, le=2.0),
):
    seed_list = [s.strip() for s in seeds.split(",") if s.strip()]

    async def event_stream():
        async for delta in expand_graph(seed_list, iterations, max_concepts, temperature):
            data = delta.model_dump_json()
            yield f"data: {data}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
