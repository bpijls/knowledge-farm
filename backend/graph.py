import asyncio
import os
import re
from collections.abc import AsyncGenerator

from models import Edge, IterationDelta, Node

MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "8"))


def normalize(concept: str) -> str:
    return re.sub(r"\s+", " ", concept.strip().lower())


async def expand_graph(
    seeds: list[str],
    iterations: int,
    max_concepts: int,
    temperature: float = 0.7,
) -> AsyncGenerator[IterationDelta, None]:
    """Yield one IterationDelta per iteration as nodes/edges are discovered."""
    from llm import expand_concept

    nodes: dict[str, Node] = {}
    edges: set[frozenset] = set()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    # Seed nodes at depth 0
    seed_delta_nodes: list[Node] = []
    frontier: set[str] = set()
    for label in seeds:
        key = normalize(label)
        if not key:
            continue
        if key not in nodes:
            node = Node(id=key, label=label, depth=0)
            nodes[key] = node
            seed_delta_nodes.append(node)
            frontier.add(key)

    yield IterationDelta(iteration=0, nodes=seed_delta_nodes, edges=[])

    for iteration in range(1, iterations + 1):
        if not frontier or len(nodes) >= max_concepts:
            break

        current_frontier = list(frontier)
        frontier = set()

        async def expand_one(source_key: str) -> tuple[str, list[str]]:
            async with sem:
                source_label = nodes[source_key].label
                related = await expand_concept(source_label, temperature)
                return source_key, related

        tasks = [asyncio.create_task(expand_one(k)) for k in current_frontier]
        results = await asyncio.gather(*tasks)

        new_nodes: list[Node] = []
        new_edges: list[Edge] = []

        for source_key, related in results:
            for label in related:
                key = normalize(label)
                if not key:
                    continue

                edge_pair = frozenset({source_key, key})
                edge_is_new = edge_pair not in edges
                edges.add(edge_pair)

                if key not in nodes:
                    if len(nodes) >= max_concepts:
                        continue
                    node = Node(id=key, label=label, depth=iteration)
                    nodes[key] = node
                    new_nodes.append(node)
                    frontier.add(key)

                if edge_is_new:
                    new_edges.append(Edge(source=source_key, target=key))

        yield IterationDelta(iteration=iteration, nodes=new_nodes, edges=new_edges)
