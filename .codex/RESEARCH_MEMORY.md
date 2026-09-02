# Verified research memory

## RES-0001 — Frequency and lô gan

Source: https://mketqua.net/tan-suat-loto; https://mketqua.net/loto-gan; https://www.minhngoc.net.vn/thong-ke-xo-so/gan-cuc-dai-tinh.html

Observed concept: configurable historical occurrence and absent-draw summaries.

Independent mathematical interpretation: occurrence count and draw-presence count are separate; gap is completed draws since the last hit strictly before the target.

VLA implementation: `frequency_stats.compute_frequency_stats`; `gap_cycle_stats.compute_gap_stats`

Validation: synthetic count/cycle and future-mutation tests.

Status: descriptive-only

Confidence: high

Last verified: 2026-09-02

## RES-0002 — Cặp loto 50

Source: https://xosodaiphat.com/thong-ke-tan-suat-loto-cap.html

Observed concept: public 50-pair table contains 45 reverse pairs and five double-shadow pairs.

Independent mathematical interpretation: an involutive partition of 00..99; non-doubles map to reverse and doubles map to the canonical positive-shadow double.

VLA implementation: `number_reference.cap_loto_50_partner`

Validation: full partition, involution and edge-pair unit tests.

Status: descriptive-only

Confidence: high

Last verified: 2026-09-02

## RES-0003 — Running positional cầu

Source: https://mketqua.net/cau-loto; https://mketqua.net/cau-hai-nhay; https://hainhay.net/cau-loto

Observed concept: public controls select a boundary and running-day count; results expose numbers, position explanations and streak counts.

Independent mathematical interpretation: semantic prior-draw digit positions feed deterministic candidate transforms evaluated on exact consecutive target dates.

VLA implementation: `dynamic_cau.find_running_patterns`

Validation: synthetic running/broken streak, missing-history, duplicate/unsorted input, two-nháy and future-mutation tests.

Status: challenger

Confidence: medium

Last verified: 2026-09-02

## RES-0004 — Pascal-style adjacent-sum triangle

Source: https://caulo100.com/soi-cau-pascal-cau-lo-100; https://soicauvn247.com/soi-cau-pascal

Observed concept: next triangle row adds adjacent digits and keeps the units digit.

Independent mathematical interpretation: `r_(k+1,j)=(r_(k,j)+r_(k,j+1)) mod 10`.

VLA implementation: none; input/candidate extraction is not sufficiently specified.

Validation: public examples reviewed only; no predictive experiment.

Status: rejected

Confidence: medium for recurrence, low for candidate mapping

Last verified: 2026-09-02

## RES-0005 — Fibonacci-style lottery rule

Source: public-web research pass; no stable reproducible Vietnamese lottery mapping found.

Observed concept: name references Fibonacci, but a history-to-candidate mapping was not documented precisely enough.

Independent mathematical interpretation: only `F_0=0`, `F_1=1`, `F_n=F_(n-1)+F_(n-2)` is known; no lottery transform inferred.

VLA implementation: none

Validation: documentation threshold not met.

Status: rejected

Confidence: low

Last verified: 2026-09-02
