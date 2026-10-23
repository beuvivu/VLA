from __future__ import annotations

"""Compatibility entrypoint for the superseded Markdown dashboard builder.

``build_markdown_dashboard_v3.py`` is the only canonical DASHBOARD.md renderer.
This file remains solely so external scripts that still invoke the historical
command continue to work without maintaining a second rendering implementation.
"""

from pages.build_markdown_dashboard_v3 import main as canonical_main


def main() -> None:
    print(
        "[THÔNG TIN] src/pages/build_markdown_dashboard.py đã được thay thế; "
        "chuyển sang src/pages/build_markdown_dashboard_v3.py."
    )
    canonical_main()


if __name__ == "__main__":
    main()
