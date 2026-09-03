import pytest

from transcreve.config import profile


def test_profile_accepts_overrides():
    config = profile("equilibrado", model="medium", threads=3, language=None)
    assert config.model == "medium"
    assert config.threads == 3
    assert config.language is None


def test_profile_rejects_invalid_overlap():
    with pytest.raises(ValueError, match="sobreposicao"):
        profile("equilibrado", chunk_minutes=1, overlap_seconds=60)
