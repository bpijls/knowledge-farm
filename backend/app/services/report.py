"""Growing a report from a graph: the `grow_report` job.

The outline comes from the graph itself, not from the model: the seed's strongest branches
(depth-1 neighbours ranked by degree) become sections, their children become the material
each section is written from. The model only writes; the graph decides what about.

Order of work, each step saved to the `reports` row as soon as it exists so a reader polling
it sees the report grow:
    intro (with a hero image tag) → sections in parallel (one image tag each) → conclusion
    → the images, drawn by the image model and cached (services/images.py)
"""
import logging
import re
from dataclasses import dataclass, field

from app.config import settings
from app.models import Graph, Report
from app.services import images
from app.services.ai import ai
from app.services.jobs import JobContext, job, run_all

log = logging.getLogger(__name__)

MAX_CHILDREN = 8


@dataclass
class Branch:
    id: str
    label: str
    children: list[str] = field(default_factory=list)       # labels
    child_ids: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)          # labels of related branches


@dataclass
class Outline:
    title: str
    seed_ids: list[str]
    branches: list[Branch]


def outline(nodes: list[dict], edges: list[dict], max_sections: int) -> Outline:
    """Pick the report's sections from the graph. Deterministic: no model involved."""
    by_id = {n["id"]: n for n in nodes}
    adj: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    for e in edges:
        if e["source"] in adj and e["target"] in adj:
            adj[e["source"]].add(e["target"])
            adj[e["target"]].add(e["source"])

    seeds = [n for n in nodes if n["depth"] == 0]
    seed_ids = [n["id"] for n in seeds]
    title = ", ".join(n["label"] for n in seeds) or "Report"

    def rank(node_id: str) -> tuple:
        return (-len(adj[node_id]), by_id[node_id]["label"].lower())

    first = {nid for s in seed_ids for nid in adj[s] if by_id[nid]["depth"] == 1}
    chosen = sorted(first, key=rank)[:max_sections]

    branches: list[Branch] = []
    for bid in chosen:
        kids = sorted((k for k in adj[bid] if by_id[k]["depth"] > 1), key=rank)[:MAX_CHILDREN]
        branches.append(Branch(id=bid, label=by_id[bid]["label"],
                               children=[by_id[k]["label"] for k in kids], child_ids=kids))

    # Two branches are related when they touch directly or share a child.
    reach = {b.id: adj[b.id] | {b.id} for b in branches}
    for b in branches:
        b.links = [o.label for o in branches
                   if o.id != b.id and (o.id in adj[b.id] or (reach[b.id] & reach[o.id]) - {b.id, o.id})]
    return Outline(title=title, seed_ids=seed_ids, branches=branches)


# --- prompts ------------------------------------------------------------------------------

_IMAGE_RULES = (
    "Include exactly one image tag, on its own line, where the image belongs: "
    "![alt text](gen: image prompt | {size}). The alt text is a few words in {language}. "
    "The image prompt is always in English, whatever the language of the text, as one concrete "
    "description: the subject, the setting, the style or medium, the composition and the light. "
    "No text or lettering in the image, and no ')' in the prompt."
)

SYSTEM = (
    "You write one part of a short illustrated report that grows from a single seed word and "
    "the concepts that word led to. Write in {language}, in plain Markdown, for a curious "
    "general reader: concrete, vivid, no filler, no bullet lists. Do not start with a heading: "
    "the app adds it. Weave the given concepts in naturally; never just list them."
)


# What the model is told for a UI language name; local models follow "Dutch" more reliably.
_MODEL_LANGUAGE = {"nederlands": "Dutch (Nederlands)", "dutch": "Dutch (Nederlands)"}


def model_language(language: str) -> str:
    return _MODEL_LANGUAGE.get(language.strip().lower(), language.strip())


def _system(language: str) -> str:
    return SYSTEM.format(language=language)


def _closing(language: str) -> str:
    """Repeated at the end of every prompt: small models drift back to English otherwise."""
    return f" Write every sentence in {language}; only the image prompt stays in English."


def is_english(language: str) -> bool:
    return language.strip().lower().startswith("english")


_ENGLISH_MARKERS = {"the", "and", "of", "to", "that", "with", "which", "its", "this", "are"}


def looks_english(text: str) -> bool:
    """Crude but enough: English function words are rare in Dutch, German, French prose."""
    words = re.findall(r"[a-z]+", text.lower())
    return len(words) > 20 and sum(w in _ENGLISH_MARKERS for w in words) / len(words) > 0.05


async def write_text(prompt: str, language: str, *, max_tokens: int) -> str:
    """One model call for report text, retried once if it came back in English by mistake."""
    text = await ai.chat(prompt, system=_system(language), max_tokens=max_tokens, temperature=0.7)
    if not is_english(language) and looks_english(images.GEN_RE.sub("", text)):
        log.info("answer drifted into English; asking again in %s", language)
        text = await ai.chat(
            f"Your previous answer was in English, which is wrong. {prompt}",
            system=_system(language), max_tokens=max_tokens, temperature=0.5)
    return text


def section_title(label: str) -> str:
    """Capitalise plain lowercase labels; leave "pH", "DNA", "iPhone" alone."""
    return label[:1].upper() + label[1:] if label == label.lower() else label


def _image_rules(language: str) -> str:
    return _IMAGE_RULES.format(language=language, size=settings.image_size)


def intro_prompt(o: Outline, language: str) -> str:
    return (
        f'Write the introduction (about 120 words, 1–2 paragraphs) of a report on "{o.title}". '
        f"The report's sections will be about: {', '.join(b.label for b in o.branches)}. "
        f"Say why these belong together, without summarising each one. "
        + _image_rules(language) + _closing(language)
    )


def section_prompt(o: Outline, b: Branch, language: str) -> str:
    related = f" It connects to the sections on {', '.join(b.links)}; mention that link once." \
        if b.links else ""
    material = ", ".join(b.children) or "(no further concepts)"
    return (
        f'Write the section "{b.label}" (about 180 words, 2–3 paragraphs) of a report on '
        f'"{o.title}". Build it from these related concepts: {material}.{related} '
        + ("" if is_english(language) else
           f"Start with one line '## ' plus the section title in {language}. ")
        + _image_rules(language) + _closing(language)
    )


def conclusion_prompt(o: Outline, language: str) -> str:
    return (
        f'Write the closing part (about 100 words) of a report on "{o.title}" that covered '
        f"{', '.join(b.label for b in o.branches)}. Start with one line '## ' plus a short, "
        f"evocative heading in {language}, then one or two paragraphs that tie the threads "
        f"together. No image." + _closing(language)
    )


# --- cleaning the model's text --------------------------------------------------------------

_HEADING = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$")


def split_heading(markdown: str) -> tuple[str | None, str]:
    """A leading `# Heading` line, if any, and the rest."""
    lines = markdown.strip().splitlines()
    if lines and (m := _HEADING.match(lines[0])):
        return m.group(1).strip(), "\n".join(lines[1:]).strip()
    return None, markdown.strip()


# `![alt](a prompt with spaces)`: an image tag where the model forgot the `gen:` prefix.
_BARE_PROMPT = re.compile(r"!\[([^\]\n]*)\]\(\s*(?!gen:|https?://|/|\.)([^)\n]*\s[^)\n]*)\)",
                          re.IGNORECASE)


def repair_image_tags(markdown: str) -> str:
    return _BARE_PROMPT.sub(lambda m: f"![{m.group(1)}](gen: {m.group(2).strip()})", markdown)


def keep_one_image(markdown: str) -> str:
    """The model sometimes adds a second image, or forgets `gen:`; one proper tag remains."""
    markdown = repair_image_tags(markdown)
    seen = False

    def sub(m: re.Match) -> str:
        nonlocal seen
        if seen:
            return ""
        seen = True
        return m.group(0)

    return re.sub(r"\n{3,}", "\n\n", images.GEN_RE.sub(sub, markdown)).strip()


def drop_images(markdown: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", images.GEN_RE.sub("", markdown)).strip()


# --- the job ---------------------------------------------------------------------------------

@job("grow_report")
async def grow_report(ctx: JobContext, report_id: str, language: str | None = None) -> dict:
    language = model_language(language or settings.report_language)
    async with ctx.db() as db:
        report = await db.get(Report, report_id)
        if report is None:
            raise RuntimeError(f"Report {report_id} no longer exists")
        graph = await db.get(Graph, report.graph_id)
        nodes, edges = list(graph.nodes), list(graph.edges)

    o = outline(nodes, edges, settings.report_max_sections)
    if not o.branches:
        raise RuntimeError("The graph has no branches to write about: grow it at least one step.")

    # Slots keep the reading order however the parallel sections finish.
    order = ["intro", *(f"s{i}" for i in range(len(o.branches))), "conclusion"]
    written: dict[str, dict] = {}

    async def save(status: str = "growing") -> None:
        async with ctx.db() as db:
            row = await db.get(Report, report_id)
            row.sections = [written[k] for k in order if k in written]
            row.status = status
            await db.commit()

    try:
        await ctx.set_total(len(order))
        await ctx.progress("Writing the introduction")
        async with ctx.gate("llm"):
            text = await write_text(intro_prompt(o, language), language, max_tokens=600)
        written["intro"] = {"key": "intro", "title": "", "markdown": keep_one_image(split_heading(text)[1]),
                            "source_node_ids": o.seed_ids}
        await save()
        await ctx.step("  introduction")

        await ctx.progress("Writing the sections")

        async def write(i: int, b: Branch) -> None:
            async with ctx.gate("llm"):
                try:
                    text = await write_text(section_prompt(o, b, language), language,
                                            max_tokens=800)
                except Exception as exc:  # noqa: BLE001 - one section must not sink the report
                    await ctx.step(f"  {b.label}: failed ({exc})")
                    return
            heading, body = split_heading(text)
            # A translated heading when the model gave one, else the concept itself.
            title = section_title(heading if heading and not is_english(language) else b.label)
            written[f"s{i}"] = {"key": f"s{i}", "title": title,
                                "markdown": keep_one_image(body),
                                "source_node_ids": [b.id, *b.child_ids]}
            await save()
            await ctx.step(f"  {b.label}")

        await run_all(write(i, b) for i, b in enumerate(o.branches))

        await ctx.progress("Writing the conclusion")
        async with ctx.gate("llm"):
            text = await write_text(conclusion_prompt(o, language), language, max_tokens=500)
        heading, body = split_heading(text)
        written["conclusion"] = {"key": "conclusion", "title": section_title(heading or ""), "markdown": drop_images(body),
                                 "source_node_ids": [*o.seed_ids, *(b.id for b in o.branches)]}
        await save()
        await ctx.step("  conclusion")

        specs = [s for k in order if k in written for s in images.gen_specs(written[k]["markdown"])]
        await ctx.set_total(len(order) + len(specs))
        await ctx.progress(f"Drawing {len(specs)} image(s) with {settings.vonk_image_model}")
        drawn = 0

        async def draw(spec: str) -> None:
            nonlocal drawn
            async with ctx.gate("image", settings.image_concurrency):
                try:
                    await images.generate(spec)
                    drawn += 1
                    await ctx.step(f"  drew: {spec[:60]}")
                except Exception as exc:  # noqa: BLE001 - a missing image stays a placeholder
                    await ctx.step(f"  image failed: {exc}")

        await run_all(draw(s) for s in specs)
        await save("done")
    except Exception:
        await save("failed")
        raise
    return {"report_id": report_id, "sections": len(written), "images": drawn}
