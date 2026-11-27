from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from math import comb
from typing import Literal, Mapping


class GameCode(str, Enum):

    MEGA_645 = "mega645"
    POWER_655 = "power655"
    LOTTO_535 = "lotto535"


BonusMode = Literal["none", "same_drum", "separate"]


@dataclass(frozen=True)
class PrizeTier:

    name: str
    main_matches: int
    bonus_required: bool = False
    fixed_amount: int | None = None
    main_matches_max: int | None = None

    @property
    def is_jackpot(self) -> bool:
        return self.fixed_amount is None

    def main_range(self) -> range:
        hi = self.main_matches if self.main_matches_max is None else self.main_matches_max
        return range(min(self.main_matches, hi), max(self.main_matches, hi) + 1)


@dataclass(frozen=True)
class TaxRule:

    rate: float = 0.10
    threshold: int = 20_000_000

    def after_tax(self, amount: float) -> float:
        return amount - self.rate * max(0.0, amount - self.threshold)


@dataclass(frozen=True)
class RolldownRule:

    threshold: int
    shares: Mapping[str, float]


@dataclass(frozen=True)
class GameSpec:

    code: GameCode
    display_name: str
    pool_size: int
    pick: int
    bonus_mode: BonusMode
    ticket_price: int
    tiers: tuple[PrizeTier, ...]
    min_jackpots: Mapping[str, int] = field(default_factory=dict)
    draw_weekdays: tuple[int, ...] = ()
    draws_per_day: int = 1
    bonus_pool_size: int | None = None
    jackpot_split: Mapping[str, float] = field(default_factory=dict)
    jackpot_cap: int | None = None
    rolldown: RolldownRule | None = None
    bao_levels: tuple[int, ...] = ()
    special_bao_max: int = 0

    @property
    def has_bonus(self) -> bool:
        return self.bonus_mode != "none"

    @property
    def separate_special(self) -> bool:
        return self.bonus_mode == "separate"

    @property
    def numbers(self) -> range:
        return range(1, self.pool_size + 1)

    @cached_property
    def total_combinations(self) -> int:
        base = comb(self.pool_size, self.pick)
        return base * (self.bonus_pool_size or 1) if self.separate_special else base

    @cached_property
    def main_combinations(self) -> int:
        return comb(self.pool_size, self.pick)

    @property
    def inclusion_probability(self) -> float:
        return self.pick / self.pool_size

    def tier(self, name: str) -> PrizeTier:
        for t in self.tiers:
            if t.name == name:
                return t
        raise KeyError(f"{self.code.value} has no tier {name!r}")

    def match_probability(self, m: int) -> float:
        n, k = self.pool_size, self.pick
        if m < 0 or m > k:
            return 0.0
        return comb(k, m) * comb(n - k, k - m) / comb(n, k)

    def match_distribution(self) -> list[float]:
        return [self.match_probability(m) for m in range(self.pick + 1)]

    def bonus_hit_probability(self, main_matches: int) -> float:
        if self.bonus_mode == "none":
            return 0.0
        if self.bonus_mode == "separate":
            return 1.0 / float(self.bonus_pool_size or 1)
        return (self.pick - main_matches) / (self.pool_size - self.pick)

    def outcome_tier(self, main_matches: int, bonus_hit: bool) -> PrizeTier | None:
        for t in self.tiers:
            if main_matches not in t.main_range():
                continue
            if t.bonus_required and not bonus_hit:
                continue
            return t
        return None

    @cached_property
    def tier_probabilities(self) -> dict[str, float]:
        probs = {t.name: 0.0 for t in self.tiers}
        for m in range(self.pick + 1):
            pm = self.match_probability(m)
            ph = self.bonus_hit_probability(m)
            for hit, p in ((True, ph), (False, 1.0 - ph)):
                if p <= 0:
                    continue
                t = self.outcome_tier(m, hit)
                if t is not None:
                    probs[t.name] += pm * p
        return probs

    @cached_property
    def p_any_prize(self) -> float:
        return float(sum(self.tier_probabilities.values()))

    def classify(self, main_matches: int, bonus_hit: bool = False) -> PrizeTier | None:
        return self.outcome_tier(main_matches, bonus_hit)


MEGA_645 = GameSpec(
    code=GameCode.MEGA_645,
    display_name="Mega 6/45",
    pool_size=45,
    pick=6,
    bonus_mode="none",
    ticket_price=10_000,
    tiers=(
        PrizeTier("jackpot1", 6),
        PrizeTier("first", 5, fixed_amount=10_000_000),
        PrizeTier("second", 4, fixed_amount=300_000),
        PrizeTier("third", 3, fixed_amount=30_000),
    ),
    min_jackpots={"jackpot1": 12_000_000_000},
    draw_weekdays=(2, 4, 6),
    jackpot_split={"jackpot1": 1.0},
    bao_levels=(5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18),
)

POWER_655 = GameSpec(
    code=GameCode.POWER_655,
    display_name="Power 6/55",
    pool_size=55,
    pick=6,
    bonus_mode="same_drum",
    ticket_price=10_000,
    tiers=(
        PrizeTier("jackpot1", 6),
        PrizeTier("jackpot2", 5, bonus_required=True),
        PrizeTier("first", 5, fixed_amount=40_000_000),
        PrizeTier("second", 4, fixed_amount=500_000),
        PrizeTier("third", 3, fixed_amount=50_000),
    ),
    min_jackpots={"jackpot1": 30_000_000_000, "jackpot2": 3_000_000_000},
    draw_weekdays=(1, 3, 5),
    jackpot_split={"jackpot1": 0.9, "jackpot2": 0.1},
    jackpot_cap=300_000_000_000,
    bao_levels=(5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18),
)

LOTTO_535 = GameSpec(
    code=GameCode.LOTTO_535,
    display_name="Lotto 5/35",
    pool_size=35,
    pick=5,
    bonus_mode="separate",
    bonus_pool_size=12,
    ticket_price=10_000,
    tiers=(
        PrizeTier("jackpot1", 5, bonus_required=True),
        PrizeTier("first", 5, fixed_amount=10_000_000),
        PrizeTier("second", 4, bonus_required=True, fixed_amount=5_000_000),
        PrizeTier("third", 4, fixed_amount=500_000),
        PrizeTier("fourth", 3, bonus_required=True, fixed_amount=100_000),
        PrizeTier("fifth", 3, fixed_amount=30_000),
        PrizeTier("consolation", 0, bonus_required=True, fixed_amount=10_000, main_matches_max=2),
    ),
    min_jackpots={"jackpot1": 6_000_000_000},
    draw_weekdays=(0, 1, 2, 3, 4, 5, 6),
    draws_per_day=2,
    jackpot_split={"jackpot1": 1.0},
    rolldown=RolldownRule(
        threshold=12_000_000_000,
        shares={"first": 1 / 3, "second": 1 / 6, "third": 1 / 6, "fourth": 1 / 6, "fifth": 1 / 6},
    ),
    bao_levels=(4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
    special_bao_max=12,
)

GAMES: dict[GameCode, GameSpec] = {g.code: g for g in (MEGA_645, POWER_655, LOTTO_535)}
SIX_NUMBER_GAMES = (GameCode.MEGA_645, GameCode.POWER_655)
DEFAULT_TAX = TaxRule()


def get_game(code: str | GameCode) -> GameSpec:
    aliases = {
        "645": GameCode.MEGA_645,
        "mega": GameCode.MEGA_645,
        "power645": GameCode.MEGA_645,
        "655": GameCode.POWER_655,
        "power": GameCode.POWER_655,
        "535": GameCode.LOTTO_535,
        "lotto": GameCode.LOTTO_535,
        "power535": GameCode.LOTTO_535,
    }
    key = code.value if isinstance(code, GameCode) else str(code).lower().strip()
    try:
        return GAMES[GameCode(key)]
    except ValueError:
        if key in aliases:
            return GAMES[aliases[key]]
        raise KeyError(f"Unknown game {code!r}; expected one of {[g.value for g in GameCode]}") from None
