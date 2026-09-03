from __future__ import annotations

import wave
from collections.abc import Iterator
from pathlib import Path

import av

from .types import AudioChunk

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2


def _write_wav(path: Path, data: bytes | bytearray) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(SAMPLE_WIDTH)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(data)


def iter_audio_chunks(
    source: Path, directory: Path, chunk_minutes: int, overlap_seconds: float
) -> Iterator[AudioChunk]:
    """Converte o audio incrementalmente em WAV mono/16 kHz de tamanho limitado."""
    limit = chunk_minutes * 60 * SAMPLE_RATE
    overlap = int(overlap_seconds * SAMPLE_RATE)
    step = limit - overlap
    if step <= 0:
        raise ValueError("a sobreposicao deve ser menor que a duracao do bloco")

    container = av.open(str(source))
    if not container.streams.audio:
        container.close()
        raise ValueError(f"nenhuma faixa de audio encontrada em {source}")
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    buffer = bytearray()
    start_sample = total_samples = index = 0

    def append(frame) -> None:
        nonlocal total_samples
        pcm = frame.to_ndarray().tobytes()
        buffer.extend(pcm)
        total_samples += len(pcm) // SAMPLE_WIDTH

    def ready_chunks() -> Iterator[AudioChunk]:
        nonlocal start_sample, index
        while len(buffer) >= limit * SAMPLE_WIDTH:
            path = directory / f"chunk-{index:05d}.wav"
            _write_wav(path, buffer[: limit * SAMPLE_WIDTH])
            yield AudioChunk(index, str(path), start_sample / SAMPLE_RATE, limit / SAMPLE_RATE)
            del buffer[: step * SAMPLE_WIDTH]
            start_sample += step
            index += 1

    try:
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                append(converted)
            yield from ready_chunks()
        for converted in resampler.resample(None):
            append(converted)
        yield from ready_chunks()

        remaining = total_samples - start_sample
        if remaining > overlap:
            path = directory / f"chunk-{index:05d}.wav"
            _write_wav(path, buffer[: remaining * SAMPLE_WIDTH])
            yield AudioChunk(index, str(path), start_sample / SAMPLE_RATE, remaining / SAMPLE_RATE)
    finally:
        container.close()
