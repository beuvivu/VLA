"""CSS link tags — parallel loads, no @import."""

from __future__ import annotations


def stylesheet_link() -> str:
    """Return parallel <link> tags for core UI + visual system."""
    return "\n  ".join(
        (
            '<link rel="stylesheet" href="assets/ui-part1.css" />',
            '<link rel="stylesheet" href="assets/ui-part2.css" />',
            '<link rel="stylesheet" href="assets/ui-part3.css" />',
            '<link rel="stylesheet" href="assets/ui-visual-system.css" data-ui-visual-system />',
        )
    )
