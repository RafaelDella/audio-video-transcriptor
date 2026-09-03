from __future__ import annotations

from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class TranscriptionConfig:
    model: str = "small"
    language: str | None = "pt"
    device: str = "cpu"
    compute_type: str = "int8"
    chunk_minutes: int = 5
    overlap_seconds: float = 15.0
    beam_size: int = 5
    threads: int = 2
    vad: bool = True
    vad_threshold: float = 0.40
    vocabulary: str = ""

    def validate(self) -> None:
        if self.chunk_minutes <= 0:
            raise ValueError("chunk_minutes deve ser positivo")
        if not 0 <= self.overlap_seconds < self.chunk_minutes * 60:
            raise ValueError("a sobreposicao deve ser menor que o bloco")
        if self.beam_size <= 0 or self.threads <= 0:
            raise ValueError("beam_size e threads devem ser positivos")

    def as_dict(self) -> dict:
        return asdict(self)


PROFILES: dict[str, TranscriptionConfig] = {
    "economico": TranscriptionConfig(model="base", beam_size=1, chunk_minutes=3),
    "equilibrado": TranscriptionConfig(model="small"),
    "qualidade": TranscriptionConfig(model="medium"),
    "maximo": TranscriptionConfig(model="large-v3", device="auto", compute_type="auto"),
}


def profile(name: str, **overrides) -> TranscriptionConfig:
    config = PROFILES[name]
    result = replace(config, **overrides)
    result.validate()
    return result
