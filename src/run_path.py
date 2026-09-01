from __future__ import annotations

"""Compatibility entrypoint for the historical ``run_path.py`` command.

The canonical path runner is ``run_path_ui.py``. Keeping two independent CLIs
previously created ambiguous, non-date-scoped prediction files under ``data/path``.
This wrapper delegates all supported legacy options to the canonical runner so
there is one implementation and one date-scoped artifact contract.
"""

import sys

from run_path_ui import main as canonical_main


LEGACY_DEFAULT_OUT = "data/path"
CANONICAL_DEFAULT_OUT = "data/path_ui"


def _translate_legacy_argv(argv: list[str]) -> list[str]:
    """Preserve legacy flags while routing output to the canonical artifact tree."""
    out = list(argv)
    if "--out-dir" not in out:
        out.extend(["--out-dir", CANONICAL_DEFAULT_OUT])
    return out


def main() -> None:
    sys.argv = [sys.argv[0], *_translate_legacy_argv(sys.argv[1:])]
    print(
        "[INFO] src/run_path.py is superseded; delegating to src/run_path_ui.py "
        "with date-scoped canonical outputs."
    )
    canonical_main()


if __name__ == "__main__":
    main()
