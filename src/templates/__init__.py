from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


class Render:
    """Small helper to render Jinja2 templates.

    The original implementation supported both sync/async environments; for this
    repository's usage (CLI scripts), a synchronous renderer is simpler and more
    reliable across Python versions.
    """

    def __init__(self, *, template_dir: Path | None = None) -> None:
        if template_dir is None:
            template_dir = Path(__file__).parent

        self._env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(),
        )

    def __call__(self, template_name: str, /, **context: Any) -> str:
        return self._env.get_template(template_name).render(**context)
