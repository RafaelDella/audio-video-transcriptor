"""Inspect and prepare Faster-Whisper models in the standard local cache."""

from __future__ import annotations

from pathlib import Path


def cached_model(model: str) -> Path | None:
    """Return a complete local snapshot without contacting the Hub."""
    from faster_whisper.utils import download_model

    try:
        directory = Path(download_model(model, local_files_only=True))
    except (OSError, ValueError):
        return None
    required = ("config.json", "model.bin", "tokenizer.json")
    return directory if all((directory / name).is_file() for name in required) else None


def model_bytes(model: str) -> int | None:
    """Measure the files in a cached snapshot; return None if unavailable."""
    directory = cached_model(model)
    if directory is None:
        return None
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def prepare_model(model: str) -> Path:
    """Download a model once, reusing the Hugging Face cache on later runs."""
    from faster_whisper.utils import download_model

    existing = cached_model(model)
    if existing:
        return existing
    directory = Path(download_model(model))
    if not all((directory / name).is_file() for name in
               ("config.json", "model.bin", "tokenizer.json")):
        raise RuntimeError("O download do modelo não foi concluído. Tente novamente.")
    return directory
