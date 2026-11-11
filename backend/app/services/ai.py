"""Shared vonk client. Import `ai` rather than constructing your own."""
from vonk import AsyncVonk

from app.config import settings

ai = AsyncVonk(
    base_url=settings.vonk_base_url,
    api_key=settings.vonk_key,
    chat_model=settings.vonk_model,
    embed_model=settings.vonk_embed_model,
    image_model=settings.vonk_image_model,
)
