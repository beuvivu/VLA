# Number-ontology source note

The canonical ontology is a software/data contract, not a claim that folklore
relationships have predictive power.

VLA adopts only relationships that are consistently documented across common
Vietnamese lottery-reference sources:

- bóng dương digit pairs: `0-5`, `1-6`, `2-7`, `3-8`, `4-9`;
- kép lệch dương: `05-50`, `16-61`, `27-72`, `38-83`, `49-94`;
- bộ/hệ lookup tables commonly expose 100 seed labels, while duplicate removal
  yields 15 distinct bóng/lộn families (5 four-number and 10 eight-number groups).

Terms with materially conflicting public definitions (notably bóng âm and some
sát-kép/kép-âm variants) are not assigned a production mapping. They require an
explicit variant name and research-only treatment.

The implementation source of truth is `src/number_reference.py`; generated data
contracts are written to `data/reference/`.
