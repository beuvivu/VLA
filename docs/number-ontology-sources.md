# Number-ontology source note

The canonical ontology is a software/data contract, not a claim that folklore
relationships have predictive power.

VLA adopts domain relationships when they are repeated consistently across
independent/common Vietnamese lottery-reference sources and can be represented
as deterministic mappings:

- bóng dương digit pairs: `0-5`, `1-6`, `2-7`, `3-8`, `4-9`;
- common 50-cặp-loto partition: 45 reverse pairs plus the five kép-bóng pairs
  `00-55`, `11-66`, `22-77`, `33-88`, `44-99`;
- kép lệch dương: `05-50`, `16-61`, `27-72`, `38-83`, `49-94`;
- bóng âm convention: `0-7`, `1-4`, `2-9`, `3-6`, `5-8`, giving kép âm
  `07-70`, `14-41`, `29-92`, `36-63`, `58-85`;
- bộ/hệ: 15 distinct bóng-dương/lộn families, consisting of 10 regular
  eight-number families and five four-number bộ-kép families;
- chạm: 19 unique numbers for each digit;
- tổng: 10 numbers per `(head + tail) mod 10` group.

The five kép-bóng pairs are recorded as a shared domain relation because common
cặp-loto tables explicitly use them to complete the 50-pair partition. VLA does
not infer that the two members must have equal probability. Historical balance,
co-occurrence, recency and downstream predictive value are measured separately.

Some terms remain variant-sensitive, particularly detailed definitions of sát
kép/sát kép lệch and narrative patterns such as bệt, câm, rơi, trùng cầu, bạc
nhớ or nuôi khung. They may be represented as explicitly named research features
but do not receive production weight without chronological validation.

The implementation source of truth is `src/number_reference.py`; generated data
contracts are written to `data/reference/`, while empirical cặp-loto evidence is
written to `data/pairs/`.
