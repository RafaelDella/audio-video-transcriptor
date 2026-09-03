import wave
from pathlib import Path

from transcreve.audio import SAMPLE_RATE, iter_audio_chunks


def test_audio_is_split_with_overlap(tmp_path: Path):
    source = tmp_path / "source.wav"
    seconds = 61
    with wave.open(str(source), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"\0\0" * SAMPLE_RATE * seconds)

    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    chunks = list(iter_audio_chunks(source, chunk_dir, chunk_minutes=1, overlap_seconds=2))

    assert len(chunks) == 2
    assert chunks[0].start == 0
    assert chunks[0].duration == 60
    assert chunks[1].start == 58
    assert chunks[1].duration == 3
