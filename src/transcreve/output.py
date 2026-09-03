from __future__ import annotations

import json
from pathlib import Path

from .types import Segment


def timestamp(seconds: float, separator: str = ",") -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def render(segments: list[Segment], format_name: str, timestamps: bool = False) -> str:
    if format_name == "txt":
        lines = []
        for segment in segments:
            prefix = ""
            if timestamps:
                prefix = f"[{timestamp(segment.start, '.')} --> {timestamp(segment.end, '.')}] "
            lines.append(prefix + segment.text)
        return "\n".join(lines) + ("\n" if lines else "")
    if format_name == "srt":
        blocks = [
            f"{index}\n{timestamp(s.start)} --> {timestamp(s.end)}\n{s.text}"
            for index, s in enumerate(segments, 1)
        ]
        return "\n\n".join(blocks) + ("\n" if blocks else "")
    if format_name == "vtt":
        blocks = [
            f"{timestamp(s.start, '.')} --> {timestamp(s.end, '.')}\n{s.text}" for s in segments
        ]
        return "WEBVTT\n\n" + "\n\n".join(blocks) + ("\n" if blocks else "")
    if format_name == "json":
        return json.dumps([s.to_dict() for s in segments], ensure_ascii=False, indent=2) + "\n"
    raise ValueError(f"formato desconhecido: {format_name}")


def write_output(path: Path, segments: list[Segment], format_name: str, timestamps=False) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(render(segments, format_name, timestamps), encoding="utf-8")
    temporary.replace(path)
