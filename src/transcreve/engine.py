from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from .audio import iter_audio_chunks
from .checkpoint import Checkpoint, checkpoint_path, fingerprint
from .config import TranscriptionConfig
from .output import write_output
from .types import AudioChunk, Segment

ProgressCallback = Callable[[AudioChunk, bool], None]


class Transcriber:
    def __init__(self, config: TranscriptionConfig) -> None:
        config.validate()
        self.config = config
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
            )
        return self._model

    def _transcribe_chunk(self, chunk: AudioChunk, context: str) -> list[Segment]:
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
    ) -> list[Segment]:
        source = source.resolve()
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        state_path = checkpoint_path(output)
        state = Checkpoint(state_path, fingerprint(source, self.config), resume)
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
                skipped = chunk.index in state.completed
                if progress:
                    progress(chunk, skipped)
                try:
                    if skipped:
                        continue
                    segments = self._transcribe_chunk(chunk, context)
                    state.append(chunk.index, segments)
                    recent = " ".join(segment.text for segment in segments)[-300:]
                    context = " ".join(part for part in (self.config.vocabulary, recent) if part)
                finally:
                    Path(chunk.path).unlink(missing_ok=True)

        state.segments.sort(key=lambda segment: (segment.start, segment.end))
        write_output(output, state.segments, format_name, timestamps)
        if not keep_checkpoint:
            state_path.unlink(missing_ok=True)
        return state.segments
