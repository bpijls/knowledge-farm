"""Reports grown from a graph, and the images they show."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Graph, Report
from app.routers.jobs import JobOut
from app.schemas import ReportOut
from app.services import images, jobs
from app.services.images import GEN_RE, ImageError
from app.services.report import STYLES, repair_image_tags

router = APIRouter(tags=["reports"])


class ReportIn(BaseModel):
    language: str | None = Field(default=None, max_length=40)
    style: Literal["prose", "business", "poetic", "flyer"] = "prose"


class ReportStarted(BaseModel):
    report: ReportOut
    job: JobOut


@router.post("/api/graphs/{graph_id}/reports", response_model=ReportStarted, status_code=202)
async def grow_report(graph_id: str, payload: ReportIn | None = None,
                      db: AsyncSession = Depends(get_db)):
    graph = await db.get(Graph, graph_id)
    if graph is None:
        raise HTTPException(404, "Graph not found")
    report = Report(graph_id=graph_id, title=", ".join(graph.seeds),
                    style=payload.style if payload else "prose")
    db.add(report)
    await db.commit()
    await db.refresh(report)
    params = {"report_id": report.id, "language": payload.language if payload else None}
    job = await jobs.enqueue(db, "grow_report", params, subject=f"graph:{graph_id}")
    return {"report": report, "job": job}


@router.get("/api/report-styles")
async def report_styles() -> list[dict]:
    """The styles a report can be grown in, for the selector."""
    return [{"key": s.key, "label": s.label} for s in STYLES.values()]


@router.get("/api/graphs/{graph_id}/reports", response_model=list[ReportOut])
async def list_reports(graph_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Report).where(Report.graph_id == graph_id).order_by(Report.created_at.desc())
    return list((await db.scalars(stmt)).all())


async def _report(db: AsyncSession, report_id: str) -> Report:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/api/reports/{report_id}", response_model=ReportOut)
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)):
    return await _report(db, report_id)


def to_markdown(report: Report, image_url=lambda name: f"images/{name}") -> str:
    """The whole report as one Markdown document, gen: tags turned into image links."""
    def link(m):
        try:
            return f"![{m.group(1)}]({image_url(images.file_name(m.group(2)))})"
        except ImageError:
            return ""

    parts = [f"# {report.title}"]
    for s in report.sections:
        if s.get("title"):
            parts.append(f"## {s['title']}")
        parts.append(GEN_RE.sub(link, repair_image_tags(s["markdown"])))
    return "\n\n".join(parts) + "\n"


@router.get("/api/reports/{report_id}/markdown", response_class=PlainTextResponse)
async def report_markdown(report_id: str, db: AsyncSession = Depends(get_db)):
    report = await _report(db, report_id)
    md = to_markdown(report, image_url=lambda name: f"/api/images/{name}")
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")


@router.get("/api/images")
async def image_for_spec(spec: str):
    """The cached image for a gen: tag; 404 until it has been drawn."""
    try:
        png = images.cached_path(spec)
    except ImageError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not png.is_file():
        raise HTTPException(404, "Not drawn yet.")
    return FileResponse(png, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/api/images/{name}")
async def image_by_name(name: str):
    if "/" in name or not name.endswith(".png") or name.startswith("."):
        raise HTTPException(400, "Bad image name")
    png = images.cached_path("x").parent / name
    if not png.is_file():
        raise HTTPException(404, "Not drawn yet.")
    return FileResponse(png)
