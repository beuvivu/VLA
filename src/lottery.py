from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
import requests

from dtos import Result, ResultList
from excel_export import export_excel_outputs
from sources import HttpClient, Source, default_sources, source_independence_key
from time_policy import VIETNAM_TZ, vietnam_date

logger = logging.getLogger(__name__)


def vietnam_today(*, now: datetime | None = None) -> date:
    """Return the domain date in Vietnam rather than the runner's local date."""
    return vietnam_date(now)


@dataclass(frozen=True)
class RepoPaths:
    """Common paths used by the project.

    The codebase historically used relative paths (e.g. "data/xsmb.json"), which
    break when scripts are executed from outside the repository root. Centralising
    path resolution makes the scripts more robust.
    """

    root: Path
    data_dir: Path
    images_dir: Path

    @classmethod
    def from_module(cls) -> "RepoPaths":
        root = Path(__file__).resolve().parents[1]
        return cls(root=root, data_dir=root / "data", images_dir=root / "images")


class Lottery:
    def __init__(
        self,
        *,
        paths: RepoPaths | None = None,
        http: HttpClient | None = None,
        sources: list[Source] | None = None,
    ) -> None:
        self._paths = paths or RepoPaths.from_module()
        # Use a normal HTTP session. The collector must not bypass CAPTCHA or
        # anti-bot protections; inaccessible sources simply fail closed.
        self._http = http or requests.Session()

        # Ordered public-source policy.  This order is also the deterministic
        # display/diagnostic tie-breaker, but never overrides an ambiguous
        # verification tie between equally supported independent result groups.
        self._sources: list[Source] = sources or default_sources()

        self._data: dict[date, Result] = {}
        self._fetch_audit: dict[str, dict[str, Any]] = {}

        self._raw_data: pd.DataFrame = pd.DataFrame()
        self._2_digits_data: pd.DataFrame = pd.DataFrame()
        self._sparse_data: pd.DataFrame = pd.DataFrame()

        self._begin_date = vietnam_today()
        self._last_date = self._begin_date

    def load(self) -> None:
        xsmb_path = self._paths.data_dir / "xsmb.json"
        if not xsmb_path.exists():
            logger.warning("Data file not found: %s (starting with empty dataset)", xsmb_path)
            self._data = {}
            self.generate_dataframes()
            return

        with xsmb_path.open("r", encoding="utf-8") as f:
            data = ResultList.model_validate_json(f.read())
        dates = [item.date for item in data.root]
        if len(dates) != len(set(dates)):
            raise ValueError("xsmb.json contains duplicate draw dates")
        for d in data.root:
            self._data[d.date] = d

        self.generate_dataframes()

    def dump(self) -> None:
        def _dump(df: pd.DataFrame, file_name: str) -> None:
            self._paths.data_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(self._paths.data_dir / f"{file_name}.csv", index=False)
            df.to_json(
                self._paths.data_dir / f"{file_name}.json",
                orient="records",
                date_format="iso",
                indent=2,
                index=False,
            )

        _dump(self._raw_data, "xsmb")
        _dump(self._2_digits_data, "xsmb-2-digits")
        _dump(self._sparse_data, "xsmb-sparse")
        export_excel_outputs(
            raw_df=self._raw_data,
            two_digit_df=self._2_digits_data,
            sparse_df=self._sparse_data,
            data_dir=self._paths.data_dir,
            latest_daily_only=True,
        )
        if self._fetch_audit:
            audit_path = self._paths.data_dir / "source_audit.json"
            existing: dict[str, Any] = {}
            if audit_path.exists():
                try:
                    existing = json.loads(audit_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            existing.update(self._fetch_audit)
            # Keep the audit compact: latest 120 requested dates.
            trimmed = dict(sorted(existing.items())[-120:])
            audit_path.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _result_signature(result: Result) -> tuple[int, ...]:
        payload = result.model_dump()
        return tuple(int(payload[k]) for k in payload if k != "date")

    def fetch(self, selected_date: date, *, min_agreement: int = 1) -> bool:
        """Fetch a draw, optionally requiring independent source agreement.

        ``min_agreement=1`` preserves the fast historical backfill behavior. For
        recent/final draws, ``min_agreement=2`` asks all configured providers and
        only promotes a candidate when at least two independent parsers agree on
        every prize field. Conflicting single-source data is never written, and
        an equal-support tie between distinct verified candidates is rejected.
        """
        min_agreement = max(1, int(min_agreement))
        candidates: list[tuple[str, Result]] = []

        for source in self._sources:
            name = getattr(source, "name", "?")
            try:
                result = source.fetch(selected_date, self._http)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Source %s failed for %s: %s", name, selected_date, exc)
                continue

            if result is None:
                continue
            if result.date != selected_date:
                logger.warning("Source %s returned date %s for requested %s; skipping", name, result.date, selected_date)
                continue

            candidates.append((name, result))
            if min_agreement == 1:
                self._data[selected_date] = result
                self._fetch_audit[selected_date.isoformat()] = {
                    "checked_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "accepted": True,
                    "required_agreement": 1,
                    "agreement": 1,
                    "runner_up_agreement": 0,
                    "ambiguous_tie": False,
                    "sources": [name],
                    "candidates": 1,
                }
                return True

        grouped: dict[tuple[int, ...], list[tuple[str, Result]]] = defaultdict(list)
        for item in candidates:
            grouped[self._result_signature(item[1])].append(item)

        best: list[tuple[str, Result]] = []
        best_group_count = 0
        runner_up_group_count = 0
        ambiguous_tie = False
        if grouped:
            # Canonical promotion is determined by independent-provider support.
            # Raw source count and configured priority may order candidates for
            # diagnostics, but MUST NOT break an equal-support verification tie.
            def group_score(items: list[tuple[str, Result]]) -> tuple[int, int, int]:
                groups = {source_independence_key(name) for name, _ in items}
                first_priority = min(
                    i for i, source in enumerate(self._sources)
                    if getattr(source, "name", "?") in {name for name, _ in items}
                )
                return len(groups), len(items), -first_priority

            ranked = sorted(grouped.values(), key=group_score, reverse=True)
            best = ranked[0]
            best_group_count = len(
                {source_independence_key(name) for name, _ in best}
            )
            if len(ranked) > 1:
                runner_up_group_count = len(
                    {source_independence_key(name) for name, _ in ranked[1]}
                )
                ambiguous_tie = (
                    best_group_count >= min_agreement
                    and runner_up_group_count == best_group_count
                )

        accepted = best_group_count >= min_agreement and not ambiguous_tie
        self._fetch_audit[selected_date.isoformat()] = {
            "checked_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "accepted": accepted,
            "required_agreement": min_agreement,
            "agreement": best_group_count,
            "runner_up_agreement": runner_up_group_count,
            "ambiguous_tie": ambiguous_tie,
            "source_agreement": len(best),
            "independent_groups": list(
                dict.fromkeys(source_independence_key(name) for name, _ in best)
            ),
            "sources": [name for name, _ in best],
            "candidates": len(candidates),
            "distinct_results": len(grouped),
        }
        if ambiguous_tie:
            logger.warning(
                "Ambiguous consensus tie for %s: top two distinct results each have %d independent group(s); canonical data unchanged",
                selected_date,
                best_group_count,
            )
        if accepted:
            self._data[selected_date] = best[0][1]
            logger.info(
                "Consensus accepted for %s: %d independent group(s), %d source(s): %s",
                selected_date,
                best_group_count,
                len(best),
                ", ".join(name for name, _ in best),
            )
            return True

        if candidates:
            logger.warning(
                "No unambiguous %d-source consensus for %s (candidates=%d, distinct=%d); canonical data unchanged",
                min_agreement, selected_date, len(candidates), len(grouped),
            )
        return False

    def generate_dataframes(self) -> None:
        if not self._data:
            self._raw_data = pd.DataFrame(columns=["date"])
            self._2_digits_data = pd.DataFrame(columns=["date"])
            self._sparse_data = pd.DataFrame(columns=["date"])
            self._begin_date = vietnam_today()
            self._last_date = self._begin_date
            return

        ordered: list[dict[str, Any]] = [self._data[d].model_dump() for d in sorted(self._data)]
        self._raw_data = pd.DataFrame(ordered)
        self._raw_data["date"] = pd.to_datetime(self._raw_data["date"])
        self._raw_data.iloc[:, 1:] = self._raw_data.iloc[:, 1:].astype("int64")
        self._raw_data.sort_values("date", inplace=True, ignore_index=True)

        # 2-digit view (lô tô) - vectorised.
        self._2_digits_data = self._raw_data.copy(deep=True)
        self._2_digits_data.iloc[:, 1:] = self._2_digits_data.iloc[:, 1:] % 100

        # Sparse view: for each draw, count occurrences of each number 00..99.
        values = self._2_digits_data.iloc[:, 1:].to_numpy(dtype=np.int16, copy=False)
        sparse = np.apply_along_axis(lambda row: np.bincount(row, minlength=100), 1, values)
        sparse_df = pd.DataFrame(sparse, columns=list(range(100)), dtype="int64")
        self._sparse_data = pd.concat([self._2_digits_data[["date"]], sparse_df], axis=1)

        begin_dt = self._raw_data["date"].min()
        last_dt = self._raw_data["date"].max()
        self._begin_date = begin_dt.to_pydatetime().date()
        self._last_date = last_dt.to_pydatetime().date()

    def get_raw_data(self) -> pd.DataFrame:
        return self._raw_data

    def get_2_digits_data(self) -> pd.DataFrame:
        return self._2_digits_data

    def get_sparse_data(self) -> pd.DataFrame:
        return self._sparse_data

    def get_last_date(self) -> date:
        return self._last_date

    def get_dates(self) -> set[date]:
        """Return the set of dates currently loaded."""

        return set(self._data.keys())

    def has_date(self, d: date) -> bool:
        return d in self._data
