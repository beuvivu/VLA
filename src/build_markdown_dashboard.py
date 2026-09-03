from __future__ import annotations

"""Compatibility entrypoint for the superseded Markdown dashboard builder.

``build_markdown_dashboard_v3.py`` is the only canonical DASHBOARD.md renderer.
This file remains solely so external scripts that still invoke the historical
command continue to work without maintaining a second rendering implementation.
"""

from build_markdown_dashboard_v3 import main as canonical_main


def main() -> None:
    print(
        "[THÔNG TIN] src/build_markdown_dashboard.py đã được thay thế; "
        "chuyển sang src/build_markdown_dashboard_v3.py."
    )
    canonical_main()


if __name__ == "__main__":
    main()
