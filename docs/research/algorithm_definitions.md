# Algorithm Definitions and Scientific Contracts

## 1. Data-time contract

For a forecast target date `D`, every production feature must be computable from information known strictly before the draw on `D`. A supervised feature row is identified by:

`(anchor_date=t, candidate_number=x) -> target on t+1`

All 100 candidate rows belonging to one date are one temporal cluster and may not be split across train/calibration/test.

## 2. Canonical number relations

The source of truth is `src/number_reference.py`.

- head: `floor(x/10)`
- tail: `x mod 10`
- digit total modulo 10: `(head+tail) mod 10`
- reverse/lộn: `AB -> BA`
- doubles/kép bằng: `A == B`
- bóng dương digit mapping: `0↔5,1↔6,2↔7,3↔8,4↔9`
- bóng âm uses the explicit mapping documented in `number_reference.py`
- bộ: VLA canonical bóng-dương/reverse orbit
- chạm d: set of numbers containing digit `d`
- cặp 50: VLA's 50 disjoint partner partition; non-doubles use reverse, doubles use kép-bóng partners.

Ambiguous external terminology never overrides these definitions without an explicit schema/test change.

## 3. Frequency

For date set `W` and number `x`:

`occurrence_count(x,W) = sum over all prize cells of 1[value=x]`

`draw_count(x,W) = sum over dates d in W of 1[x occurs at least once on d]`

`hit_rate(x,W) = draw_count(x,W) / |W|`

These are separate quantities because one number may appear multiple times in one draw.

## 4. Gap / gan

For target date `D` and latest prior hit date `H < D`, gap is the declared number of completed eligible time units between `H` and `D`. VLA modules explicitly document whether the unit is consecutive draw rows or calendar-day absence.

Gap is descriptive. A large gap is not automatically assigned higher future probability.

Useful summaries:
- current right-censored gap;
- completed historical gaps;
- max/mean/median gap;
- empirical percentile or standardized gap only when enough observations exist.

## 5. Recurrence / cycle

For occurrence dates `d1 < d2 < ... < dn`:

`g_i = d_i - d_(i-1)`

Summaries may include mean, median, variance, quantiles, max and recent trend. Current gap is right-censored and should not be silently treated as a completed recurrence interval.

## 6. EMA

For binary hit indicator `y_t` and span `s`:

`alpha = 2/(s+1)`

`EMA_t = alpha*y_t + (1-alpha)*EMA_(t-1)`

The update for a historical target must stop at its anchor date.

## 7. Pair / association statistics

For eligible dates `N` and events A/B:

`support(A->B) = count(A and B)/N`

`confidence(A->B) = count(A and B)/count(A)`

`lift(A->B) = confidence(A->B)/P(B)`

High confidence with tiny support is not strong evidence. Raw counts must accompany normalized statistics.

## 8. Conditional next-day transitions

Only exact calendar transitions are eligible:

`t -> t+1 calendar day`

For source state/event `i` and target event `j`:

`transition_count[i,j] = count(i_t and j_(t+1))`

`P(j|i) = transition_count[i,j] / source_count[i]`

Low-support cells should use explicit smoothing/shrinkage. Historical matrices for a target date may contain only transitions whose target outcomes were known before that target date.

## 9. Markov models

A categorical first-order model with additive smoothing may use:

`P_ij = (count(i->j)+alpha)/(sum_k count(i->k)+alpha*|S|)`

VLA also contains lower-dimensional binary/per-number transition formulations and a limited Markov-2 component in `number_dynamics.py`. Higher order is research-only unless sample-size checks and OOS evidence support it.

## 10. Positional cầu

A positional rule consists of:

- semantic prize/digit source position(s);
- exact calendar lag(s);
- deterministic operator;
- target event definition.

A rule identifier must be stable independently of dashboard layout offsets.

For an evaluation boundary, current run length is the number of consecutive eligible target dates ending at that boundary on which the rule succeeds. Historical support, failures and maximum streak are separate quantities.

Searching many positions/operators creates `PATTERN_SELECTION_BIAS_RISK`. The best historical rule is not predictive evidence. `research_firewall.py` and `crosslag_positional_lab.py` use chronological validation/holdout and multiple-testing controls; their outputs remain research-only.

## 11. Two-nháy

For target number x and target draw D:

- ordinary Loto hit: `occurrence_count(x,D) >= 1`
- two-nháy hit: `occurrence_count(x,D) >= 2`
- exact nháy: the integer occurrence count.

These endpoints must never be conflated.

## 12. Pascal transform

Public lottery-analysis descriptions commonly show deterministic triangular reduction by adjacent modulo-10 sums. VLA's documented independent interpretation is:

Given digit row `r^(0)`:

`r^(k+1)_i = (r^(k)_i + r^(k)_(i+1)) mod 10`

until the explicitly configured output width is reached.

The source digit sequence must be explicitly specified and predate the target. This transformation has no presumed forecasting power and is not a production signal without separate OOS validation.

## 13. Fibonacci

The mathematical sequence is:

`F_0=0`, `F_1=1`, `F_n=F_(n-1)+F_(n-2)`.

This research pass did not identify a sufficiently consistent public mapping from Vietnamese lottery result history to a Fibonacci-derived forecast. VLA therefore does not invent one. Status: research-only / not implemented.

## 14. Score versus probability

An arbitrary weighted index:

`score = sum_i w_i * normalized_component_i`

is a **score**, not a probability.

A value may be called probability only when it is produced or calibrated as a probabilistic estimate and evaluated with proper scoring rules.

## 15. Brier and LogLoss

Both are losses; lower is better.

Binary Brier:

`mean((p-y)^2)`

Relative skill:

`skill = (baseline_loss - challenger_loss)/baseline_loss`

Therefore positive skill is improvement, zero is no improvement and negative is degradation.

For Đề, production serves one categorical distribution over 00..99. Challenger evaluation must normalize each date's 100-number vector exactly as production does and use categorical Brier/LogLoss. Evaluating raw independent Bernoulli values is not equivalent.

For Loto, multiple numbers can hit, so 100 Bernoulli marginals are the appropriate probability representation.

## 16. Controlled walk-forward challenger comparison

For each fold:

`TRAIN < CALIBRATION < TEST`

Baseline and challenger must share:
- exact train dates;
- exact calibration dates;
- exact test dates;
- exact target/candidate rows;
- identical downsampled training row IDs;
- identical model random state and hyperparameters.

Only challenger feature columns may differ.

The domain challenger uses:
- folds 1-2: feature-family screening;
- fold 3: later confirmation and pre-final trust determination;
- fold 4: untouched final evaluation of the actual fixed-trust production blend.

No tuning after observing fold 4 is permitted. Leave-one-group-out diagnostics computed after the final decision are explicitly non-selection diagnostics.

## 17. Paired draw-cluster bootstrap

Candidate rows from one draw are correlated. Bootstrap unit is therefore DATE/DRAW.

For each replicate:
1. sample OOS dates with replacement;
2. preserve each complete 100-row date cluster;
3. preserve multiplicity of repeated sampled dates;
4. compute baseline and challenger losses on the same sampled clusters;
5. compute paired improvement `baseline_loss - challenger_loss`.

The default promotion CI is the percentile 95% interval with a deterministic seed.

## 18. Production promotion gate

Experimental domain features may influence production only when all required evidence is valid:

- enough OOS dates;
- Brier skill > 0;
- LogLoss skill > 0;
- paired bootstrap Brier improvement lower CI > 0;
- paired bootstrap LogLoss improvement lower CI > 0;
- temporal/calibration contracts valid;
- explicit production feature allowlist generated.

Unknown, missing, NaN or invalid states fail closed.

The feature manifest conceptually contains:

```json
{
  "schema_version": 2,
  "baseline_features": ["..."],
  "feature_groups": {"partner": ["..."], "cap_50": ["..."]},
  "promoted_groups": [],
  "production_features": ["..."]
}
```

Rejected feature columns may exist in a research dataframe but are never selected by production inference.

## 19. Limitations

Lottery drawings should be treated as stochastic. Pattern mining can generate visually compelling historical relationships by chance, especially when thousands of hypotheses are searched. Replication of a public statistical transformation proves only transformation equivalence, not predictive power or increased odds.
