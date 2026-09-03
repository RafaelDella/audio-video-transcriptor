from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import TranscriptionConfig
from .types import Segment


def fingerprint(source: Path, config: TranscriptionConfig) -> str:
    stat = source.stat()
    payload = {
        "source": str(source.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "config": config.as_dict(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


class Checkpoint:
    def __init__(self, path: Path, identity: str, resume: bool) -> None:
        self.path = path
        self.identity = identity
        self.completed: set[int] = set()
        self.segments: list[Segment] = []
        if resume and path.is_file():
            self._load()
        else:
            self._reset()

    def _reset(self) -> None:
        self.path.write_text(
            json.dumps({"type": "meta", "fingerprint": self.identity}) + "\n",
            encoding="utf-8",
        )

    def _load(self) -> None:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if not lines:
            self._reset()
            return
        meta = json.loads(lines[0])
        if meta.get("fingerprint") != self.identity:
            self._reset()
            return
        for line in lines[1:]:
            record = json.loads(line)
            if record.get("type") != "chunk":
                continue
            self.completed.add(int(record["index"]))
            self.segments.extend(Segment.from_dict(item) for item in record["segments"])

    def append(self, index: int, segments: list[Segment]) -> None:
        record = {
            "type": "chunk",
            "index": index,
            "segments": [segment.to_dict() for segment in segments],
        }
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            file.flush()
        self.completed.add(index)
        self.segments.extend(segments)


def checkpoint_path(output: Path) -> Path:
    return output.with_name(output.name + ".checkpoint.jsonl")
