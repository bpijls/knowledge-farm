"""Growing a graph: expansion, dedupe, depth, limits, the SSE stream and saving."""
import json

from app.services import graph as graph_service
from app.services.graph import expand_graph, normalize

TREE = {
    "water": ["Rain", "river", "Ice"],
    "rain": ["cloud", "River"],          # "River" merges with "river"
    "river": ["delta", "rain"],
    "ice": ["glacier", "ice"],           # self-link is dropped
}


def fake_expand(mapping):
    async def expand(concept, temperature=0.7):
        return mapping.get(normalize(concept), [])
    return expand


async def collect(seeds, iterations=2, max_concepts=500):
    return [d async for d in expand_graph(seeds, iterations, max_concepts)]


def test_normalize():
    assert normalize("  Machine   Learning ") == "machine learning"


async def test_expands_dedupes_and_records_depth(monkeypatch):
    monkeypatch.setattr(graph_service, "expand_concept", fake_expand(TREE))
    deltas = await collect(["Water"])

    assert [d.iteration for d in deltas] == [0, 1, 2]
    nodes = {n.id: n for d in deltas for n in d.nodes}
    assert nodes["water"].depth == 0 and nodes["water"].label == "Water"
    assert {k for k, n in nodes.items() if n.depth == 1} == {"rain", "river", "ice"}
    assert {k for k, n in nodes.items() if n.depth == 2} == {"cloud", "delta", "glacier"}

    pairs = [frozenset((e.source, e.target)) for d in deltas for e in d.edges]
    assert len(pairs) == len(set(pairs))                 # undirected, no duplicates
    assert frozenset(("rain", "river")) in pairs          # cross-link between branches
    assert all(len(p) == 2 for p in pairs)                # no self-links


async def test_max_concepts_caps_the_graph(monkeypatch):
    monkeypatch.setattr(graph_service, "expand_concept", fake_expand(TREE))
    deltas = await collect(["water"], max_concepts=3)
    assert sum(len(d.nodes) for d in deltas) == 3


async def test_expand_concept_swallows_errors(monkeypatch):
    class Broken:
        async def json(self, *a, **k):
            raise RuntimeError("vonk down")

    monkeypatch.setattr(graph_service, "ai", Broken())
    assert await graph_service.expand_concept("x") == []


async def test_expand_concept_cleans_and_limits(monkeypatch):
    class Fake:
        async def json(self, *a, **k):
            return {"concepts": [" a ", "", "b", 3, "c", "d", "e", "f"]}

    monkeypatch.setattr(graph_service, "ai", Fake())
    assert await graph_service.expand_concept("x") == ["a", "b", "c", "d", "e"]


async def test_stream_sends_deltas_then_saves(client, monkeypatch):
    monkeypatch.setattr(graph_service, "expand_concept", fake_expand(TREE))
    res = await client.get("/api/graphs/stream", params={"seeds": "water", "iterations": 1})
    assert res.status_code == 200
    events = [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]
    assert events[0]["iteration"] == 0 and events[-1]["done"] is True

    graph_id = events[-1]["graph_id"]
    saved = (await client.get(f"/api/graphs/{graph_id}")).json()
    assert saved["seeds"] == ["water"]
    assert {n["id"] for n in saved["nodes"]} == {"water", "rain", "river", "ice"}
    assert [g["id"] for g in (await client.get("/api/graphs")).json()] == [graph_id]

    assert (await client.delete(f"/api/graphs/{graph_id}")).status_code == 204
    assert (await client.get(f"/api/graphs/{graph_id}")).status_code == 404


async def test_stream_needs_a_seed(client):
    assert (await client.get("/api/graphs/stream", params={"seeds": " , "})).status_code == 422
