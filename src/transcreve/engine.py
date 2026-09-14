from __future__ import annotations

import math
import tempfile
from collections.abc import Callable
from concurrent.futures import CancelledError
from dataclasses import dataclass
from pathlib import Path

import av

from .audio import iter_audio_chunks
from .checkpoint import Checkpoint, checkpoint_path, fingerprint
from .config import TranscriptionConfig
from .output import write_output
from .types import AudioChunk, Segment


@dataclass(frozen=True)
class ProgressEvent:
    phase: str  # started, completed, finished
    chunk_index: int | None
    completed_chunks: int
    total_chunks: int | None
    skipped: bool = False
    start_seconds: float | None = None
    end_seconds: float | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def _estimated_chunk_count(source: Path, minutes: int, overlap: float) -> int | None:
    """Estimate the chunk count from container metadata without decoding twice."""
    with av.open(str(source)) as container:
        stream = next(iter(container.streams.audio), None)
        if stream is None:
            return None
        if stream.duration is not None and stream.time_base is not None:
            duration = float(stream.duration * stream.time_base)
        elif container.duration is not None:
            duration = container.duration / av.time_base
        else:
            return None
    if duration <= 0:
        return None
    length = minutes * 60
    if duration <= length:
        return 1
    return 1 + math.ceil((duration - length) / (length - overlap))


class Transcriber:
    def __init__(self, config: TranscriptionConfig, offline: bool = False) -> None:
        config.validate()
        self.config = config
        self.offline = offline
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.config.model,
                device=self.config.device,
                compute_type=self.config.compute_type,
                cpu_threads=self.config.threads,
                num_workers=1,
                local_files_only=self.offline,
            )
        return self._model

    def prepare_model(self) -> None:
        """Load or download the model before reporting chunk processing."""
        self._load_model()

    def _transcribe_chunk(self, chunk: AudioChunk, context: str,
                          cancel: Callable[[], bool] | None = None) -> list[Segment]:
        kwargs = {
            "language": self.config.language,
            "vad_filter": self.config.vad,
            "beam_size": self.config.beam_size,
            "initial_prompt": context or None,
            "hotwords": self.config.vocabulary or None,
            "condition_on_previous_text": True,
        }
        if self.config.vad:
            kwargs["vad_parameters"] = {
                "threshold": self.config.vad_threshold,
                "min_speech_duration_ms": 150,
                "min_silence_duration_ms": 700,
                "speech_pad_ms": 400,
            }
        raw_segments, _ = self._load_model().transcribe(chunk.path, **kwargs)
        result = []
        for raw in raw_segments:
            if cancel and cancel():
                raise CancelledError()
            if chunk.index and (raw.start + raw.end) / 2 < self.config.overlap_seconds:
                continue
            text = raw.text.strip()
            if text:
                result.append(Segment(chunk.start + raw.start, chunk.start + raw.end, text))
        return result

    def transcribe(
        self,
        source: Path,
        output: Path,
        format_name: str = "txt",
        timestamps: bool = False,
        resume: bool = True,
        keep_checkpoint: bool = False,
        progress: ProgressCallback | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> list[Segment]:
        source = source.resolve()
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        state_path = checkpoint_path(output)
        state = Checkpoint(state_path, fingerprint(source, self.config), resume)
        total_chunks = (
            _estimated_chunk_count(source, self.config.chunk_minutes, self.config.overlap_seconds)
            if progress else None
        )
        completed_chunks = 0
        context = " ".join(
            part
            for part in (self.config.vocabulary, " ".join(s.text for s in state.segments)[-300:])
            if part
        )

        with tempfile.TemporaryDirectory(prefix="transcreve-") as directory:
            chunks = iter_audio_chunks(
                source,
                Path(directory),
                self.config.chunk_minutes,
                self.config.overlap_seconds,
            )
            for chunk in chunks:
                if cancel and cancel():
                    Path(chunk.path).unlink(missing_ok=True)
                    raise CancelledError()
                skipped = chunk.index in state.completed
                if progress:
                    progress(
                        ProgressEvent(
                            "started", chunk.index, completed_chunks, total_chunks,
                            skipped, chunk.start, chunk.start + chunk.duration,
                        )
                    )
                try:
                    if cancel and cancel():
                        raise CancelledError()
                    if not skipped:
                        segments = (self._transcribe_chunk(chunk, context, cancel)
                                    if cancel else self._transcribe_chunk(chunk, context))
                        if cancel and cancel():
                            raise CancelledError()
                        state.append(chunk.index, segments)
                        recent = " ".join(segment.text for segment in segments)[-300:]
                        context = " ".join(
                            part for part in (self.config.vocabulary, recent) if part
                        )
                    completed_chunks += 1
                    if cancel and cancel():
                        raise CancelledError()
                    if progress:
                        progress(
                            ProgressEvent(
                                "completed", chunk.index, completed_chunks, total_chunks,
                                skipped, chunk.start, chunk.start + chunk.duration,
                            )
                        )
                finally:
                    Path(chunk.path).unlink(missing_ok=True)

        if cancel and cancel():
            raise CancelledError()
        state.segments.sort(key=lambda segment: (segment.start, segment.end))
        write_output(output, state.segments, format_name, timestamps)
        if not keep_checkpoint:
            state_path.unlink(missing_ok=True)
        if progress:
            progress(ProgressEvent("finished", None, completed_chunks, completed_chunks))
        return state.segments
