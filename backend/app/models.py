import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Graph(Base):
    """A grown concept graph, saved when its stream finishes so it can be reopened."""

    __tablename__ = "graphs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    seeds: Mapped[list] = mapped_column(JSON, default=list)
    # iterations, max_concepts, temperature
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    nodes: Mapped[list] = mapped_column(JSON, default=list)    # [{id, label, depth}]
    edges: Mapped[list] = mapped_column(JSON, default=list)    # [{source, target}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Report(Base):
    """A report grown from a graph by the `grow_report` job, section by section.

    `sections` is a list of {key, title, markdown, source_node_ids}; the job rewrites the whole
    list after each section so readers polling the row see it grow.
    """

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    graph_id: Mapped[str] = mapped_column(ForeignKey("graphs.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(16), default="growing")   # growing | done | failed
    sections: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
