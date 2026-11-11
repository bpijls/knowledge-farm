"""Images generated from `![alt](gen: prompt)` tags, cached on disk.

Ported from my-vault (`backend/app/services/images.py`). The cache key is sha1(prompt|size),
so an unchanged prompt is never drawn twice and editing it means a new image. A `.json`
sidecar records what produced each PNG.
"""
import base64
import hashlib
import json
import re
import time
from pathlib import Path

import httpx

from app.config import settings
from app.services.ai import ai

_SPEC_RE = re.compile(r"(.*?)\s*\|\s*(\d{2,4}x\d{2,4})\s*")
# `![alt](gen: prompt)` or `![alt](gen: prompt | 1280x720)`; the prompt may not contain `)`.
GEN_RE = re.compile(r"!\[([^\]\n]*)\]\(\s*gen:\s*([^)\n]*)\)", re.IGNORECASE)


class ImageError(Exception):
    pass


def parse_spec(spec: str) -> tuple[str, str]:
    """`a red fox` or `a red fox | 1280x720` → (prompt, size)."""
    m = _SPEC_RE.fullmatch(spec.strip())
    prompt, size = (m.group(1), m.group(2)) if m else (spec, settings.image_size)
    prompt = " ".join(prompt.split())
    if not prompt:
        raise ImageError("The gen: tag has no prompt.")
    return prompt, size


def gen_specs(markdown: str) -> list[str]:
    """The spec (text after `gen:`) of every image tag, in order."""
    return [m.group(2).strip() for m in GEN_RE.finditer(markdown)]


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "image"


def file_name(spec: str) -> str:
    prompt, size = parse_spec(spec)
    key = hashlib.sha1(f"{prompt}|{size}".encode()).hexdigest()[:8]
    return f"{_slug(prompt)}-{key}.png"


def cached_path(spec: str) -> Path:
    return Path(settings.image_dir) / file_name(spec)


async def _fetch(result: str) -> bytes:
    """vonk hands back either a URL or base64, depending on the backend."""
    if result.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.get(result)
            res.raise_for_status()
            return res.content
    return base64.b64decode(result.split(",", 1)[1] if result.startswith("data:") else result)


async def generate(spec: str, *, force: bool = False) -> Path:
    png = cached_path(spec)
    if png.exists() and not force:
        return png
    prompt, size = parse_spec(spec)
    result = await ai.image(prompt, model=settings.vonk_image_model, size=size)
    if not result:
        raise ImageError("vonk returned no image data.")
    try:
        data = await _fetch(result)
    except (httpx.HTTPError, ValueError) as exc:
        raise ImageError(f"Could not read the generated image: {exc}") from exc
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(data)
    meta = {"prompt": prompt, "size": size, "model": settings.vonk_image_model,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    png.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
    return png
