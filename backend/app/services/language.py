"""The two languages a graph or report can be grown in, and how to name them to the model."""
from typing import Literal

# What the UI sends. A Literal so the API rejects anything else.
Language = Literal["English", "Nederlands"]

_MODEL_LANGUAGE = {"nederlands": "Dutch (Nederlands)", "dutch": "Dutch (Nederlands)"}


def model_language(language: str) -> str:
    """'Nederlands' → 'Dutch (Nederlands)': small models follow the English name more reliably."""
    return _MODEL_LANGUAGE.get(language.strip().lower(), language.strip())


def is_english(language: str) -> bool:
    return language.strip().lower().startswith("english")
