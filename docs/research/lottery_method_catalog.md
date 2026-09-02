# Vietnamese Lottery Method Catalog

This catalog records publicly observable statistical concepts and VLA's independent mathematical interpretations. It is not evidence that lottery outcomes are predictable.

> **Historical patterns do not guarantee future lottery outcomes.**
>
> **Only temporal out-of-sample evidence may justify enabling an experimental feature in production.**

Where a public site exposes only behavior/UI rather than source code, VLA uses an **Independent implementation based on publicly observable behavior.** Marketing claims are never treated as predictive evidence.

## Frequency / tần suất lô tô

Aliases: tần suất, thống kê nhanh, số lần về

Sources:
- https://mketqua.net/thong-ke-tong-hop
- https://hainhay.net/
- https://xosodaiphat.com/xsdpthongke/xsdptktonghop
- https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html

Category: descriptive

Input: date-indexed two-digit draw results.

Mathematical definition: for number `x` and window `W`, occurrence frequency is the total count of `x` across all prize cells in `W`; draw frequency is the number of dates in `W` containing `x`; hit rate is draw frequency divided by eligible draw dates.

Parameters: lookback dates/window; occurrence-vs-draw counting mode.

Output: occurrence count, hit dates, hit rate, rolling frequency.

Edge cases: a number may occur more than once in one draw; occurrence count and draw count are therefore distinct.

Leakage risk: low when the window ends strictly before the prediction date; high if a full-history aggregate is reused in backtests.

Existing VLA equivalent: `advanced_stats.compute_frequency`, rolling features in `ml_features.py` / `cau_keo_ml.py`.

Implementation status: existing

Research confidence: high

Predictive evidence: untested as a standalone production signal

## Lô gan / current gap

Aliases: gan, lô khan, chưa về, số lượt chưa về

Sources:
- https://mketqua.net/loto-gan
- https://hainhay.net/
- https://xosodaiphat.com/xsdpthongke/xsdptktonghop
- https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html

Category: descriptive

Input: occurrence dates through an as-of date.

Mathematical definition: `gap(x,D)` is the number of completed eligible draws/calendar days since the latest occurrence of `x` strictly before target date `D`, under the declared calendar convention.

Parameters: as-of date, lookback, draw-days versus calendar-days convention.

Output: current gap, historical max/mean/median gap and related summaries.

Edge cases: never-seen number; missing dates; current right-censored interval.

Leakage risk: low with explicit as-of filtering.

Existing VLA equivalent: `advanced_stats.compute_overdue`, `cycle_stats._gap_series_calendar`, `number_dynamics._gap_hazard_current`.

Implementation status: existing

Research confidence: high

Predictive evidence: descriptive-only; a long gap must not be interpreted as "due" without OOS evidence.

## Cycle / chu kỳ / nhịp

Aliases: chu kỳ loto, chu kỳ ĐB, nhịp về

Sources:
- https://mketqua.net/soi-cau
- https://hainhay.net/
- https://rongbachkim.net/tools-soicau.html

Category: descriptive | pattern-mining

Input: ordered occurrence dates.

Mathematical definition: for hit dates `d1 < ... < dn`, recurrence intervals are `g_i = d_i - d_(i-1)` in the declared time unit. Summaries include mean, median, maximum and the current censored interval.

Parameters: lookback, time-unit convention.

Output: interval distribution, recent cycle, current gap.

Edge cases: fewer than two occurrences; missing calendar dates.

Leakage risk: low with an as-of cutoff.

Existing VLA equivalent: `advanced_stats.compute_cycle_stats`, `cycle_stats.py`, `descriptive_extensions.py`.

Implementation status: existing

Research confidence: high

Predictive evidence: descriptive-only unless separately validated.

## Head / tail / total / chạm

Aliases: đầu, đuôi, tổng, chạm

Sources:
- https://mketqua.net/dau-duoi-loto
- https://mketqua.net/thong-ke-theo-tong
- https://hainhay.net/
- https://xosodaiphat.com/xsdpthongke/xsdptktonghop

Category: descriptive

Input: normalized 00..99 values.

Mathematical definition: head=`floor(x/10)`, tail=`x mod 10`, total=`(head+tail) mod 10` where modulo-10 total is intended; chạm `d` is the set of two-digit numbers containing digit `d` in either position.

Parameters: lookback, occurrence/draw counting convention.

Output: grouped frequency/gap tables.

Edge cases: duplicated membership for doubles in chạm logic must be deduplicated.

Leakage risk: low.

Existing VLA equivalent: `number_reference.head/tail/digit_sum_mod10/dan_cham`, `advanced_stats.compute_head_tail_total`, `descriptive_extensions.py`.

Implementation status: existing

Research confidence: high

Predictive evidence: untested/research-only as challenger features.

## Reverse / lộn

Aliases: đảo, lộn

Sources:
- https://rongbachkim.net/tools-soicau.html
- https://hainhay.net/cau-hai-nhay

Category: descriptive | pattern-mining

Input: normalized two-digit number `AB`.

Mathematical definition: `reverse(AB)=BA`; doubles are fixed points.

Parameters: none.

Output: related number / pair.

Edge cases: doubles such as 00 and 99.

Leakage risk: none for the deterministic mapping.

Existing VLA equivalent: `number_reference.reverse`, `cap_lon`.

Implementation status: existing

Research confidence: high

Predictive evidence: untested as a standalone predictive signal.

## Cặp 50 / canonical partner partition

Aliases: cặp loto 50, cặp lộn plus kép-bóng pairs

Sources: terminology is reconstructed from VLA's existing tests/ontology and multiple public pair/cầu descriptions; public sites do not expose proprietary source code for the exact partition.

Category: descriptive | predictive-hypothesis

Input: normalized `00..99`.

Mathematical definition in VLA: non-doubles pair with reverse `AB↔BA`; doubles pair by bóng dương: `00↔55`, `11↔66`, `22↔77`, `33↔88`, `44↔99`. This yields exactly 50 disjoint pairs.

Parameters: none.

Output: partner, pair id, pair statistics.

Edge cases: doubles use bóng partner, not singleton reverse.

Leakage risk: none for mapping; medium for predictive aggregates if built with future data.

Existing VLA equivalent: `number_reference.cap_loto_50*`, `cap_loto_50_stats.py`.

Implementation status: existing; predictive group is validation-gated.

Research confidence: high for VLA definition, medium for external terminology equivalence.

Predictive evidence: inconclusive / must pass temporal challenger gate.

## Bộ

Aliases: bộ số, họ bộ

Sources: public terminology varies; VLA intentionally uses one documented canonical definition rather than guessing site-specific proprietary semantics.

Category: descriptive | predictive-hypothesis

Input: normalized `00..99`.

Mathematical definition in VLA: orbit generated by digit-wise bóng dương and reversal. The 100-number universe forms 15 unique families: ten 8-member families and five 4-member kép families.

Parameters: none.

Output: canonical family id/members.

Edge cases: bộ kép has four unique members.

Leakage risk: none for deterministic mapping.

Existing VLA equivalent: `number_reference.bo`, `bo_family_id`.

Implementation status: existing

Research confidence: high for VLA definition; medium when mapping ambiguous external labels.

Predictive evidence: inconclusive / challenger only.

## Bóng

Aliases: bóng dương, bóng âm

Sources: public usage is not perfectly standardized; VLA keeps documented mappings explicit.

Category: descriptive | predictive-hypothesis

Input: digits or two-digit number.

Mathematical definition in VLA: bóng dương digit pairs `0↔5,1↔6,2↔7,3↔8,4↔9`; documented bóng âm pairs `0↔7,1↔4,2↔9,3↔6,5↔8`, applied digit-wise.

Parameters: mapping convention.

Output: transformed number(s).

Edge cases: do not conflate bóng with mathematical 9-complement.

Leakage risk: none for mapping.

Existing VLA equivalent: `number_reference.bong_duong`, `bong_am`.

Implementation status: existing

Research confidence: high for VLA contract.

Predictive evidence: inconclusive / challenger only.

## Same-draw pair frequency / association

Aliases: cặp cùng về, max dàn cùng về

Sources:
- https://mketqua.net/soi-cau
- https://xosodaiphat.com/xsdpthongke/xsdptktonghop

Category: descriptive | pattern-mining

Input: per-date set of hit numbers.

Mathematical definition: co-occurrence count is the number of eligible dates containing both `i` and `j`; association support=`count(A∩B)/N`; confidence=`count(A∩B)/count(A)`; lift=`confidence/P(B)`.

Parameters: window, minimum support.

Output: counts, support, confidence, lift/correlation diagnostics.

Edge cases: sparse counts can create misleading high confidence; minimum support/shrinkage is required.

Leakage risk: medium if full-history association tables are reused in historical prediction rows.

Existing VLA equivalent: `pair_stats.py`, `number_dynamics` co-occurrence phi, research strategy diagnostics.

Implementation status: existing

Research confidence: high

Predictive evidence: research-only unless walk-forward validated.

## Conditional next-day matrix

Aliases: loto theo ĐB, loto theo loto, chuyển trạng thái

Sources:
- https://mketqua.net/soi-cau
- https://hainhay.net/

Category: pattern-mining | predictive-hypothesis

Input: exact consecutive calendar-day draw pairs.

Mathematical definition: `transition[i,j]=count(i_t and j_(t+1))`; `P(j_(t+1)|i_t)` divides by eligible source occurrences, optionally with empirical-Bayes/Dirichlet shrinkage. Lift compares the conditional probability to the marginal target probability.

Parameters: prior strength, source/target mode, lookback.

Output: counts, probabilities, support, effect, lift.

Edge cases: missing dates must not be treated as one-day transitions; small source counts require shrinkage.

Leakage risk: high if matrices are precomputed using observations later than a historical target date.

Existing VLA equivalent: `conditional_matrices.py`, `conditional_nextday.py`, `number_dynamics.transition_posterior`.

Implementation status: existing

Research confidence: high

Predictive evidence: research-only unless challenger validation says otherwise.

## Dynamic positional cầu / cầu chạy N ngày

Aliases: cầu loto, cầu ĐB, cầu ghép vị trí, cầu lộn, bạch thủ

Sources:
- https://rongbachkim.net/tools-soicau.html
- https://mketqua.net/soi-cau
- https://hainhay.net/

Category: pattern-mining

Input: structured prize digit positions from prior draws and a deterministic transformation.

Mathematical definition: a rule identifies semantic source position(s), calendar lag(s), transformation and target criterion; a running streak is the number of consecutive eligible target dates ending at the evaluation boundary for which the rule succeeds.

Parameters: source positions, lags, operator, minimum run length, target type.

Output: rule id, candidate payload, trials, hits, current/max streak, validation/holdout evidence.

Edge cases: layout offsets must not replace semantic prize identifiers; missing dates invalidate naive row-lag semantics.

Leakage risk: high because large pattern searches create severe selection bias.

Existing VLA equivalent: `crosslag_positional_lab.py`, `path_models.py`, `path_prob.py`, `research_firewall.py`, `cau_position_evidence.py`.

Implementation status: existing research foundation

Research confidence: high for the independently implemented concept; exact external proprietary rule search is unknown.

Predictive evidence: research-only; never automatically production eligible.

## Cầu 2 nháy

Aliases: hai nháy, lô 2 nháy

Sources:
- https://hainhay.net/cau-hai-nhay
- https://rongbachkim.net/tools-soicau.html and public `soicau-...nhay=2` pages

Category: pattern-mining

Input: positional rule candidate plus occurrence count of the resulting number in the target draw.

Mathematical definition in VLA interpretation: success for "2 nháy" is `occurrence_count(target_number, target_draw) >= 2`; this must be distinct from ordinary Loto hit `>=1`.

Parameters: rule, minimum streak, lộn handling.

Output: one-hit/two-hit evidence, exact target occurrence count, rule streak.

Edge cases: do not silently reduce two-nháy to ordinary presence.

Leakage risk: high in large positional searches.

Existing VLA equivalent: `advanced_stats.compute_daily_nhay_stats` provides descriptive nháy counts; positional research exists but a dedicated two-nháy promotion path is intentionally not production-wired.

Implementation status: existing descriptive support; research-only positional interpretation

Research confidence: medium because external search internals are proprietary.

Predictive evidence: untested / research-only.

## Markov / transition dynamics

Aliases: transition matrix, trạng thái

Sources: general statistical formalism; public lottery platforms expose conditional-history concepts but not necessarily a formal Markov implementation.

Category: predictive-hypothesis

Input: temporally ordered hit-state vectors.

Mathematical definition: first-order transitions use smoothed conditional probabilities; VLA additionally estimates per-number second-order state posteriors with shrinkage. A generic categorical form is `(count(i→j)+alpha)/(sum_k count(i→k)+alpha*|S|)`.

Parameters: prior strength / alpha, order, minimum history.

Output: transition probabilities, lift, reliability.

Edge cases: high-order 100-state models are data-starved and must be sample-size checked.

Leakage risk: high if fit on future observations.

Existing VLA equivalent: `markov_stats.py`, `number_dynamics.py`.

Implementation status: existing

Research confidence: high

Predictive evidence: statistical-signal component only; no claim that Markov alone predicts random draws.

## Pascal-style transformation

Aliases: cầu Pascal, bảng Pascal

Sources: public Vietnamese lottery-analysis articles commonly describe recursively adding adjacent digits and retaining modulo 10; exact proprietary ranking/scoring around the transform varies by site.

Category: pattern-mining | predictive-hypothesis

Input: an explicitly declared digit sequence, often derived from recent result fields.

Mathematical definition: for row `r`, next row is `r'[i]=(r[i]+r[i+1]) mod 10`; recurse until the configured output width. Any reverse/dàn expansion must be separately declared.

Parameters: source digit sequence, output width.

Output: deterministic reduced digit row / candidate code.

Edge cases: input length < output width; non-digit data; site-specific source sequence ambiguity.

Leakage risk: low for the deterministic transform when input predates target; high if source selection is tuned on target history.

Existing VLA equivalent: none identified as a canonical reusable API.

Implementation status: planned/research-only; no production integration in this tranche.

Research confidence: medium

Predictive evidence: untested.

## Fibonacci-style lottery rules

Aliases: Fibonacci soi cầu, Fibonacci gấp thếp

Sources: public search results mix mathematical Fibonacci definitions with betting-stake progressions and loosely specified numerology.

Category: predictive-hypothesis

Input: ambiguous in public lottery descriptions.

Mathematical definition: canonical sequence is `F0=0`, `F1=1`, `Fn=F(n-1)+F(n-2)`, but no sufficiently consistent public mapping from XSMB history to predicted numbers was identified in this research pass.

Parameters: unknown/site-specific.

Output: not defined reliably enough for independent predictive implementation.

Edge cases: high risk of inventing a rule that a source never specified.

Leakage risk: unknown.

Existing VLA equivalent: none required.

Implementation status: rejected for implementation pending a reproducible public definition.

Research confidence: low for lottery mapping; high for the mathematical sequence itself.

Predictive evidence: untested.

## Candidate composite score / "chỉ số nổ"

Aliases: điểm tổng hợp, score, chỉ số

Sources: many public platforms rank or visually emphasize numbers but exact proprietary score formulas are generally unavailable.

Category: descriptive | predictive-hypothesis

Input: normalized component evidence such as frequency, gap, EMA, cycle, conditional and pattern features.

Mathematical definition: a configurable weighted score may combine normalized components; it is **not a probability** unless separately calibrated as such.

Parameters: component definitions and weights.

Output: rank/score plus evidence provenance.

Edge cases: missing components; incomparable scales; hand-tuned weights can overfit.

Leakage risk: medium/high when weights or normalizers use future history.

Existing VLA equivalent: explainability/ranking layers in `cau_keo_ml.py`, `statistics_ai_overlay.py`, `statistical_signal.py`.

Implementation status: existing, with scores explicitly separated from calibrated model probabilities.

Research confidence: high for the distinction between score and probability.

Predictive evidence: component-dependent; production probability requires temporal calibration/OOS validation.
