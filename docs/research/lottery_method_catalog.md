# Vietnamese Lottery Method Catalog

Last verified: 2026-09-02

This catalog records public lottery-analysis concepts, not claims of predictability.
Where a site's proprietary implementation is not public, VLA uses an **Independent
implementation based on publicly observable behavior.** Marketing claims are never
accepted as predictive evidence.

> Historical patterns do not guarantee future lottery outcomes.
>
> Only temporal out-of-sample evidence may justify enabling an experimental
> feature in production.

## Frequency / tần suất lô

Aliases: tần suất loto, lần xuất hiện, frequency

Sources:
- https://www.minhngoc.net.vn/thong-ke-xo-so/tan-suat-mien.html
- https://mketqua.net/thong-ke-theo-tong
- https://xosodaiphat.com/

Category: descriptive

Input: date-indexed draws and the 00..99 two-digit occurrences.

Mathematical definition:
- occurrence_count(x, W) = total number of occurrences of x in window W;
- draw_count(x, W) = number of dates in W with at least one occurrence of x;
- draw_hit_rate = draw_count / eligible_draws.

Parameters: lookback window, occurrence-vs-date counting contract, mode.

Output: counts, hit dates/rates, rolling-window summaries.

Edge cases: repeated occurrences within one draw must not be confused with one hit date.

Leakage risk: low if the window ends before the target draw; high if a full-history table is reused in a historical backtest.

Existing VLA equivalent: `advanced_stats.compute_frequency`, rolling features in `cau_keo_ml.py` and `ml_features.py`.

Implementation status: existing

Research confidence: high

Predictive evidence: untested as a standalone rule; frequency features remain subject to ML OOS evaluation.

## Lô gan / gap / overdue

Aliases: gan, lô gan, số lượt quay chưa về, days since last hit

Sources:
- https://www.minhngoc.net.vn/thong-ke-xo-so/tan-suat-mien.html
- https://mketqua.net/thong-ke-theo-tong
- https://hainhay.net/chu-ky-db

Category: descriptive

Input: ordered hit dates for each number/group.

Mathematical definition for target date D:
`gap(x,D) = number of completed eligible draws/calendar days since the most recent occurrence strictly before D`, with the unit explicitly recorded.

Parameters: calendar-day versus draw-count unit, lookback window.

Output: current gap, historical max/mean/median, optional empirical percentile.

Edge cases: never-seen numbers; missing dates; current right-censored interval.

Leakage risk: low with an as-of cutoff; high if current/future hit is included.

Existing VLA equivalent: `cycle_stats.py`, `advanced_stats.compute_overdue`, `advanced_stats.compute_cycle_stats`, `number_dynamics._gap_hazard_current`.

Implementation status: existing

Research confidence: high

Predictive evidence: descriptive-only unless a leakage-safe challenger proves otherwise. A long gap is not evidence that a number is "due".

## Cycle / recurrence / chu kỳ

Aliases: chu kỳ loto, chu kỳ ĐB, nhịp

Sources:
- https://hainhay.net/chu-ky-db
- https://xosodaiphat.com/

Category: descriptive

Input: occurrence dates d1 < d2 < ... < dn.

Mathematical definition: completed recurrence intervals `g_i = d_i - d_(i-1)`; report mean, median, variance/quantiles, max, recent intervals, and current censoring interval separately.

Parameters: unit and lookback window.

Output: interval distribution and current censored gap.

Edge cases: one/no occurrences and missing calendar dates.

Leakage risk: low with an explicit as-of date.

Existing VLA equivalent: `cycle_stats.py`, `advanced_stats.compute_cycle_stats`.

Implementation status: existing

Research confidence: high

Predictive evidence: descriptive-only.

## Head / tail / total / chạm

Aliases: đầu, đuôi, tổng, chạm đề/loto

Sources:
- https://www.minhngoc.net.vn/thong-ke-xo-so/tan-suat-mien.html
- https://mketqua.net/thong-ke-theo-tong
- https://hainhay.net/chu-ky-db
- https://xosodaiphat.com/

Category: descriptive / predictive-hypothesis when used as a challenger

Input: normalized two-digit number AB.

Mathematical definition:
- head = A;
- tail = B;
- total_mod10 = (A+B) mod 10;
- chạm d = numbers where A=d or B=d.

Parameters: window/mode.

Output: group frequency/gap, or candidate features.

Edge cases: total may be reported as raw digit sum or modulo-10 by different sites; VLA names modulo-10 explicitly.

Leakage risk: none for deterministic mapping; temporal aggregates require as-of cutoff.

Existing VLA equivalent: `number_reference.py`, `advanced_stats.py`, `descriptive_extensions.py`, domain challenger feature groups.

Implementation status: existing

Research confidence: high for definitions, medium for site-specific display conventions.

Predictive evidence: challenger only; production requires OOS gate.

## Reverse / lộn partner

Aliases: lộn, đảo, reverse pair

Sources:
- public cầu interfaces including https://rongbachkim.net/
- existing VLA ontology cross-checked against public terminology.

Category: descriptive / predictive-hypothesis

Input: AB.

Mathematical definition: reverse(AB)=BA.

Parameters: none.

Output: deterministic partner, pair evidence/features.

Edge cases: doubles AA reverse to themselves.

Leakage risk: none for mapping.

Existing VLA equivalent: `number_reference.reverse`, baseline reverse features, challenger `partner` family.

Implementation status: existing

Research confidence: high

Predictive evidence: challenger; not assumed predictive.

## Cặp 50

Aliases: 50 cặp loto, cặp lộn + kép bóng

Sources: public Vietnamese lottery terminology plus VLA's documented ontology; exact site naming varies.

Category: descriptive / predictive-hypothesis

Input: 00..99.

Mathematical definition used by VLA: 45 non-double reverse pairs plus five kép-bóng pairs `00-55, 11-66, 22-77, 33-88, 44-99`, producing an exact partition of the 100-number universe.

Parameters: none.

Output: pair id/kind, pair frequency/balance/gap evidence.

Edge cases: must not be conflated with arbitrary same-draw co-occurrence pairs.

Leakage risk: none for mapping; historical pair aggregates require cutoff.

Existing VLA equivalent: `number_reference.cap_loto_50*`, `cap_loto_50_stats.py`, challenger `cap_50` family.

Implementation status: existing

Research confidence: high inside the documented VLA convention.

Predictive evidence: challenger only.

## Bộ / bóng

Aliases: bộ số, bóng dương, bóng âm

Sources: multiple public lottery terminology pages; exact bóng-âm conventions vary by community.

Category: descriptive / predictive-hypothesis

Input: AB.

Mathematical definition: VLA's canonical definitions are versioned in `number_reference.py`; bộ is the orbit generated by digit-wise bóng dương and reversal. Bóng dương uses 0<->5, 1<->6, 2<->7, 3<->8, 4<->9. Bóng âm uses the explicitly documented VLA convention.

Parameters: ontology schema version.

Output: family id/members/partner.

Edge cases: ambiguous folklore terminology; never silently replace the canonical mapping from another website.

Leakage risk: none for deterministic mapping.

Existing VLA equivalent: `number_reference.py`.

Implementation status: existing

Research confidence: high for VLA's declared convention, medium for cross-site equivalence.

Predictive evidence: challenger only.

## Pair frequency / cặp cùng về

Aliases: tần suất cặp, cặp loto cùng về, co-occurrence pair

Sources:
- https://xosodaiphat.com/
- https://www.minhngoc.net.vn/thong-ke-xo-so/tan-suat-tinh.html
- public navigation on https://hainhay.net/

Category: descriptive / pattern-mining

Input: per-date set of hit numbers.

Mathematical definition: for unordered distinct pair {i,j}, same_draw_count = number of eligible dates where both i and j occur. Optional Jaccard/phi quantify association; support must be retained.

Parameters: date window, minimum support.

Output: counts, support/rates, association measures.

Edge cases: repeated occurrences do not create duplicate same-date pair hits unless occurrence-pair counting is explicitly requested.

Leakage risk: low with cutoff.

Existing VLA equivalent: `pair_stats.compute_pair_frequency`, `cap_loto_50_stats.py`, co-occurrence in `number_dynamics.py`.

Implementation status: existing

Research confidence: high

Predictive evidence: descriptive-only unless separately validated.

## Dynamic positional cầu / cầu chạy

Aliases: cầu loto, cầu vị trí, cầu chạy N ngày, cầu lộn, bạch thủ-style path

Sources:
- https://rongbachkim.net/soicau-ngay-20-07-2026.html?db=0&exactlimit=0&limit=3&lon=1&nhay=2&showcau=&vt=103x104
- public cầu navigation on https://mketqua.net/ and https://hainhay.net/

Category: pattern-mining

Input: semantically indexed prize/digit positions and historical target draws.

Observed behavior: public tools expose source-position pairs, lộn toggles, target type, and a maximum consecutive run length; pages also summarize multiple positions producing the same number/pair.

Mathematical definition: each rule deterministically maps one or more source positions from dates strictly before the target to a candidate set. A run length is the number of consecutive eligible target dates ending at a stated endpoint for which the candidate-set success predicate is true.

Parameters: source positions, lag(s), operator, target type, minimum run/support.

Output: rule id, support, hits/failures, current/max streak, candidate payload and evidence dates.

Edge cases: missing dates, duplicate dates, same-position rules, lộn doubles, large search-space multiplicity.

Leakage risk: high if source date or selected pattern is allowed to use target/future outcomes.

Existing VLA equivalent: `path_prob.py`, `path_models.py`, `cau_position_evidence.py`, `crosslag_positional_lab.py`, `research_firewall.py`.

Implementation status: existing; do not duplicate.

Research confidence: high for observable position/run mechanics; proprietary ranking is unknown.

Predictive evidence: research-only unless separate OOS promotion is implemented.

## Cầu 2 nháy

Aliases: hai nháy, lô 2 nháy

Sources:
- https://rongbachkim.net/soicau-ngay-20-07-2026.html?db=0&exactlimit=0&limit=3&lon=1&nhay=2&showcau=&vt=103x104
- https://hainhay.net/

Category: pattern-mining

Input: candidate number/set and complete draw occurrence counts.

Mathematical definition used for independent VLA interpretation: success_1 = occurrence_count >= 1; success_2 = occurrence_count >= 2. These are separate outcomes and must not be conflated.

Parameters: occurrence threshold (1,2,...), pattern rule.

Output: exact occurrence count, >=1 hit, >=2 hit.

Edge cases: duplicate appearances inside one draw.

Leakage risk: high for target-date misuse; none for retrospective descriptive counting.

Existing VLA equivalent: exact nháy counts in `advanced_stats.compute_daily_nhay_stats`; positional research UI supports a `nhay=2` concept externally but VLA should keep >=2 target semantics explicit.

Implementation status: partially existing; integration into generic positional research can be a later research PR.

Research confidence: high for >=2 occurrence interpretation from public UI behavior.

Predictive evidence: untested.

## Conditional matrices / next-day association

Aliases: loto theo đặc biệt, loto theo loto, conditional matrix

Sources: public menus on https://hainhay.net/ and related analysis platforms.

Category: pattern-mining / predictive-hypothesis

Input: aligned consecutive date pairs.

Mathematical definition: transition_count[i,j] = count(source i at t and target j at t+1); conditional probability = count / source trials, preferably shrinkage-smoothed; lift compares against target marginal prevalence.

Parameters: smoothing prior, minimum support, exact +1 calendar-day requirement.

Output: raw counts, trials, probability, support/lift, FDR where tested.

Edge cases: missing calendar dates and small source-state support.

Leakage risk: medium/high if full-history tables are reused for historical predictions.

Existing VLA equivalent: `conditional_matrices.py`, `conditional_nextday.py`, `number_dynamics.py`.

Implementation status: existing

Research confidence: high

Predictive evidence: research/challenger only unless OOS validated.

## Association rules

Aliases: A -> B, support/confidence/lift

Sources: generic statistical formalism applied to public co-occurrence/conditional concepts.

Category: pattern-mining

Input: eligible event pairs A,B.

Mathematical definition:
- support(A->B)=count(A and B)/N;
- confidence(A->B)=count(A and B)/count(A);
- lift=confidence/P(B).

Parameters: minimum observations/support, smoothing/FDR where appropriate.

Output: support, confidence, lift, counts.

Edge cases: 1/1 confidence must not outrank large-support evidence solely due to 100% confidence.

Leakage risk: depends on temporal use.

Existing VLA equivalent: conditional/research modules contain counts, effects/lift and FDR; a standalone generic rule API is optional future refactoring rather than a duplicate implementation.

Implementation status: existing in specialized modules / planned generic facade.

Research confidence: high

Predictive evidence: research-only.

## Markov transition

Aliases: Markov, transition state

Sources: statistical model, not a claim taken from a lottery marketing site.

Category: predictive-hypothesis

Input: chronologically aligned state/hit sequence.

Mathematical definition: `P_ij=(count(i->j)+alpha)/(sum_k count(i->k)+alpha*|S|)` for a categorical state; VLA also uses Beta/empirical-Bayes variants for binary per-number states.

Parameters: prior/smoothing strength, order, minimum support.

Output: counts, posterior probabilities, lift/reliability.

Edge cases: high-order 100-state chains are sample-starved.

Leakage risk: high if transition tables include future test rows.

Existing VLA equivalent: `markov_stats.py`, `number_dynamics.py` first/second-order components.

Implementation status: existing

Research confidence: high

Predictive evidence: no automatic production promotion; must beat simple temporal baselines.

## Pascal-style transform

Aliases: cầu Pascal, Pascale

Sources:
- https://caulo168.com/soi-cau-pascal-cau-lo-168
- https://xsmb360.com/du-doan-xsmb-1-6-2025-thong-ke-xo-so-mien-bac-chu-nhat/

Category: predictive-hypothesis / deterministic transform

Observed behavior: public descriptions concatenate recent result digits (often special + first prize), repeatedly replace adjacent pairs by `(a+b) mod 10`, and derive a final one/two-digit payload. Site-specific ranking layers are not publicly reproducible.

Independent mathematical definition: for row `r^(0)=(d_1,...,d_n)`, define `r^(k+1)_i=(r^(k)_i+r^(k)_(i+1)) mod 10` until the configured terminal width.

Parameters: source digits/prizes, terminal width, optional reversal.

Output: deterministic terminal digits/candidate set.

Edge cases: different sites stop at one or two digits and may use different seed digits.

Leakage risk: low for transform when seed comes strictly from prior draws; high if variant selection is tuned on the same holdout.

Existing VLA equivalent: none canonical.

Implementation status: planned research-only; not included in this production-safety PR.

Research confidence: high for recurrence, medium for site-specific seed/selection rules.

Predictive evidence: untested; no established forecasting power assumed.

## Fibonacci-style lottery rules

Aliases: Fibonacci sequence derived dàn/cầu

Sources: public web search on 2026-09-02 did not yield a stable, reproducible Vietnamese lottery mapping across reputable analysis pages.

Category: predictive-hypothesis

Input: unknown site-specific mapping; standard sequence alone is `F0=0, F1=1, Fn=F(n-1)+F(n-2)`.

Mathematical definition: the Fibonacci recurrence is known, but a lottery-history-to-candidate mapping is not sufficiently specified by the researched public sources.

Parameters: undefined until a reproducible public rule is identified.

Output: none.

Edge cases: numerology/gấp-thế content must not be misrepresented as a statistical forecasting algorithm.

Leakage risk: unknown.

Existing VLA equivalent: none.

Implementation status: rejected for now / research-only until definition is reproducible.

Research confidence: low for lottery mapping, high for the mathematical Fibonacci recurrence itself.

Predictive evidence: untested.

## Candidate score / "chỉ số nổ"

Aliases: điểm tổng hợp, score, ranking index

Sources: common public ranking presentation; exact proprietary weights are generally unknown.

Category: descriptive/predictive-hypothesis depending on components.

Input: normalized descriptive/model evidence.

Mathematical definition: configurable weighted score `S(x)=sum_k w_k z_k(x)` where each z component has documented scale/provenance. It is not a probability unless independently calibrated.

Parameters: component definitions and weights.

Output: score plus evidence/provenance.

Edge cases: arbitrary percentages must not be labeled probabilities.

Leakage risk: depends on component construction and weight tuning.

Existing VLA equivalent: explainability/ranking layers in `cau_keo_ml.py`, `statistical_signal.py`, `statistics_ai_overlay.py`.

Implementation status: existing specialized implementations; future generic facade optional.

Research confidence: high for distinction between score and calibrated probability.

Predictive evidence: only calibrated/OOS-evaluated model probabilities may be interpreted probabilistically.
