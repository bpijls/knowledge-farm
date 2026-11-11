from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Node(BaseModel):
    id: str
    label: str
    depth: int


class Edge(BaseModel):
    source: str
    target: str


class IterationDelta(BaseModel):
    """One SSE message while a graph grows: what this iteration added."""

    iteration: int
    nodes: list[Node]
    edges: list[Edge]


class GraphSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seeds: list[str]
    params: dict
    created_at: datetime


class GraphOut(GraphSummary):
    nodes: list[Node]
    edges: list[Edge]


class Section(BaseModel):
    key: str
    title: str
    markdown: str
    source_node_ids: list[str] = []


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    graph_id: str
    title: str
    status: str
    sections: list[Section]
    created_at: datetime

