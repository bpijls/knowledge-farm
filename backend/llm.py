import json
import os
import re

import httpx

from models import ConceptList

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://vonk:4000")
LLM_MODEL = os.getenv("LLM_MODEL", "google/gemma-4-26B-A4B-it")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-8hkrYpm4ptmxRsbR4aFxRw")

_SYSTEM_PROMPT = (
    "You are a knowledge graph assistant. "
    "When given a concept, return exactly a JSON object with a single key 'concepts' "
    "containing a list of up to 5 closely related concepts. "
    "No prose, no markdown, no code fences — raw JSON only. "
    'Example: {"concepts": ["neural network", "gradient descent", "backpropagation"]}'
)

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=LLM_BASE_URL,
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            timeout=60.0,
        )
    return _client


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    # also strip <think>...</think> blocks some models emit
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


async def _call_once(concept: str, temperature: float) -> ConceptList | None:
    client = get_client()
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Concept: {concept}"},
        ],
        "temperature": temperature,
    }
    resp = await client.post("/v1/chat/completions", json=payload)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    raw = _strip_fences(content)
    data = json.loads(raw)
    return ConceptList.model_validate(data)


async def expand_concept(concept: str, temperature: float = 0.7) -> list[str]:
    """Return up to 5 related concepts, retrying once on parse failure."""
    for attempt in range(2):
        try:
            result = await _call_once(concept, temperature)
            if result:
                return [c.strip() for c in result.concepts if c.strip()][:5]
        except Exception:
            if attempt == 1:
                return []
    return []


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
