"""The report: outline from the graph, the grow_report job, and its endpoints."""
import base64

from app.models import Graph, Report
from app.services import images, jobs
from app.services import report as report_service
from app.services.jobs import Job
from app.services.report import (
    keep_one_image,
    model_language,
    outline,
    section_title,
    split_heading,
)

NODES = [
    {"id": "water", "label": "water", "depth": 0},
    {"id": "rain", "label": "rain", "depth": 1},
    {"id": "river", "label": "river", "depth": 1},
    {"id": "ice", "label": "ice", "depth": 1},
    {"id": "cloud", "label": "cloud", "depth": 2},
    {"id": "delta", "label": "delta", "depth": 2},
    {"id": "glacier", "label": "glacier", "depth": 2},
    {"id": "storm", "label": "storm", "depth": 2},
]
EDGES = [
    {"source": "water", "target": "rain"}, {"source": "water", "target": "river"},
    {"source": "water", "target": "ice"}, {"source": "rain", "target": "cloud"},
    {"source": "rain", "target": "storm"}, {"source": "rain", "target": "river"},
    {"source": "river", "target": "delta"}, {"source": "ice", "target": "glacier"},
    {"source": "glacier", "target": "river"},
]


def test_outline_ranks_branches_by_degree():
    o = outline(NODES, EDGES, max_sections=2)
    assert o.title == "water" and o.seed_ids == ["water"]
    # rain: water, cloud, storm, river = 4; river: water, rain, delta, glacier = 4; ice: 2
    assert [b.id for b in o.branches] == ["rain", "river"]
    rain = o.branches[0]
    assert set(rain.children) == {"cloud", "storm"}
    assert rain.links == ["river"]


def test_outline_links_branches_through_a_shared_child():
    o = outline(NODES, EDGES, max_sections=3)
    ice = next(b for b in o.branches if b.id == "ice")
    assert "river" in ice.links          # via glacier


def test_titles_and_language_names():
    assert section_title("phase transition") == "Phase transition"
    assert section_title("pH") == "pH" and section_title("DNA") == "DNA"
    assert model_language("Nederlands") == "Dutch (Nederlands)"
    assert model_language("English") == "English"


def test_looks_english():
    en = "The river carries water to the sea, and the delta is where it meets the salt of the ocean."
    nl = "De rivier voert water naar zee, en de delta is waar het zoete water het zoute ontmoet bij de kust."
    assert report_service.looks_english(en * 2) and not report_service.looks_english(nl * 2)


async def test_english_drift_is_retried_once(monkeypatch):
    replies = iter(["The answer and the text of this are in English, which is the wrong one " * 3,
                    "Nu in het Nederlands."])
    prompts = []

    class Fake:
        async def chat(self, prompt, **kwargs):
            prompts.append(prompt)
            return next(replies)

    monkeypatch.setattr(report_service, "ai", Fake())
    assert await report_service.write_text("Schrijf iets.", "Dutch (Nederlands)", max_tokens=50) == \
        "Nu in het Nederlands."
    assert prompts[1].startswith("Your previous answer was in English")


def test_split_heading_and_one_image():
    assert split_heading("## Oogst\n\nText") == ("Oogst", "Text")
    assert split_heading("Text") == (None, "Text")
    md = "A\n\n![x](gen: one)\n\nB\n\n![y](gen: two)\n\nC"
    assert keep_one_image(md) == "A\n\n![x](gen: one)\n\nB\n\nC"
    # a forgotten gen: prefix is put back; real image links are left alone
    assert keep_one_image("![m](3D render of a molecule, blue)") == "![m](gen: 3D render of a molecule, blue)"
    assert keep_one_image("![p](/api/images/a b.png)") == "![p](/api/images/a b.png)"


class FakeAI:
    def __init__(self, fail_section=None, fail_images=False):
        self.fail_section = fail_section
        self.fail_images = fail_images
        self.prompts = []

    async def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if self.fail_section and f'section "{self.fail_section}"' in prompt:
            raise RuntimeError("model error")
        if "closing part" in prompt:
            return "## The harvest\n\nAll together.\n\n![no](gen: should be dropped)"
        topic = prompt.split('"')[1]
        return f"## Heading\n\nOver {topic}.\n\n![{topic}](gen: a picture of {topic})\n\n![x](gen: extra)"

    async def image(self, prompt, *, model=None, size="1024x1024"):
        if self.fail_images:
            raise RuntimeError("no GPU")
        return base64.b64encode(f"img:{prompt}".encode()).decode()


async def _start(client, factory):
    async with factory() as db:
        g = Graph(seeds=["water"], nodes=NODES, edges=EDGES, params={})
        db.add(g)
        await db.commit()
        graph_id = g.id
    res = await client.post(f"/api/graphs/{graph_id}/reports", json={"language": "Nederlands"})
    assert res.status_code == 202
    body = res.json()
    return graph_id, body["report"]["id"], body["job"]["id"]


async def test_job_grows_the_report_and_draws_images(client, factory, monkeypatch, image_dir):
    fake = FakeAI()
    monkeypatch.setattr(report_service, "ai", fake)
    monkeypatch.setattr(images, "ai", fake)
    monkeypatch.setattr(report_service.settings, "report_max_sections", 3)

    graph_id, report_id, job_id = await _start(client, factory)
    await jobs.run_job(job_id, factory)

    async with jobs._lock(), factory() as db:
        job = await db.get(Job, job_id)
        report = await db.get(Report, report_id)
    assert job.status == "done", job.error
    assert all("Write every sentence in Dutch (Nederlands)" in p for p in fake.prompts)
    assert job.result == {"report_id": report_id, "sections": 5, "images": 4}

    keys = [s["key"] for s in report.sections]
    assert keys == ["intro", "s0", "s1", "s2", "conclusion"]
    assert report.status == "done"
    s0 = report.sections[1]
    # Nederlands: the model's translated heading becomes the title, and leaves the body
    assert s0["title"] == "Heading" and s0["source_node_ids"][0] == "rain"
    assert "Heading" not in s0["markdown"] and s0["markdown"].count("gen:") == 1
    concl = report.sections[-1]
    assert concl["title"] == "The harvest" and "gen:" not in concl["markdown"]
    assert sorted(p.name for p in image_dir.glob("*.png")) == sorted(
        images.file_name(f"a picture of {t}") for t in ["water", "rain", "river", "ice"])

    # endpoints
    got = (await client.get(f"/api/reports/{report_id}")).json()
    assert got["status"] == "done" and len(got["sections"]) == 5
    assert [r["id"] for r in (await client.get(f"/api/graphs/{graph_id}/reports")).json()] == [report_id]
    md = (await client.get(f"/api/reports/{report_id}/markdown")).text
    assert md.startswith("# water") and "## Heading" in md and "gen:" not in md
    assert "/api/images/a-picture-of-rain-" in md
    img = await client.get("/api/images", params={"spec": "a picture of rain"})
    assert img.status_code == 200 and img.content == b"img:a picture of rain"
    name = images.file_name("a picture of rain")
    assert (await client.get(f"/api/images/{name}")).status_code == 200
    assert (await client.get("/api/images", params={"spec": "never drawn"})).status_code == 404


async def test_a_failing_section_or_image_does_not_sink_the_report(client, factory, monkeypatch):
    fake = FakeAI(fail_section="river", fail_images=True)
    monkeypatch.setattr(report_service, "ai", fake)
    monkeypatch.setattr(images, "ai", fake)

    _, report_id, job_id = await _start(client, factory)
    await jobs.run_job(job_id, factory)

    async with jobs._lock(), factory() as db:
        job = await db.get(Job, job_id)
        report = await db.get(Report, report_id)
    assert job.status == "done"
    assert "river" not in [s["title"].lower() for s in report.sections]
    assert job.result["images"] == 0
    assert "image failed" in job.log_text


async def test_report_needs_branches(client, factory, monkeypatch):
    monkeypatch.setattr(report_service, "ai", FakeAI())
    async with factory() as db:
        g = Graph(seeds=["lonely"], nodes=[{"id": "lonely", "label": "lonely", "depth": 0}],
                  edges=[], params={})
        db.add(g)
        await db.commit()
    res = await client.post(f"/api/graphs/{g.id}/reports")
    job_id = res.json()["job"]["id"]
    await jobs.run_job(job_id, factory)
    async with jobs._lock(), factory() as db:
        job = await db.get(Job, job_id)
    assert job.status == "failed" and "no branches" in job.error


async def test_missing_graph_is_404(client):
    assert (await client.post("/api/graphs/nope/reports")).status_code == 404


async def test_style_reaches_every_prompt(client, factory, monkeypatch):
    seen = []

    class Fake(FakeAI):
        async def chat(self, prompt, **kwargs):
            seen.append((prompt, kwargs.get("system", "")))
            return await super().chat(prompt, **kwargs)

    fake = Fake()
    monkeypatch.setattr(report_service, "ai", fake)
    monkeypatch.setattr(images, "ai", fake)
    async with factory() as db:
        g = Graph(seeds=["water"], nodes=NODES, edges=EDGES, params={})
        db.add(g)
        await db.commit()
    res = await client.post(f"/api/graphs/{g.id}/reports", json={"style": "flyer"})
    assert res.json()["report"]["style"] == "flyer"
    await jobs.run_job(res.json()["job"]["id"], factory)

    flyer = report_service.STYLES["flyer"]
    assert seen and all(flyer.voice in system for _, system in seen)
    assert all("commercial flyer text" in prompt for prompt, _ in seen)
    image_prompts = [p for p, _ in seen if "closing part" not in p]
    assert all(flyer.image in p for p in image_prompts)


async def test_unknown_style_is_rejected_and_styles_are_listed(client, factory):
    async with factory() as db:
        g = Graph(seeds=["water"], nodes=NODES, edges=EDGES, params={})
        db.add(g)
        await db.commit()
    assert (await client.post(f"/api/graphs/{g.id}/reports", json={"style": "limerick"})).status_code == 422
    styles = (await client.get("/api/report-styles")).json()
    assert [s["key"] for s in styles] == ["prose", "business", "poetic", "flyer"]
