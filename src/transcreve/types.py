from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> Segment:
        return cls(float(value["start"]), float(value["end"]), str(value["text"]))


@dataclass(frozen=True)
class AudioChunk:
    index: int
    path: str
    start: float
    duration: float
