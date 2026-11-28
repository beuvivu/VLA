from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pytest

from ingest.fetch_results import (
    DEFAULT_REQUEST_TIMEOUT,
    TOTAL_SLOTS,
    USER_AGENTS,
    PollConfig,
    _TimeoutCappedSession,
    build_session,
    poll_once,
    poll_until_complete,
    stamp,
)
from ingest.sources import EXPECTED_COUNTS, PRIZE_ORDER, STALE_PAGE_ERROR

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
TARGET = date(2026, 9, 7)


def _full_prize_map() -> dict[str, list[str]]:
    widths = {
        "special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
        "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2,
    }
    out: dict[str, list[str]] = {}
    seed = 10
    for key in PRIZE_ORDER:
        vals = []
        for _ in range(EXPECTED_COUNTS[key]):
            seed = (seed * 7 + 13) % (10 ** widths[key])
            vals.append(str(seed).zfill(widths[key]))
        out[key] = vals
    return out


class FakeSource:

    def __init__(self, name: str, script: list[dict[str, list[str]]]) -> None:
        self.name = name
        self.script = script
        self.calls = 0
        self.timeouts_seen: list[float] = []

    def fetch_partial(self, selected_date, http, *, live=False):
        idx = min(self.calls, len(self.script) - 1)
        self.calls += 1
        payload = self.script[idx]
        if isinstance(payload, Exception):
            raise payload
        return payload


class BoomSource(FakeSource):

    def fetch_partial(self, selected_date, http, *, live=False):
        self.calls += 1
        raise TimeoutError("nguồn quá hạn")


class FakeClock:

    def __init__(self, start: datetime) -> None:
        self.now = start
        self.slept: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now = self.now + timedelta(seconds=seconds)


def test_total_slots_is_the_xsmb_invariant() -> None:
    assert TOTAL_SLOTS == 27


@pytest.mark.parametrize(
    "kwargs",
    [
        {"interval_seconds": (0, 90)},
        {"interval_seconds": (90, 60)},
        {"request_timeout": 0},
        {"min_agreement": 0},
        {"max_rounds": 0},
    ],
)
def test_config_rejects_impossible_settings(kwargs) -> None:
    with pytest.raises(ValueError):
        PollConfig(target=TARGET, **kwargs)


def test_default_timeout_is_tight_enough_for_peak_hour() -> None:
    assert DEFAULT_REQUEST_TIMEOUT <= 8.0


def test_session_sends_a_browser_user_agent() -> None:
    session = build_session()
    ua = session.headers["User-Agent"]
    assert ua in USER_AGENTS
    assert "python-requests" not in ua


def test_session_sends_the_headers_a_real_browser_would() -> None:
    headers = build_session().headers
    assert "Accept-Language" in headers
    assert "vi" in headers["Accept-Language"]


def test_user_agent_pool_has_more_than_one_entry() -> None:
    assert len(set(USER_AGENTS)) >= 3


class _RecordingSession:
    def __init__(self, status: int = 200, boom: Exception | None = None) -> None:
        self.seen: list[float] = []
        self.status = status
        self.boom = boom

    def get(self, url, timeout=None, **kwargs):
        self.seen.append(timeout)
        if self.boom is not None:
            raise self.boom

        class _Resp:
            status_code = self.status
            text = ""

        return _Resp()


def test_timeout_cap_overrides_a_longer_caller_timeout() -> None:
    inner = _RecordingSession()
    _TimeoutCappedSession(inner, 8.0).get("http://x", timeout=15)
    assert inner.seen == [8.0]


def test_timeout_cap_keeps_a_shorter_caller_timeout() -> None:
    inner = _RecordingSession()
    _TimeoutCappedSession(inner, 8.0).get("http://x", timeout=3)
    assert inner.seen == [3.0]


def test_timeout_cap_applies_when_caller_passes_nothing() -> None:
    inner = _RecordingSession()
    _TimeoutCappedSession(inner, 8.0).get("http://x")
    assert inner.seen == [8.0]


def test_a_single_round_verifies_when_two_groups_agree() -> None:
    full = _full_prize_map()
    sources = [FakeSource("a.vn", [full]), FakeSource("b.vn", [full])]
    _, verified, stats = poll_once(sources, TARGET, min_agreement=2)
    assert verified == TOTAL_SLOTS
    assert all(s["complete"] for s in stats)


def test_one_source_alone_cannot_verify_under_two_group_agreement() -> None:
    full = _full_prize_map()
    empty = {k: [] for k in PRIZE_ORDER}
    sources = [FakeSource("a.vn", [full]), FakeSource("b.vn", [empty])]
    _, verified, _ = poll_once(sources, TARGET, min_agreement=2)
    assert verified == 0


def test_a_dead_source_does_not_sink_the_round() -> None:
    full = _full_prize_map()
    sources = [FakeSource("a.vn", [full]), BoomSource("b.vn", []), FakeSource("c.vn", [full])]
    _, verified, stats = poll_once(sources, TARGET, min_agreement=2)
    assert verified == TOTAL_SLOTS
    errored = [s for s in stats if s["error"]]
    assert len(errored) == 1
    assert "TimeoutError" in errored[0]["error"]


def test_round_reports_per_source_latency_for_diagnosis() -> None:
    full = _full_prize_map()
    _, _, stats = poll_once([FakeSource("a.vn", [full])], TARGET, min_agreement=1)
    assert stats[0]["latency_ms"] >= 0
    assert stats[0]["source"] == "a.vn"


def test_stats_come_back_in_business_priority_order() -> None:
    full = _full_prize_map()
    sources = [FakeSource(f"s{i}.vn", [full]) for i in range(5)]
    _, _, stats = poll_once(sources, TARGET, min_agreement=2)
    assert [s["priority"] for s in stats] == [1, 2, 3, 4, 5]


def _cfg(**kw) -> PollConfig:
    base = dict(
        target=TARGET,
        window_start=dtime(18, 15),
        deadline=dtime(19, 30),
        interval_seconds=(60.0, 60.0),
        min_agreement=1,
    )
    base.update(kw)
    return PollConfig(**base)


def test_the_fallbacks_are_not_asked_while_the_primary_answers() -> None:
    full = _full_prize_map()
    primary, backup = FakeSource("xoso.vn", [full]), FakeSource("du-phong.vn", [full])
    clock = FakeClock(datetime(2026, 9, 7, 18, 33, tzinfo=TZ))

    outcome = poll_until_complete(_cfg(), sources=[primary, backup], sleeper=clock.sleep, clock=clock)

    assert outcome.verified is True
    assert (primary.calls, backup.calls) == (1, 0)


def test_values_arriving_during_the_draw_do_not_wake_the_fallbacks() -> None:
    partial = dict(_full_prize_map())
    partial["prize7"] = []
    primary, backup = FakeSource("xoso.vn", [partial]), FakeSource("du-phong.vn", [_full_prize_map()])
    clock = FakeClock(datetime(2026, 9, 7, 18, 25, tzinfo=TZ))

    poll_until_complete(_cfg(deadline=dtime(18, 26)), sources=[primary, backup],
                        sleeper=clock.sleep, clock=clock)

    assert backup.calls == 0


def test_a_dead_primary_hands_the_round_to_the_fallbacks() -> None:
    full = _full_prize_map()
    primary, backup = BoomSource("xoso.vn", []), FakeSource("du-phong.vn", [full])
    clock = FakeClock(datetime(2026, 9, 7, 18, 33, tzinfo=TZ))

    outcome = poll_until_complete(_cfg(), sources=[primary, backup], sleeper=clock.sleep, clock=clock)

    assert outcome.verified is True
    assert backup.calls == 1
    assert [row["priority"] for row in outcome.source_stats] == [1, 2]


def test_a_primary_stuck_after_18_40_hands_over_to_the_fallbacks() -> None:
    full = _full_prize_map()
    partial = dict(full)
    partial["prize7"] = []
    primary, backup = FakeSource("xoso.vn", [partial]), FakeSource("du-phong.vn", [full])
    clock = FakeClock(datetime(2026, 9, 7, 18, 45, tzinfo=TZ))

    outcome = poll_until_complete(_cfg(), sources=[primary, backup], sleeper=clock.sleep, clock=clock)

    assert outcome.verified is True
    assert outcome.prize_map["prize7"] == full["prize7"]


def test_a_page_still_showing_yesterday_is_never_verified() -> None:
    yesterday = _full_prize_map()
    primary = FakeSource("xoso.vn", [yesterday])
    backup = FakeSource("du-phong.vn", [yesterday])
    clock = FakeClock(datetime(2026, 9, 7, 18, 15, tzinfo=TZ))

    outcome = poll_until_complete(
        _cfg(deadline=dtime(18, 17), previous_draw=yesterday),
        sources=[primary, backup], sleeper=clock.sleep, clock=clock,
    )

    assert outcome.verified is False
    assert outcome.verified_slots == 0
    assert backup.calls >= 1, "nguồn chính còn hiện kỳ trước là sự cố, phải hỏi dự phòng"
    assert {row["error"] for row in outcome.source_stats} == {STALE_PAGE_ERROR}


def test_todays_draw_is_verified_once_the_page_moves_on() -> None:
    yesterday = _full_prize_map()
    today = {**_full_prize_map(), "special": ["00000"]}
    primary = FakeSource("xoso.vn", [yesterday, today])
    clock = FakeClock(datetime(2026, 9, 7, 18, 15, tzinfo=TZ))

    outcome = poll_until_complete(
        _cfg(previous_draw=yesterday), sources=[primary], sleeper=clock.sleep, clock=clock,
    )

    assert outcome.verified is True
    assert outcome.prize_map["special"] == ["00000"]


def test_a_two_group_threshold_asks_every_source_from_the_start() -> None:
    full = _full_prize_map()
    primary, backup = FakeSource("xoso.vn", [full]), FakeSource("du-phong.vn", [full])
    clock = FakeClock(datetime(2026, 9, 7, 18, 33, tzinfo=TZ))

    outcome = poll_until_complete(
        _cfg(min_agreement=2), sources=[primary, backup], sleeper=clock.sleep, clock=clock,
    )

    assert outcome.verified is True
    assert outcome.rounds == 1
    assert (primary.calls, backup.calls) == (1, 1)


def test_polling_stops_the_moment_all_27_are_verified() -> None:
    full = _full_prize_map()
    empty = {k: [] for k in PRIZE_ORDER}
    script = [empty, empty, full, full, full]
    sources = [FakeSource("a.vn", list(script)), FakeSource("b.vn", list(script))]
    clock = FakeClock(datetime(2026, 9, 7, 18, 15, tzinfo=TZ))

    outcome = poll_until_complete(_cfg(), sources=sources, sleeper=clock.sleep, clock=clock)

    assert outcome.verified is True
    assert outcome.rounds == 3, "phải dừng ngay vòng đủ số, không chạy tiếp"
    assert sources[0].calls == 3


def test_polling_waits_until_the_window_opens() -> None:
    full = _full_prize_map()
    sources = [FakeSource("a.vn", [full]), FakeSource("b.vn", [full])]
    clock = FakeClock(datetime(2026, 9, 7, 17, 50, tzinfo=TZ))

    poll_until_complete(_cfg(), sources=sources, sleeper=clock.sleep, clock=clock)

    assert clock.slept, "phải chờ tới khung quay"
    assert clock.slept[0] == pytest.approx(25 * 60), "chờ đúng 25 phút tới 18:15"


def test_polling_does_not_wait_when_started_inside_the_window() -> None:
    full = _full_prize_map()
    sources = [FakeSource("a.vn", [full]), FakeSource("b.vn", [full])]
    clock = FakeClock(datetime(2026, 9, 7, 18, 20, tzinfo=TZ))

    outcome = poll_until_complete(_cfg(), sources=sources, sleeper=clock.sleep, clock=clock)

    assert clock.slept == []
    assert outcome.rounds == 1


def test_polling_gives_up_at_the_deadline() -> None:
    empty = {k: [] for k in PRIZE_ORDER}
    sources = [FakeSource("a.vn", [empty]), FakeSource("b.vn", [empty])]
    clock = FakeClock(datetime(2026, 9, 7, 18, 15, tzinfo=TZ))

    outcome = poll_until_complete(
        _cfg(deadline=dtime(18, 20)), sources=sources, sleeper=clock.sleep, clock=clock
    )

    assert outcome.verified is False
    assert clock.now <= datetime(2026, 9, 7, 18, 21, tzinfo=TZ)


def test_polling_never_sleeps_past_the_deadline() -> None:
    empty = {k: [] for k in PRIZE_ORDER}
    sources = [FakeSource("a.vn", [empty])]
    clock = FakeClock(datetime(2026, 9, 7, 19, 29, tzinfo=TZ))

    poll_until_complete(
        _cfg(interval_seconds=(90.0, 90.0), min_agreement=1),
        sources=sources, sleeper=clock.sleep, clock=clock,
    )

    assert clock.now <= datetime(2026, 9, 7, 19, 30, 1, tzinfo=TZ)


def test_partial_progress_is_reported_even_on_failure() -> None:
    full = _full_prize_map()
    partial = dict(full)
    partial["prize7"] = []
    sources = [FakeSource("a.vn", [partial]), FakeSource("b.vn", [partial])]
    clock = FakeClock(datetime(2026, 9, 7, 18, 15, tzinfo=TZ))

    outcome = poll_until_complete(
        _cfg(deadline=dtime(18, 18)), sources=sources, sleeper=clock.sleep, clock=clock
    )

    assert outcome.verified is False
    assert outcome.verified_slots == TOTAL_SLOTS - 4


def test_max_rounds_is_a_backstop_against_a_broken_clock() -> None:
    empty = {k: [] for k in PRIZE_ORDER}
    sources = [FakeSource("a.vn", [empty])]
    frozen = datetime(2026, 9, 7, 18, 15, tzinfo=TZ)

    outcome = poll_until_complete(
        _cfg(max_rounds=4, min_agreement=1),
        sources=sources,
        sleeper=lambda _s: None,
        clock=lambda: frozen,
    )

    assert outcome.rounds == 4


def test_outcome_serialises_to_plain_json_types() -> None:
    import json

    full = _full_prize_map()
    sources = [FakeSource("a.vn", [full]), FakeSource("b.vn", [full])]
    clock = FakeClock(datetime(2026, 9, 7, 18, 15, tzinfo=TZ))
    outcome = poll_until_complete(_cfg(), sources=sources, sleeper=clock.sleep, clock=clock)

    json.dumps(outcome.to_dict(), ensure_ascii=False)


def test_log_stamp_carries_both_timezones() -> None:
    text = stamp(datetime(2026, 9, 7, 18, 15, 0, tzinfo=TZ))
    assert "18:15:00 ICT" in text
    assert "11:15:00 UTC" in text


def test_wrapper_records_a_network_error_it_reraises() -> None:
    inner = _RecordingSession(boom=TimeoutError("quá hạn"))
    wrapper = _TimeoutCappedSession(inner, 8.0)
    with pytest.raises(TimeoutError):
        wrapper.get("http://x")
    assert wrapper.last_error is not None
    assert "TimeoutError" in wrapper.last_error


def test_wrapper_records_a_non_200_status() -> None:
    wrapper = _TimeoutCappedSession(_RecordingSession(status=429), 8.0)
    wrapper.get("http://x")
    assert wrapper.last_error == "HTTP 429"
    assert wrapper.last_status == 429


def test_wrapper_records_no_error_on_success() -> None:
    wrapper = _TimeoutCappedSession(_RecordingSession(status=200), 8.0)
    wrapper.get("http://x")
    assert wrapper.last_error is None


class _SilentlyFailingSource:

    name = "im-lặng.vn"

    def fetch_partial(self, selected_date, http, *, live=False):
        try:
            http.get("http://x", timeout=15)
        except Exception:
            pass
        return {k: [] for k in PRIZE_ORDER}


def test_a_silently_swallowed_error_still_reaches_the_stats(monkeypatch) -> None:
    from ingest import fetch_results as mod

    monkeypatch.setattr(
        mod, "build_session", lambda *a, **k: _RecordingSession(boom=OSError("mạng hỏng"))
    )
    _, _, stats = poll_once([_SilentlyFailingSource()], TARGET, min_agreement=1)
    assert stats[0]["error"] is not None, "lỗi bị nuốt phải nổi lên nhật ký"
    assert "OSError" in stats[0]["error"]


class _FlakySession:

    def __init__(self, fail_times: int, status: int = 503, boom: Exception | None = None,
                 retry_after: str | None = None) -> None:
        self.fail_times = fail_times
        self.status = status
        self.boom = boom
        self.retry_after = retry_after
        self.calls = 0

    def get(self, url, timeout=None, **kwargs):
        self.calls += 1
        outer = self

        class _Resp:
            headers = {"Retry-After": outer.retry_after} if outer.retry_after else {}
            status_code = outer.status if outer.calls <= outer.fail_times else 200
            text = ""

        if outer.calls <= outer.fail_times and outer.boom is not None:
            raise outer.boom
        return _Resp()


def _wrap(inner, **kw):
    naps: list[float] = []
    kw.setdefault("max_attempts", 3)
    session = _TimeoutCappedSession(inner, 8.0, sleeper=naps.append, **kw)
    return session, naps


def test_retries_a_transient_server_error_then_succeeds() -> None:
    inner = _FlakySession(fail_times=2, status=503)
    session, naps = _wrap(inner)
    resp = session.get("http://x")
    assert resp.status_code == 200
    assert inner.calls == 3
    assert len(naps) == 2, "phải chờ giữa các lần thử"


def test_retries_rate_limiting() -> None:
    inner = _FlakySession(fail_times=1, status=429)
    session, _ = _wrap(inner)
    assert session.get("http://x").status_code == 200
    assert inner.calls == 2


@pytest.mark.parametrize("status", [403, 404, 410])
def test_does_not_retry_a_permanent_error(status) -> None:
    inner = _FlakySession(fail_times=5, status=status)
    session, naps = _wrap(inner)
    assert session.get("http://x").status_code == status
    assert inner.calls == 1
    assert naps == []


def test_retries_a_network_exception() -> None:
    inner = _FlakySession(fail_times=1, status=200, boom=TimeoutError("quá hạn"))
    session, _ = _wrap(inner)
    assert session.get("http://x").status_code == 200
    assert inner.calls == 2


def test_gives_up_after_max_attempts_and_reraises() -> None:
    inner = _FlakySession(fail_times=99, status=200, boom=OSError("mạng hỏng"))
    session, naps = _wrap(inner, max_attempts=3)
    with pytest.raises(OSError):
        session.get("http://x")
    assert inner.calls == 3
    assert len(naps) == 2, "chờ giữa các lần, không chờ sau lần cuối"


def test_backoff_grows_exponentially() -> None:
    inner = _FlakySession(fail_times=99, status=503)
    session, naps = _wrap(inner, max_attempts=4, backoff_base=1.0, backoff_cap=100.0)
    session.get("http://x")
    assert 0.5 <= naps[0] <= 1.0
    assert 1.0 <= naps[1] <= 2.0
    assert 2.0 <= naps[2] <= 4.0


def test_backoff_is_jittered_not_a_fixed_ladder() -> None:
    seen = set()
    for _ in range(12):
        inner = _FlakySession(fail_times=99, status=503)
        session, naps = _wrap(inner, max_attempts=2, backoff_base=1.0, backoff_cap=100.0)
        session.get("http://x")
        seen.add(round(naps[0], 6))
    assert len(seen) > 1, "độ trễ phải có nhiễu, không phải bậc thang cố định"


def test_backoff_respects_retry_after_but_caps_it() -> None:
    inner = _FlakySession(fail_times=99, status=429, retry_after="600")
    session, naps = _wrap(inner, max_attempts=2, backoff_base=0.5, backoff_cap=4.0)
    session.get("http://x")
    assert naps[0] <= 4.0


def test_retry_budget_must_fit_inside_the_poll_interval() -> None:
    with pytest.raises(ValueError, match="ngân sách thử lại"):
        PollConfig(
            target=TARGET,
            request_timeout=8.0,
            max_attempts=20,
            interval_seconds=(60.0, 90.0),
        )


def test_default_config_has_a_feasible_retry_budget() -> None:
    cfg = PollConfig(target=TARGET)
    assert cfg.max_attempts * cfg.request_timeout <= cfg.interval_seconds[0]


class _RequestingSource:

    name = "co-goi.vn"

    def fetch_partial(self, selected_date, http, *, live=False):
        http.get("http://x", timeout=15)
        return _full_prize_map()


def test_attempt_count_reaches_the_stats_for_diagnosis(monkeypatch) -> None:
    from ingest import fetch_results as mod

    monkeypatch.setattr(mod, "build_session", lambda *a, **k: _FlakySession(fail_times=2, status=503))
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    _, _, stats = poll_once([_RequestingSource()], TARGET, min_agreement=1)
    assert stats[0]["attempts"] == 3, "phải báo đủ số lần đã thử"


def test_a_source_that_never_requests_reports_zero_attempts() -> None:
    full = _full_prize_map()
    _, _, stats = poll_once([FakeSource("a.vn", [full])], TARGET, min_agreement=1)
    assert stats[0]["attempts"] == 0


def test_a_start_after_the_deadline_still_polls_once() -> None:
    full = _full_prize_map()
    sources = [FakeSource("a.vn", [full]), FakeSource("b.vn", [full])]
    clock = FakeClock(datetime(2026, 9, 7, 21, 0, tzinfo=TZ))

    outcome = poll_until_complete(_cfg(), sources=sources, sleeper=clock.sleep, clock=clock)

    assert outcome.verified is True
    assert outcome.rounds == 1
    assert clock.slept == []


def test_a_late_start_that_finds_no_result_does_not_keep_polling() -> None:
    empty = {k: [] for k in PRIZE_ORDER}
    sources = [FakeSource("a.vn", [empty]), FakeSource("b.vn", [empty])]
    clock = FakeClock(datetime(2026, 9, 7, 21, 0, tzinfo=TZ))

    outcome = poll_until_complete(_cfg(), sources=sources, sleeper=clock.sleep, clock=clock)

    assert outcome.verified is False
    assert outcome.rounds == 1
    assert clock.slept == []


def test_the_command_line_reads_the_previous_draw_from_the_ledger(tmp_path, monkeypatch) -> None:
    from ingest import fetch_results as mod

    full = _full_prize_map()
    header = ["date"] + [
        key if EXPECTED_COUNTS[key] == 1 else f"{key}_{i}"
        for key in PRIZE_ORDER
        for i in range(1, EXPECTED_COUNTS[key] + 1)
    ]
    row = ["2026-09-06"] + [value for key in PRIZE_ORDER for value in full[key]]
    ledger = tmp_path / "xsmb.csv"
    ledger.write_text(",".join(header) + "\n" + ",".join(row) + "\n", encoding="utf-8")

    seen: list[PollConfig] = []

    def fake_poll(config: PollConfig) -> object:
        seen.append(config)
        now = datetime(2026, 9, 7, 18, 15, tzinfo=TZ)
        return mod.PollOutcome(False, 0, TOTAL_SLOTS, 0, {k: [] for k in PRIZE_ORDER}, now, now)

    monkeypatch.setattr(mod, "poll_until_complete", fake_poll)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    mod.main(["--date", "2026-09-07", "--history", str(ledger)])

    assert seen[0].previous_draw == full
