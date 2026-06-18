from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    seeds: list[str]
    iterations: int = Field(default=2, ge=1, le=10)
    max_concepts: int = Field(default=500, ge=1, le=2000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class Node(BaseModel):
    id: str
    label: str
    depth: int


class Edge(BaseModel):
    source: str
    target: str


class GenerateResponse(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


# SSE iteration delta
class IterationDelta(BaseModel):
    iteration: int
    nodes: list[Node]
    edges: list[Edge]


# LLM response shape
class ConceptList(BaseModel):
    concepts: list[str]
