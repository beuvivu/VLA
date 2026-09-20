"""CSS link tags — 2 parallel sheets + preload (no @import)."""

from __future__ import annotations


def stylesheet_link() -> str:
    """Parallel CSS: preload + 2 stylesheets (core + visual polish).

    Why 2 files (not 3-4 parts):
    - HTTP/2 multiplexes well with 2 mid-size sheets
    - Full rule coverage (split parts were incomplete)
    - Preload starts fetch before parser hits stylesheet links
    """
    return "\n  ".join(
        (
            '<link rel="preload" href="assets/ui.css" as="style" />',
            '<link rel="preload" href="assets/ui-visual-system.css" as="style" />',
            '<link rel="preload" href="assets/InterVariable.woff2" as="font" type="font/woff2" crossorigin />',
            '<link rel="stylesheet" href="assets/ui.css" />',
            '<link rel="stylesheet" href="assets/ui-visual-system.css" data-ui-visual-system />',
        )
    )
