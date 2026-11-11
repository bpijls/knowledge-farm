"""Growing a concept graph: seeds expanded by the model, iteration by iteration.

Nodes are deduplicated by `normalize()`, which is also the node id. The frontend repeats the
same normalisation to find the seeds among the streamed nodes, so keep the two in sync
(`frontend/src/graph.js::normalize`).
"""
import asyncio
import logging
import re
from collections.abc import AsyncGenerator

from app.config import settings
from app.schemas import Edge, IterationDelta, Node
from app.services.ai import ai

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a knowledge graph assistant. "
    "When given a concept, return exactly a JSON object with a single key 'concepts' "
    "containing a list of up to {n} closely related concepts. "
    "No prose, no markdown, no code fences — raw JSON only. "
    'Example: {{"concepts": ["neural network", "gradient descent", "backpropagation"]}}'
)


def normalize(concept: str) -> str:
    return re.sub(r"\s+", " ", concept.strip().lower())


async def expand_concept(concept: str, temperature: float = 0.7) -> list[str]:
    """Up to CONCEPTS_PER_NODE related concepts. Never raises: a bad call yields []."""
    n = settings.concepts_per_node
    try:
        data = await ai.json(f"Concept: {concept}", system=SYSTEM_PROMPT.format(n=n),
                             temperature=temperature, max_tokens=300)
    except Exception as exc:  # noqa: BLE001 - one bad call never ends a graph
        log.warning("expanding %r failed: %s", concept, exc)
        return []
    # Lenient: a bare list is fine too, and stray non-strings are skipped rather than failing.
    concepts = data.get("concepts") if isinstance(data, dict) else data
    if not isinstance(concepts, list):
        return []
    return [c.strip() for c in concepts if isinstance(c, str) and c.strip()][:n]


async def expand_graph(
    seeds: list[str], iterations: int, max_concepts: int, temperature: float = 0.7,
) -> AsyncGenerator[IterationDelta, None]:
    """Yield one IterationDelta per iteration as nodes and edges are discovered."""
    nodes: dict[str, Node] = {}
    edges: set[frozenset] = set()
    sem = asyncio.Semaphore(settings.graph_concurrency)

    seed_nodes: list[Node] = []
    frontier: set[str] = set()
    for label in seeds:
        key = normalize(label)
        if key and key not in nodes:
            nodes[key] = Node(id=key, label=label.strip(), depth=0)
            seed_nodes.append(nodes[key])
            frontier.add(key)
    yield IterationDelta(iteration=0, nodes=seed_nodes, edges=[])

    for iteration in range(1, iterations + 1):
        if not frontier or len(nodes) >= max_concepts:
            break
        current, frontier = sorted(frontier), set()

        async def expand_one(key: str) -> tuple[str, list[str]]:
            async with sem:
                return key, await expand_concept(nodes[key].label, temperature)

        results = await asyncio.gather(*(expand_one(k) for k in current))

        new_nodes: list[Node] = []
        new_edges: list[Edge] = []
        for source, related in results:
            for label in related:
                key = normalize(label)
                if not key or key == source:
                    continue
                if key not in nodes:
                    if len(nodes) >= max_concepts:
                        continue
                    nodes[key] = Node(id=key, label=label, depth=iteration)
                    new_nodes.append(nodes[key])
                    frontier.add(key)
                pair = frozenset({source, key})
                if pair not in edges:
                    edges.add(pair)
                    new_edges.append(Edge(source=source, target=key))

        yield IterationDelta(iteration=iteration, nodes=new_nodes, edges=new_edges)
