# Public-source comparison

Reviewed 2026-09-02 using public pages only. No authentication, CAPTCHA,
private API, or proprietary source was accessed. Page labels and controls show
what a service exposes; they do not reveal every ranking rule. Every VLA
reconstruction below is an **Independent implementation based on publicly
observable behavior.**

## Site-level observations

| Site | Publicly observed functionality | Behavior that can be inferred | Ambiguity / confidence |
| --- | --- | --- | --- |
| [mketqua.net](https://mketqua.net/) | Frequency, pair frequency, cycle, gan, head/tail, conditional tables, lô rơi, Loto/special/bạch-thủ/two-nháy cầu | Date/window controls; occurrence tables; configurable running-cầu boundary/run length; displayed source positions and streak counts | Descriptive counts: high. Exact pattern enumeration/ranking: medium/low. |
| [hainhay.net](https://hainhay.net/) | Cycle, frequency, pair frequency, gan, head/tail, conditional stats, Loto/two-nháy/bạch-thủ/special cầu | Cycle pages expose maximum interval, historical dates, and current draw distance; navigation distinguishes target families | Cycle interpretation: high. Proprietary cầu selection: low. |
| [rongbachkim.net](https://rongbachkim.net/thongke.html) | 00..99 history grid, per-day multiplicity, special marker, cycle/gan drill-down | Legend explicitly separates no hit, one, two, three, and four occurrences; configurable date window | Multiplicity semantics: high. Internal sort/scoring: low. |
| [xosodaiphat.com](https://xosodaiphat.com/) | Gan, same-draw pairs, doubles, head/tail, special, frequency, pair frequency, occurrence and cycle | Same-draw tool accepts chosen numbers/period and returns qualifying dates; pair-frequency page publishes the 50-pair layout | Descriptive relations: high. Predictive interpretation: unsupported. |
| [minhngoc.net.vn](https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html) | Loto lookup, maximum gan, frequency by region/province and target type | Public form accepts 2–4 digit query, draw count/date context, Loto/head-tail/special modes; maximum absent-draw interval is displayed | Query behavior: high. Aggregation details across multi-province schedules: medium. |
| [Cầu Lô 100 Pascal page](https://caulo100.com/soi-cau-pascal-cau-lo-100) | Pascal-labelled digit triangle and candidate display | Each next row is publicly described as adjacent sums with units-digit reduction | Recurrence: medium/high. Seed and candidate-selection mapping: low. Displayed confidence is not calibrated evidence. |

## Method comparison matrix

| Method | External aliases | VLA implementation | Mathematical basis | Main parameters | Descriptive value | Leakage risk | Predictive status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lô gan | gan, lô khan | `gap_cycle_stats.compute_gap_stats` | Completed draws since last hit, strict before target | as-of, lookback | Recency/censoring | Medium | Descriptive only; “due” claim rejected |
| Frequency | tần suất, số lần về | `frequency_stats.compute_frequency_stats` | Occurrence sum and draw-presence sum | calendar/draw lookback | High | Medium | Untested |
| Pair frequency | cặp cùng về, lô xiên history | `pair_stats`, `build_cooccurrence_matrix` | Same-draw joint count/support/lift | window, support | High | Medium | Untested |
| Cycle | chu kỳ, nhịp | `gap_cycle_stats` | Hit-to-hit draw/calendar intervals | lookback, recent intervals | High | Low | Untested |
| Head/tail | đầu/đuôi | `number_reference`, `frequency_stats` | Tens/units digit groups | group/window | High | Low | Untested |
| Total | tổng, tổng đề | `digit_sum`, `digit_sum_mod10` | `a+b` or `(a+b) mod 10`, named explicitly | raw/mod-10 | High | Low | Untested |
| Chạm | chạm đầu/đuôi | `dan_cham`, group stats | `a=d or b=d` | digit/window | High | Low | Untested |
| Reverse | lộn, đảo | `number_reference.reverse` | `AB↔BA` | none | High | None | Deterministic only |
| Cặp 50 | cặp loto, kép-bóng | `number_reference.cap_loto_50` | 45 reverse pairs + 5 double-shadow pairs | none | High | None | Challenger relation only |
| Bộ/bóng | bộ, hệ, bóng dương/âm | `number_reference` | Documented digit maps and generated orbit | convention | Medium/high | Medium if selected | Challenger relation only |
| Dynamic positional cầu | cầu chạy, ghép vị trí | `dynamic_cau.find_running_patterns` | Lag-one semantic digits + deterministic transform + streak | positions, run, support, target | Pattern discovery | High | Research only, untested |
| Cầu lộn | reverse-pair cầu | `dynamic_cau` `reverse_pair` | Candidate set `{AB,BA}` | positions/run | Pattern discovery | High | Research only, untested |
| Cầu 2 nháy | hai nháy | `dynamic_cau` `loto_2_nhay` | Any individually predicted number occurs at least twice | positions/run/support | Multiplicity-aware | High | Research only, untested |
| Special-prize cầu | cầu đề, cầu ĐB | `dynamic_cau` `special` | Candidate contains next special suffix | positions/run | Pattern discovery | High | Research only, untested |
| Conditional matrix | loto theo loto/ĐB | `conditional_matrices`, `conditional_nextday` | Exact-calendar joint/source counts and smoothed conditional rates | alpha, cutoff | High | High | Inconclusive/research only |
| Association rules | A→B | `association_rules.mine_association_rules` | support, confidence, lift, Wilson lower bound | thresholds, lag | High | High | Untested |
| Markov | transition model | `markov_stats.build_markov_chain` | Additively smoothed first-order transitions | alpha, states | Medium | High | Inconclusive/research only |
| Candidate score | chỉ số nổ, điểm | `candidate_scoring.rank_candidates` | Explicit weighted normalized components | weights, EMA, lookback | Explanation/ranking | Medium | Untested; never labeled probability |
| Pascal | tam giác Pascal | None | Public adjacent-sum modulo-10 recurrence; mapping underspecified | seed/depth/extraction | Transformation only | High | Rejected pending reproducible mapping |
| Fibonacci | cầu Fibonacci | None | Fibonacci recurrence; lottery mapping not found | unspecified | None yet | High | Rejected as underspecified |
| Graph | number network | None; matrix foundation exists | Weighted graph summaries | edge/threshold | Potentially descriptive | High | Planned research only |

## Evidence boundaries

- The sites consistently expose historical statistics and pattern-search tools.
  That establishes terminology and observable transformations, not future skill.
- Exact proprietary enumeration, pruning, ranking, or “confidence” formulas
  cannot be recovered from public output and are not fabricated here.
- VLA's canonical cặp-50 layout matches the public 50-pair table observed at
  Xổ Số Đại Phát, including the five double-shadow pairs.
- Public Pascal pages were mutually similar, but similarity does not establish
  independence or a validated forecast. VLA records only the visible recurrence.
- No sufficiently precise public Fibonacci-to-lottery mapping survived the
  documentation threshold, so no implementation was added.
