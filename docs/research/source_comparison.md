# Public Source Comparison

This matrix compares publicly observable functionality, not proprietary implementations. Exact private algorithms are not claimed or copied.

| Method | Public aliases / observed sources | VLA implementation | Mathematical basis | Key parameters | Descriptive value | Leakage / selection risk | Predictive status |
|---|---|---|---|---|---|---|---|
| Frequency | Tần suất loto; mketqua, hainhay, xosodaiphat, Minh Ngọc | `advanced_stats.compute_frequency`, rolling ML features | counts / dates-hit / hit rate | window, count mode | High | Low if as-of safe | descriptive; feature only |
| Lô gan | Gan, lô khan, chưa về | `advanced_stats.compute_overdue`, `cycle_stats.py` | time since latest prior hit | as-of date, calendar convention | High | Low | descriptive-only |
| Cycle | Chu kỳ, nhịp | `advanced_stats.compute_cycle_stats`, `cycle_stats.py` | intervals between occurrence dates | window/time unit | High | Low | descriptive-only |
| Head/tail | Đầu/đuôi | `number_reference`, `advanced_stats.compute_head_tail_total` | digit grouping | window | High | Low | descriptive |
| Total | Tổng | `number_reference.digit_sum_mod10`, grouped stats | digit sum modulo 10 | window | High | Low | descriptive/challenger |
| Chạm | Chạm | `number_reference.dan_cham`, descriptive extensions | digit membership set | digit/window | High | Low | descriptive/challenger |
| Reverse | Lộn/đảo | `number_reference.reverse` | AB→BA | none | High | None | challenger hypothesis only |
| Cặp 50 | Cặp loto | `number_reference.cap_loto_50*`, `cap_loto_50_stats.py` | 50 disjoint partner pairs under VLA contract | none/window | High | Medium if backtest aggregate is future-fit | challenger only |
| Same-draw pair | Cặp cùng về | `pair_stats.py`, co-occurrence in `number_dynamics.py` | support/confidence/lift/correlation | window/min support | High | Medium | research-only |
| Dynamic positional cầu | Soi cầu, ma trận cầu; Rồng Bạch Kim, mketqua, hainhay | `crosslag_positional_lab.py`, `path_*`, `research_firewall.py` | semantic digit positions + deterministic operator + consecutive success | positions, lag, operator, run length | Medium/high for explanation | **Very high** multiplicity risk | research-only |
| Cầu lộn | Lộn / không lộn | `crosslag_positional_lab` operator `lon` | AB and BA candidate set | source positions/lags | Medium | Very high when mined | research-only |
| Cầu 2 nháy | Hai nháy | descriptive nháy stats + positional research | target occurrence count >=2 | positions/lags/run | Medium | Very high | research-only |
| Special-prize cầu | Cầu giải ĐB | path/research modules | positional transform to one categorical Đề outcome | positions/lags | Medium | Very high | research-only |
| Conditional matrix | Loto theo ĐB/loto | `conditional_matrices.py`, `conditional_nextday.py` | P(B at t+1 | A at t), support/lift | prior strength/window | High | High if full-history matrix reused | research/statistical signal |
| Association rules | Cùng về / relation mining | pair/co-occurrence and research modules | support/confidence/lift | min support/confidence/lift | High | High multiplicity | research-only |
| Markov | Transition/state | `markov_stats.py`, `number_dynamics.py` | smoothed transition posterior | alpha/prior/order | Medium | High if future-fit | research/statistical signal |
| Pascal | Cầu Pascal | no canonical VLA API in this tranche | adjacent modulo-10 recursive reduction | source digits/output width | Medium as deterministic transform | Medium/high source-selection bias | untested/research-only |
| Fibonacci | Fibonacci/gấp thếp | intentionally not implemented | Fibonacci recurrence itself is known; lottery mapping ambiguous | unknown | Low | High conceptual risk | rejected pending precise definition |
| Candidate score | Chỉ số/điểm tổng hợp | `cau_keo_ml`, `statistics_ai_overlay`, `statistical_signal` | weighted normalized evidence | weights/components | Useful ranking/explanation | Medium/high tuning risk | score != probability |

## Source notes

### mketqua.net

Public pages expose broad groups including cầu Loto/ĐB/bạch thủ/hai-nháy and descriptive statistics such as tần suất, gan, chu kỳ, cặp, đầu/đuôi/tổng. VLA treats these page labels as terminology/functionality observations only.

Relevant public pages:
- https://mketqua.net/soi-cau
- https://mketqua.net/loto-gan
- https://mketqua.net/thong-ke-theo-tong
- https://mketqua.net/dau-duoi-loto
- https://mketqua.net/thong-ke-tong-hop

### hainhay.net

Public pages expose frequency/gan/cycle-style summaries plus cầu Loto, bạch thủ and hai-nháy views. Exact rule-search/ranking internals are not public.

Relevant public pages:
- https://hainhay.net/
- https://hainhay.net/cau-hai-nhay

### rongbachkim.net

Public soi-cầu pages visibly expose digit-position pairs, selectable cầu length, lộn/non-lộn behavior and two-nháy modes. VLA's positional implementation is independent and uses semantic prize-position identifiers rather than attempting to reproduce private layout offsets or source code.

Relevant public pages:
- https://rongbachkim.net/tools-soicau.html
- public `soicau-...` result pages linked by that tool

### xosodaiphat.com

Public tổng hợp statistics include number occurrence counts, gan/last-seen style values, same-draw pair information and head/tail summaries.

Relevant public page:
- https://xosodaiphat.com/xsdpthongke/xsdptktonghop

### minhngoc.net.vn

Public statistics include gan cực đại / lookup by lô, đầu-đuôi or special-prize context and frequency views.

Relevant public page:
- https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html

## Interpretation rule

A method being present on multiple public lottery-analysis websites raises confidence that the **terminology/statistical transformation is common**. It does not raise confidence that it predicts future random draws.

For externally observed rule systems whose code is unavailable, VLA records:

> **Independent implementation based on publicly observable behavior.**
