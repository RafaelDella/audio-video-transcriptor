from pathlib import Path

from transcreve.config import profile
from transcreve.engine import Transcriber
from transcreve.model_store import cached_model, model_bytes, prepare_model


def test_cached_model_requires_complete_local_snapshot(tmp_path: Path, monkeypatch):
    calls = []

    def fake_download(model, *, local_files_only=False):
        calls.append((model, local_files_only))
        return str(tmp_path)

    monkeypatch.setattr("faster_whisper.utils.download_model", fake_download)
    assert cached_model("small") is None
    for name in ("config.json", "model.bin", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"ok")
    assert cached_model("small") == tmp_path
    assert model_bytes("small") == 6
    assert prepare_model("small") == tmp_path
    assert calls == [("small", True)] * 4


def test_prepare_model_downloads_only_when_missing(tmp_path: Path, monkeypatch):
    calls = []

    def fake_download(model, *, local_files_only=False):
        calls.append(local_files_only)
        if local_files_only:
            raise OSError("not cached")
        for name in ("config.json", "model.bin", "tokenizer.json"):
            (tmp_path / name).write_bytes(b"ok")
        return str(tmp_path)

    monkeypatch.setattr("faster_whisper.utils.download_model", fake_download)
    assert prepare_model("base") == tmp_path
    assert calls == [True, False]


def test_transcriber_offline_load_never_requests_download(monkeypatch):
    options = {}

    class FakeWhisperModel:
        def __init__(self, model, **kwargs):
            options.update(kwargs)

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeWhisperModel)
    Transcriber(profile("economico"), offline=True).prepare_model()
    assert options["local_files_only"] is True
