from datetime import date

from pydantic import BaseModel, RootModel, model_validator


class Result(BaseModel):
    """A single XSMB draw result.

    All prize fields are stored as integers (leading zeros are preserved when
    rendering via formatting).  Prize ranges are enforced at the domain-model
    boundary so malformed source/import data cannot create an invalid draw even
    when it bypasses the normal HTML parser.
    """
    date: date

    special: int

    prize1: int

    prize2_1: int
    prize2_2: int

    prize3_1: int
    prize3_2: int
    prize3_3: int
    prize3_4: int
    prize3_5: int
    prize3_6: int

    prize4_1: int
    prize4_2: int
    prize4_3: int
    prize4_4: int

    prize5_1: int
    prize5_2: int
    prize5_3: int
    prize5_4: int
    prize5_5: int
    prize5_6: int

    prize6_1: int
    prize6_2: int
    prize6_3: int

    prize7_1: int
    prize7_2: int
    prize7_3: int
    prize7_4: int

    @model_validator(mode="after")
    def validate_prize_ranges(self) -> "Result":
        widths = {
            "special": 5,
            "prize1": 5,
            "prize2_1": 5,
            "prize2_2": 5,
            "prize3_1": 5,
            "prize3_2": 5,
            "prize3_3": 5,
            "prize3_4": 5,
            "prize3_5": 5,
            "prize3_6": 5,
            "prize4_1": 4,
            "prize4_2": 4,
            "prize4_3": 4,
            "prize4_4": 4,
            "prize5_1": 4,
            "prize5_2": 4,
            "prize5_3": 4,
            "prize5_4": 4,
            "prize5_5": 4,
            "prize5_6": 4,
            "prize6_1": 3,
            "prize6_2": 3,
            "prize6_3": 3,
            "prize7_1": 2,
            "prize7_2": 2,
            "prize7_3": 2,
            "prize7_4": 2,
        }
        for field, width in widths.items():
            value = getattr(self, field)
            if not 0 <= int(value) < 10**width:
                raise ValueError(
                    f"{field}={value!r} outside valid {width}-digit prize range"
                )
        return self


class ResultList(RootModel):
    root: list[Result]
