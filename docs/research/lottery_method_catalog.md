# Vietnamese lottery method catalog

Last verified: 2026-09-02

This catalog records public behavior, not proprietary implementation details.
Unless stated otherwise, each VLA equivalent is an **Independent implementation
based on publicly observable behavior.** Marketing statements are not validation
evidence. Historical patterns do not guarantee future lottery outcomes.

## Frequency

Aliases: tần suất loto, số lần về, frequency

Sources: https://mketqua.net/tan-suat-loto; https://xosodaiphat.com/thong-ke-tan-suat-loto.html; https://www.minhngoc.net.vn/thong-ke-xo-so/tan-suat-tinh.html

Category: descriptive

Input: date-indexed occurrence counts for 00..99

Mathematical definition: occurrence count is `sum_t count_t(x)`; draw count is `sum_t 1[count_t(x)>0]`; draw hit rate is draw count divided by eligible draws.

Parameters: calendar or draw-count lookback; as-of date

Output: occurrence/draw counts, hit rate, maximum multiplicity, exact-two and at-least-two counts

Edge cases: empty windows, duplicate dates, missing number columns, repeated occurrences in one draw

Leakage risk: medium if the target date enters the window; VLA uses dates strictly before the as-of date

Existing VLA equivalent: `frequency_stats.compute_frequency_stats`; `advanced_stats.compute_frequency` is a compatibility facade

Implementation status: implemented

Research confidence: high

Predictive evidence: untested

## Lô gan / gap

Aliases: gan, lô khan, overdue

Sources: https://mketqua.net/loto-gan; https://rongbachkim.net/thongke.html; https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html

Category: descriptive

Input: date-indexed draw presence for 00..99

Mathematical definition: `gap(x,D)` is the completed eligible draws after the most recent hit and strictly before target date `D`; calendar absence is reported separately as `(D-last_hit).days-1`.

Parameters: as-of date; optional calendar/draw lookback

Output: current draw/calendar gap, last hit, historical gaps, percentile, z-score

Edge cases: never seen, one hit, zero variance, missing calendar dates

Leakage risk: medium if the target result is included

Existing VLA equivalent: `gap_cycle_stats.compute_gap_stats`; legacy `cycle_stats._gap_series_calendar`

Implementation status: implemented

Research confidence: high

Predictive evidence: rejected as an automatic “due number” rule; a long gap does not itself raise future probability

## Cycle / recurrence

Aliases: chu kỳ, nhịp, recurrence interval

Sources: https://hainhay.net/chu-ky; https://xosodaiphat.com/thong-ke-chu-ky-loto.html

Category: descriptive

Input: ordered hit dates and draw indices

Mathematical definition: for hit indices `i_1,...,i_n`, recurrence is `g_k=i_k-i_(k-1)` and completed absence is `g_k-1`; calendar recurrence uses date differences.

Parameters: lookback and recent-trend interval count

Output: intervals, mean, median, variance, quartiles, maximum, recent slope, current right-censored interval

Edge cases: fewer than two hits; irregular calendars; current censoring is not a completed interval

Leakage risk: low with a strict as-of boundary

Existing VLA equivalent: `gap_cycle_stats.compute_recurrence_intervals`, `compute_gap_stats`; legacy `cycle_stats.build_cycle_tables`

Implementation status: implemented

Research confidence: high

Predictive evidence: untested

## Head / tail / total / chạm

Aliases: đầu, đuôi, tổng, tổng modulo 10, chạm

Sources: https://mketqua.net/; https://xosodaiphat.com/; https://hainhay.net/chu-ky-db

Category: descriptive

Input: a two-digit number `10a+b` or historical occurrence counts

Mathematical definition: head=`a`; tail=`b`; digit sum=`a+b`; total-mod-10=`(a+b) mod 10`; chạm `d` contains numbers where `a=d or b=d`.

Parameters: group kind and historical window

Output: membership, occurrence/draw counts, hit rate, group gap

Edge cases: `00`, `99`; chạm has 19 unique members; raw sum 0..18 differs from modulo-10 total

Leakage risk: low with a strict cutoff

Existing VLA equivalent: `number_reference` group functions; `frequency_stats.compute_group_frequency_stats`; `gap_cycle_stats.compute_group_gap_stats`

Implementation status: existing

Research confidence: high

Predictive evidence: untested

## Same-draw pair frequency

Aliases: cặp cùng về, pair co-occurrence

Sources: https://xosodaiphat.com/thong-ke-lo-xien.html; https://mketqua.net/tan-suat-cap-loto

Category: descriptive

Input: unique Loto-number set for each draw

Mathematical definition: `cooccur(i,j)=sum_t 1[i in draw_t and j in draw_t]`; support=`cooccur/eligible_draws`.

Parameters: lookback, minimum support, top-N

Output: raw co-occurrence, support, marginal counts, lift, recent dates

Edge cases: one-number multiplicity is not pair co-occurrence; unordered pairs exclude `i=j`

Leakage risk: high if a full-history table is reused in historical backtests

Existing VLA equivalent: `pair_stats.compute_pair_frequency`, `descriptive_extensions.build_pair_recency`, `conditional_matrices.build_cooccurrence_matrix`

Implementation status: existing

Research confidence: high

Predictive evidence: untested

## Reverse / lộn and cặp loto 50

Aliases: đảo, lộn, AB-BA, cặp 50, kép-bóng

Sources: https://xosodaiphat.com/thong-ke-tan-suat-loto-cap.html; `docs/number-ontology-sources.md`

Category: descriptive

Input: one two-digit number

Mathematical definition: reverse maps `AB→BA`. The 50-pair partition contains 45 non-double reverse pairs plus `00-55`, `11-66`, `22-77`, `33-88`, `44-99`.

Parameters: none

Output: reverse, pair id, pair type

Edge cases: double numbers are reverse singletons and use their bóng-dương double in cặp 50

Leakage risk: none for the deterministic mapping

Existing VLA equivalent: `number_reference.reverse`, `cap_loto_50_partner`, `all_cap_loto_50`; `cap_loto_50_stats.build_stats`

Implementation status: existing

Research confidence: high

Predictive evidence: rejected as automatic predictive evidence; relation features remain challengers

## Bộ and bóng

Aliases: bộ/hệ, bóng dương, bóng âm

Sources: multiple public descriptions cross-checked in `docs/number-ontology-sources.md`

Category: descriptive

Input: digit or two-digit number

Mathematical definition: bóng dương pairs are `0↔5,1↔6,2↔7,3↔8,4↔9`; VLA bộ is the orbit generated by digit-wise bóng dương and reversal, producing ten size-8 and five size-4 families.

Parameters: declared mapping convention

Output: transformations, family id and members

Edge cases: terminology varies; complement-to-nine is deliberately not called bóng in VLA

Leakage risk: none for mapping; medium if families are selected on target-period results

Existing VLA equivalent: `number_reference.bo`, `bong_duong`, `bong_am`

Implementation status: existing

Research confidence: medium for terminology, high for the documented VLA rule

Predictive evidence: rejected as automatic predictive evidence

## Dynamic positional cầu

Aliases: cầu loto chạy N ngày, cầu ghép vị trí, bạch thủ, cầu đặc biệt

Sources: https://mketqua.net/cau-loto; https://mketqua.net/cau-bach-thu; https://hainhay.net/cau-loto

Category: pattern-mining

Input: semantic prize/result/digit positions from draw `t-1` and targets at `t`

Mathematical definition: select source digits and apply concatenation, reverse concatenation, reverse pair, or bộ. Active run is the latest consecutive-calendar sequence satisfying the target criterion.

Parameters: positions, transformations, target, minimum run/support, hypothesis cap

Output: pattern id, next candidate set, active/longest run, support, successes/failures, confidence, coverage, recent success dates, search counts

Edge cases: missing calendar dates break runs; duplicates fail; one perfect observation is weak evidence

Leakage risk: high; same-period selection/reporting triggers `PATTERN_SELECTION_BIAS_RISK`

Existing VLA equivalent: `dynamic_cau.find_running_patterns`; specialized predecessor `crosslag_positional_lab.evaluate_lab`

Implementation status: implemented

Research confidence: medium because exact site enumeration/ranking is proprietary

Predictive evidence: untested

## Cầu 2 nháy

Aliases: cầu ăn hai nháy, two-hit Loto

Sources: https://mketqua.net/cau-hai-nhay; https://hainhay.net/cau-loto-2-nhay; https://rongbachkim.net/thongke.html

Category: predictive-hypothesis

Input: positional candidates and per-number target-draw multiplicity

Mathematical definition: VLA uses `max_x count_t(x)>=2` for an individually predicted `x`; counts from different candidates are not pooled. At-least-one, at-least-two, and exact counts are separate.

Parameters: rule, run length, minimum support

Output: ordinary/two-nháy successes and exact-count histogram

Edge cases: exactly two differs from at least two; two one-hit candidates do not form one two-nháy hit

Leakage risk: high during pattern search

Existing VLA equivalent: `dynamic_cau.evaluate_pattern(target_type="loto_2_nhay")`; descriptive `advanced_stats.compute_daily_nhay_stats`

Implementation status: implemented

Research confidence: medium; public labels are clear but selection logic is unknown

Predictive evidence: untested

## Special-prize positional cầu

Aliases: cầu đề, cầu giải đặc biệt, bạch thủ đề

Sources: https://mketqua.net/cau-giai-dac-biet; https://hainhay.net/cau-dac-biet

Category: predictive-hypothesis

Input: prior semantic digit positions and next special-prize two-digit suffix

Mathematical definition: positional transformation with success `1[predicted set contains special_t mod 100]`.

Parameters: positions, transform, run/support thresholds

Output: pattern evidence and deterministic next candidate set

Edge cases: full special prize and its two-digit suffix are distinct targets

Leakage risk: high

Existing VLA equivalent: `dynamic_cau.evaluate_pattern(target_type="special")`; research-only `crosslag_positional_lab`

Implementation status: implemented

Research confidence: medium

Predictive evidence: untested

## Conditional and transition matrices

Aliases: loto theo loto, loto theo đặc biệt, next-day matrix

Sources: https://mketqua.net/; https://hainhay.net/chu-ky

Category: pattern-mining

Input: date-indexed source and exact-next-calendar-day target presence

Mathematical definition: `count(i,j)=sum_t 1[i_t and j_(t+1)]`; confidence=`count/source_count`; support=`count/N`; lift=`confidence/P(j)`; multi-label Beta smoothing=`(count+alpha)/(source_count+2alpha)`.

Parameters: strict as-of date, smoothing alpha

Output: raw counts, marginal support, confidence, smoothed rate, lift

Edge cases: missing dates are skipped; multi-label Loto rows need not sum to one

Leakage risk: high if fitted with future transitions

Existing VLA equivalent: `conditional_matrices.build_transition_matrix`, `conditional_nextday`, `number_dynamics.transition_posterior`

Implementation status: implemented

Research confidence: high

Predictive evidence: inconclusive; research/challenger only

## Association rules

Aliases: A→B, conditional pair rule

Sources: standard statistical formalism applied independently to public pair/conditional features

Category: pattern-mining

Input: same-draw or exact-next-day presence sets

Mathematical definition: support=`count(A and B)/N`; confidence=`count(A and B)/count(A)`; lift=`confidence/P(B)`.

Parameters: lag 0/1, minimum support/confidence/lift and antecedent observations, alpha

Output: raw counts and metrics plus Wilson lower confidence bound

Edge cases: zero/rare antecedents, perfect tiny samples, directed versus unordered semantics

Leakage risk: high when selection and evaluation share one period

Existing VLA equivalent: `association_rules.mine_association_rules`

Implementation status: implemented

Research confidence: high for mathematics

Predictive evidence: untested

## First-order Markov chain

Aliases: Markov transition

Sources: standard statistical definition; no proprietary site model is claimed

Category: predictive-hypothesis

Input: ordered exclusive states

Mathematical definition: `P_ij=(count(i→j)+alpha)/(sum_k count(i→k)+alpha|S|)`.

Parameters: state space and alpha

Output: counts, outgoing support, row-normalized probabilities

Edge cases: unseen states; alpha zero; multi-label Loto needs Bernoulli conditionals instead

Leakage risk: high if test dates enter the matrix

Existing VLA equivalent: `markov_stats.build_markov_chain`; same-number `compute_markov_for_loto`; limited second-order research in `number_dynamics`

Implementation status: implemented

Research confidence: high for mathematics

Predictive evidence: inconclusive; must beat marginal/rolling baselines OOS

## Candidate scoring / chỉ số nổ

Aliases: score, điểm tổng hợp, chỉ số nổ

Sources: generic reconstruction from common public multi-indicator displays; no proprietary formula claimed

Category: predictive-hypothesis

Input: strict-history frequency, gap, recency, EMA, cycle, optional conditional/pattern scores

Mathematical definition: normalized weighted mean. EMA uses `alpha=2/(span+1)` and `EMA_t=alpha*y_t+(1-alpha)*EMA_(t-1)`.

Parameters: lookback, EMA span/initialization/minimum history, explicit weights

Output: `CandidateScore` containing score, components, evidence, explanation, provenance

Edge cases: missing optional components are disclosed/excluded; insufficient history yields zero

Leakage risk: medium; every input must respect as-of date

Existing VLA equivalent: `candidate_scoring.rank_candidates`; production `cau_keo_ml._add_ai_judgement` remains separate

Implementation status: implemented

Research confidence: high for VLA formula, low for external equivalence

Predictive evidence: untested; score is not a calibrated probability

## Pascal-style transformation

Aliases: cầu Pascal, tam giác Pascal xổ số

Sources: https://caulo100.com/soi-cau-pascal-cau-lo-100; https://soicauvn247.com/soi-cau-pascal

Category: predictive-hypothesis

Input: an externally chosen seed digit sequence

Mathematical definition: public pages describe `r_(k+1,j)=(r_(k,j)+r_(k,j+1)) mod 10`; seed choice and candidate extraction are insufficiently specified.

Parameters: seed, depth, candidate-extraction rule

Output: deterministic triangle; ranking needs a separately specified mapping

Edge cases: displayed marketing confidence has no public calibration method and is not evidence

Leakage risk: high if seed/extraction is chosen after outcomes

Existing VLA equivalent: none

Implementation status: rejected

Research confidence: medium for recurrence, low for extraction

Predictive evidence: rejected pending a reproducible mapping

## Fibonacci-style transformation

Aliases: cầu Fibonacci

Sources: no stable, sufficiently detailed public Vietnamese lottery mapping identified in this pass

Category: predictive-hypothesis

Input: unspecified lottery history and Fibonacci sequence

Mathematical definition: only `F_0=0`, `F_1=1`, `F_n=F_(n-1)+F_(n-2)` is unambiguous; no reproducible history-to-candidate mapping was found.

Parameters: unspecified

Output: unspecified

Edge cases: inventing a mapping would fabricate an external method

Leakage risk: high if rules are retrospectively selected

Existing VLA equivalent: none

Implementation status: rejected

Research confidence: low

Predictive evidence: rejected as underspecified

## Graph analytics

Aliases: number graph, co-occurrence network

Sources: standard graph summaries applied to the matrices above; no proprietary-site equivalence claimed

Category: pattern-mining

Input: co-occurrence, transition, or lift matrix

Mathematical definition: nodes are 00..99; declared weighted edges feed weighted degree, PageRank, community, or centrality algorithms.

Parameters: edge metric/threshold/direction and graph algorithm

Output: descriptive node/edge summaries

Edge cases: dense background edges and threshold sensitivity

Leakage risk: high if full-future graphs create historical features

Existing VLA equivalent: none; canonical matrix inputs exist

Implementation status: planned

Research confidence: high for graph mathematics, low for predictive relevance

Predictive evidence: untested
