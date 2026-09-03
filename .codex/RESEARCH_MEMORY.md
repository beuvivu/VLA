# Research Memory

## RES-0001 — Public frequency / gan / cycle statistics

Source:
- https://www.minhngoc.net.vn/thong-ke-xo-so/tan-suat-mien.html
- https://mketqua.net/thong-ke-theo-tong
- https://hainhay.net/chu-ky-db
- https://xosodaiphat.com/

Observed concept:
Public tools expose configurable frequency, last occurrence/current gan, cycle,
head/tail/total and pair statistics.

Independent mathematical interpretation:
frequency separates occurrence count from hit-date count; gap is elapsed eligible
time since last hit; cycle is the completed inter-arrival distribution plus a
current censored interval.

VLA implementation:
`advanced_stats.py`, `cycle_stats.py`, `pair_stats.py`, `number_reference.py`.

Validation:
existing regression suite plus source comparison in `docs/research/`.

Status:
descriptive-only

Confidence:
high

Last verified:
2026-09-02

## RES-0002 — Dynamic positional cầu / two-nháy public behavior

Source:
https://rongbachkim.net/soicau-ngay-20-07-2026.html?db=0&exactlimit=0&limit=3&lon=1&nhay=2&showcau=&vt=103x104

Observed concept:
Public UI exposes source-position pair, lộn option, nháy threshold, maximum run
length and repeated candidate pairs produced by different position rules.

Independent mathematical interpretation:
A semantic position rule maps prior-draw digit positions to a candidate set; run
length is a consecutive success streak over eligible target dates. Two-nháy uses
the distinct target `occurrence_count >= 2` rather than ordinary `>=1` Loto hit.

VLA implementation:
`path_prob.py`, `cau_position_evidence.py`, `crosslag_positional_lab.py`,
`research_firewall.py`; exact >=2 occurrence statistics already exist in
`advanced_stats.compute_daily_nhay_stats`. Generic two-nháy positional target
integration remains a later research task.

Validation:
existing research firewall uses chronological segments, FDR/Bonferroni and
reality checks; production remains disconnected.

Status:
descriptive-only / challenger research

Confidence:
high for public mechanics; proprietary ranking unknown

Last verified:
2026-09-02

## RES-0003 — Pascal-style modulo-10 transform

Source:
- https://caulo168.com/soi-cau-pascal-cau-lo-168
- https://xsmb360.com/du-doan-xsmb-1-6-2025-thong-ke-xo-so-mien-bac-chu-nhat/

Observed concept:
Seed digits from recent lottery results are reduced row-by-row by adjacent sums,
keeping only the units digit. Public variants differ in seed selection, terminal
width and ranking overlays.

Independent mathematical interpretation:
`r^(k+1)_i = (r^(k)_i + r^(k)_(i+1)) mod 10`.

VLA implementation:
none canonical in this safety PR.

Validation:
not yet evaluated; deterministic recurrence is reproducible but forecasting value
is unproven.

Status:
challenger research planned

Confidence:
high for recurrence, medium for site-specific mapping

Last verified:
2026-09-02

## RES-0004 — Fibonacci lottery mapping not sufficiently defined

Source:
public web research pass on 2026-09-02.

Observed concept:
The standard Fibonacci recurrence is well-defined, but no sufficiently consistent
public Vietnamese lottery-history-to-candidate mapping was identified in the
reviewed sources.

Independent mathematical interpretation:
`F0=0, F1=1, Fn=F(n-1)+F(n-2)` only; no lottery mapping inferred.

VLA implementation:
none.

Validation:
not applicable until a deterministic mapping is specified independently.

Status:
rejected

Confidence:
high that VLA should not invent a mapping; low regarding any proprietary variants

Last verified:
2026-09-02

## RES-0005 — Domain challenger evidence hierarchy

Source:
internal ML audit plus statistical best practice.

Observed concept:
Deterministic folklore relations such as partner/cặp-50/bộ/bóng/chạm/tổng can be
computed safely but are not predictive evidence by themselves.

Independent mathematical interpretation:
Treat each relation as an explicit feature family and compare against the champion
under identical temporal folds/sample plan. Require paired draw-level uncertainty
before production influence.

VLA implementation:
`cau_keo_domain_challenger.py`, `ml_validation.py`.

Validation:
regression tests for metric direction, categorical Đề normalization, clustered
bootstrap, fold-plan identity, CI gate and production allowlist.

Status:
challenger

Confidence:
high

Last verified:
2026-09-02
