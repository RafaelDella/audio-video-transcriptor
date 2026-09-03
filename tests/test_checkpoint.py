from pathlib import Path

from transcreve.checkpoint import Checkpoint, fingerprint
from transcreve.config import profile
from transcreve.types import Segment


def test_checkpoint_round_trip(tmp_path: Path):
    audio = tmp_path / "audio.bin"
    audio.write_bytes(b"audio")
    identity = fingerprint(audio, profile("economico"))
    path = tmp_path / "state.jsonl"
    first = Checkpoint(path, identity, resume=True)
    first.append(0, [Segment(0, 1, "teste")])

    restored = Checkpoint(path, identity, resume=True)
    assert restored.completed == {0}
    assert restored.segments == [Segment(0, 1, "teste")]


def test_changed_configuration_invalidates_checkpoint(tmp_path: Path):
    audio = tmp_path / "audio.bin"
    audio.write_bytes(b"audio")
    path = tmp_path / "state.jsonl"
    old = Checkpoint(path, fingerprint(audio, profile("economico")), resume=True)
    old.append(0, [Segment(0, 1, "antigo")])

    current = Checkpoint(path, fingerprint(audio, profile("equilibrado")), resume=True)
    assert current.completed == set()
    assert current.segments == []
