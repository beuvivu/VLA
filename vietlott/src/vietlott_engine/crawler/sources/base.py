from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from vietlott_engine.core.games import GameSpec
from vietlott_engine.core.models import Draw


@dataclass
class FetchResult:

    draws: list[Draw] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)


class DrawSource(ABC):

    name: str = "abstract"

    @abstractmethod
    async def fetch(self, spec: GameSpec, since_id: int | None = None) -> FetchResult:
        pass
