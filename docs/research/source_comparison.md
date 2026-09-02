# Public Source Comparison

Verified: 2026-09-02

This document compares **publicly observable functionality**, not proprietary
source code. Exact hidden ranking formulas are never assumed. When VLA implements
an equivalent concept, it does so independently from mathematical definitions.

| Method | Public source / observed feature | VLA equivalent | Mathematical basis | Descriptive value | Leakage risk | Predictive status |
|---|---|---|---|---|---|---|
| Frequency | Minh Ngọc frequency tables; mketqua totals; Xổ Số Đại Phát occurrence statistics | `advanced_stats.compute_frequency`, rolling ML features | count occurrences and hit dates in window | high | low with cutoff | existing feature, OOS-gated where predictive |
| Lô gan | Minh Ngọc gan; mketqua "số lượt quay chưa về" | `cycle_stats.py`, `advanced_stats.compute_overdue` | elapsed eligible dates/draws since last hit | high | low with cutoff | descriptive |
| Cycle | Hainhay chu kỳ ĐB/loto | `cycle_stats.py`, `advanced_stats.compute_cycle_stats` | inter-arrival intervals + current censoring | high | low | descriptive |
| Head/tail | Minh Ngọc, Hainhay, Xổ Số Đại Phát | `number_reference.py`, `advanced_stats.py` | first/final digit groups | high | low | descriptive/challenger |
| Total | mketqua thống kê theo tổng; Hainhay | `number_reference.digit_sum_mod10`, descriptive stats | `(A+B) mod 10` when explicitly named modulo-10 | high | low | descriptive/challenger |
| Chạm | Hainhay/public ĐB analytics | `number_reference.dan_cham`, challenger | A=d or B=d | high | low | descriptive/challenger |
| Pair frequency | Minh Ngọc pair views; Hainhay/Xổ Số Đại Phát pair statistics | `pair_stats.py`, `cap_loto_50_stats.py` | same-date co-occurrence/support | high | low | descriptive |
| Reverse/lộn | Rồng Bạch Kim lộn option and public terminology | `number_reference.reverse`, baseline/challenger features | AB -> BA | high | none for mapping | challenger only |
| Cặp 50 | common Vietnamese pair ontology | `number_reference.cap_loto_50*` | 45 reverse pairs + 5 kép-bóng pairs | high | none for mapping | challenger only |
| Bộ/bóng | common Vietnamese ontology | `number_reference.py` | deterministic orbit/mappings | high | none for mapping | challenger only |
| Dynamic positional cầu | Rồng Bạch Kim source-position pages and run length; mketqua/hainhay cầu menus | `path_prob.py`, `crosslag_positional_lab.py`, `research_firewall.py` | source positions -> deterministic candidate; consecutive success streak | high research value | high | research-only unless separately promoted |
| 2 nháy | Rồng Bạch Kim/Hainhay "Hai nháy" | occurrence counts in `advanced_stats.py`; generic path integration later | target occurs >=2 times in draw | high descriptive value | high if target-day data used | untested pattern hypothesis |
| Conditional ĐB->loto / loto->loto | Hainhay "loto theo đặc biệt/loto" | `conditional_matrices.py`, `conditional_nextday.py` | transition counts, conditional probability, lift | high | medium/high | research/challenger |
| Markov | statistical research method | `markov_stats.py`, `number_dynamics.py` | smoothed transition posterior | medium | high if globally fitted | research signal; no automatic promotion |
| Pascal | several public Pascal pages | none canonical yet | adjacent sum modulo 10 recurrence | reproducible transform | medium due selection bias | research-only planned |
| Fibonacci | inconsistent public lottery mapping | none | standard recurrence known; lottery mapping undefined | low until defined | unknown | rejected/not implemented |
| Candidate score | common public ranking presentation | `cau_keo_ml.py`, `statistics_ai_overlay.py` | weighted normalized evidence | useful explanation | depends on inputs | score, not probability |

## Source notes

### Minh Ngọc

Public pages expose configurable frequency queries by number of draws and query
mode, plus gan-related navigation. This supports independent implementations of
frequency/overdue statistics; it does not expose evidence that those statistics
predict a future draw.

Relevant public page:
https://www.minhngoc.net.vn/thong-ke-xo-so/tan-suat-mien.html

### mketqua.net

The public "thống kê theo tổng" page exposes total historical appearances, last
appearance date and number of draws since last appearance, and navigation to
frequency, pair frequency, cầu loto and bạch thủ tools. VLA independently defines
those quantities rather than copying display logic.

Relevant public page:
https://mketqua.net/thong-ke-theo-tong

### Hainhay

Public pages/navigation expose lô gan, tần suất loto/cặp, chu kỳ loto/ĐB,
head-tail, loto conditional on ĐB/loto, bạch thủ, hai nháy and special-prize cầu.
The public cycle page makes the "last occurrence -> current gan" behavior directly
observable.

Relevant public page:
https://hainhay.net/chu-ky-db

### Rồng Bạch Kim

Public cầu pages expose position-pair identifiers, lộn and nháy controls, maximum
running length, concrete source positions and repeated candidate-pair summaries.
VLA already has semantic positional engines and therefore should extend those
engines rather than create parallel hard-coded tables.

Relevant public example:
https://rongbachkim.net/soicau-ngay-20-07-2026.html?db=0&exactlimit=0&limit=3&lon=1&nhay=2&showcau=&vt=103x104

### Xổ Số Đại Phát

Public XSMB pages expose/navigation to loto gan, cặp loto cùng về, loto kép,
head/tail, last appearance, 00-99 and cycle statistics. This corroborates the
terminology catalog but does not reveal proprietary prediction logic.

Example public page:
https://xosodaiphat.com/xsmb-16-07-2026.html

## Independent-implementation rule

For every concept where an exact site algorithm/ranking formula is not public,
VLA's status is:

**Independent implementation based on publicly observable behavior.**

Replication of a descriptive transformation is not validation of predictive
skill. Production eligibility remains governed by temporal OOS probability loss,
uncertainty and explicit feature manifests.
