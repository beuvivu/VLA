from __future__ import annotations

import logging

from ingest.lottery import Lottery
from ingest.sync import ensure_up_to_date


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    lottery = Lottery()
    lottery.load()
    ensure_up_to_date(lottery=lottery)


if __name__ == "__main__":
    main()
