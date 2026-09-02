# Research Memory

Verified repository/domain research only. These notes do not alter model weights.

## RES-0001 — Frequency / gan / cycle terminology is broadly public

Source:
- https://mketqua.net/soi-cau
- https://mketqua.net/loto-gan
- https://hainhay.net/
- https://xosodaiphat.com/xsdpthongke/xsdptktonghop
- https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html

Observed concept:
Public Vietnamese lottery-analysis platforms commonly expose frequency, last-seen/gan, cycle, head/tail/total and pair statistics.

Independent mathematical interpretation:
Counts/hit dates, time since latest prior occurrence, recurrence intervals and digit-group aggregates with explicit as-of windows.

VLA implementation:
`advanced_stats.py`, `cycle_stats.py`, `descriptive_extensions.py`, `pair_stats.py`, `number_reference.py`.

Validation:
Existing regression tests plus research catalog audit.

Status:
descriptive-only

Confidence:
high

Last verified:
2026-09-02

## RES-0002 — Public positional cầu exposes position pairs, run length and lộn modes

Source:
- https://rongbachkim.net/tools-soicau.html
- public Rồng Bạch Kim `soicau-...` pages
- https://mketqua.net/soi-cau
- https://hainhay.net/cau-hai-nhay

Observed concept:
Public tools visibly select digit positions, show a historical cầu length/run and may distinguish lộn/non-lộn and two-nháy target behavior.

Independent mathematical interpretation:
A rule is semantic source position(s) + exact calendar lag(s) + deterministic transformation + target success event; current run length counts consecutive successes ending at the evaluation boundary.

VLA implementation:
`crosslag_positional_lab.py`, `path_models.py`, `research_firewall.py`, `cau_position_evidence.py`.

Validation:
Existing chronological validation/holdout and multiple-testing safeguards were audited. Exact proprietary search implementation is unknown.

Status:
challenger/research-only

Confidence:
high for the independent concept; medium for exact external equivalence

Last verified:
2026-09-02

## RES-0003 — Two-nháy is a distinct target event

Source:
- https://hainhay.net/cau-hai-nhay
- public Rồng Bạch Kim pages with `nhay=2`

Observed concept:
Two-nháy pages distinguish a number/pair appearing multiple times from an ordinary Loto presence event.

Independent mathematical interpretation:
For number x on target draw D: ordinary hit is `count(x,D)>=1`; two-nháy is `count(x,D)>=2`; exact occurrence count should also be retained.

VLA implementation:
`advanced_stats.compute_daily_nhay_stats` covers descriptive counts; positional two-nháy remains research-only.

Validation:
Source comparison and existing canonical occurrence-count data.

Status:
descriptive-only / research-only

Confidence:
medium-high

Last verified:
2026-09-02

## RES-0004 — Pascal-style public method is deterministic adjacent modulo-10 reduction

Source:
Public Vietnamese "cầu Pascal" descriptions found in lottery-analysis articles; exact surrounding ranking rules vary by publisher.

Observed concept:
Starting digits are repeatedly reduced by adding adjacent digits and retaining the last digit/modulo 10, forming a triangular table.

Independent mathematical interpretation:
`r_next[i]=(r[i]+r[i+1]) mod 10`, repeated until a configured output width.

VLA implementation:
No production implementation in this tranche. Mathematical contract documented in `docs/research/algorithm_definitions.md`.

Validation:
Research comparison only; no predictive experiment executed.

Status:
research-only

Confidence:
medium

Last verified:
2026-09-02

## RES-0005 — Fibonacci lottery-number mapping is not sufficiently defined

Source:
Public search results inspected during the 2026-09-02 research pass.

Observed concept:
Results mix the standard Fibonacci sequence with betting-stake/gấp-thế progression and loosely specified number-selection numerology.

Independent mathematical interpretation:
The sequence `F0=0,F1=1,Fn=F(n-1)+F(n-2)` is unambiguous, but no consistent public XSMB-history-to-number transform was established.

VLA implementation:
None; intentionally not invented.

Validation:
Definition-gap review.

Status:
rejected

Confidence:
high that implementation should be deferred; low regarding any proprietary lottery mapping

Last verified:
2026-09-02
