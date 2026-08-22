"""Safe, cached access to immutable versioned prompt templates."""

from functools import lru_cache
from pathlib import Path
from typing import Any


_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt(filename: str) -> str:
    """Load one flat, versioned prompt file from this package.

    Prompt versions are immutable: introduce a new ``*_vN.txt`` file for a
    behavioral change rather than editing an existing version.
    """
    path = (_PROMPTS_DIR / filename).resolve()
    if path.parent != _PROMPTS_DIR or path.suffix != ".txt":
        raise ValueError(f"Invalid prompt filename: {filename}")
    return path.read_text(encoding="utf-8").strip()


def render_prompt(filename: str, **values: Any) -> str:
    """Render a named prompt template using explicit runtime values."""
    return load_prompt(filename).format(**values)
