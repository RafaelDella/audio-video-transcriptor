import wave
from concurrent.futures import CancelledError
from pathlib import Path

import pytest

from transcreve.audio import SAMPLE_RATE
from transcreve.config import profile
from transcreve.engine import Transcriber
from transcreve.types import Segment


def test_cancel_stops_before_writing_output(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"\0\0" * SAMPLE_RATE * 61)

    transcriber = Transcriber(profile("economico", chunk_minutes=1, overlap_seconds=2))
    monkeypatch.setattr(transcriber, "_transcribe_chunk",
                        lambda *_: pytest.fail("O bloco não deveria começar após cancelar"))
    cancelled = False

    def report(event):
        nonlocal cancelled
        if event.phase == "started":
            cancelled = True

    output = tmp_path / "result.txt"
    with pytest.raises(CancelledError):
        transcriber.transcribe(source, output, progress=report, cancel=lambda: cancelled)
    assert not output.exists()


def test_progress_reports_completion_and_resumed_chunks(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"\0\0" * SAMPLE_RATE * 61)

    transcriber = Transcriber(profile("economico", chunk_minutes=1, overlap_seconds=2))
    monkeypatch.setattr(transcriber, "_transcribe_chunk", lambda chunk, context: [
        Segment(chunk.start, chunk.start + 1, "teste")
    ])
    output = tmp_path / "result.txt"
    events = []
    transcriber.transcribe(source, output, progress=events.append, keep_checkpoint=True)

    assert [(event.phase, event.completed_chunks, event.total_chunks) for event in events] == [
        ("started", 0, 2), ("completed", 1, 2),
        ("started", 1, 2), ("completed", 2, 2), ("finished", 2, 2),
    ]
    assert not any(event.skipped for event in events)

    events.clear()
    transcriber.transcribe(source, output, progress=events.append)
    assert [event.skipped for event in events if event.phase == "completed"] == [True, True]
    assert events[-1].phase == "finished"
