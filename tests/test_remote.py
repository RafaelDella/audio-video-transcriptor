from pathlib import Path

import pytest

from transcreve.remote import source_name, validate_url


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abc123",
    "https://vimeo.com/123456",
    "https://example.com/audio.mp3",
])
def test_public_links_are_accepted(url):
    assert validate_url(f"  {url}  ") == url


@pytest.mark.parametrize("url", [
    "", "file:///tmp/audio.mp3", "https://localhost/audio",
    "http://127.0.0.1/audio", "http://192.168.1.4/audio",
    "https://user:pass@example.com/audio",
])
def test_local_or_invalid_links_are_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_source_names_are_readable_and_safe():
    assert source_name("https://youtu.be/abc123") == ("YouTube: abc123", "youtube-abc123", "YouTube")
    assert source_name("https://vimeo.com/987654") == ("Vimeo: 987654", "vimeo-987654", "Vimeo")
    assert source_name("https://example.com/audio.mp3") == ("example.com: audio.mp3", "audio", "example.com")


def test_download_media_uses_a_single_audio_stream(tmp_path, monkeypatch):
    from transcreve.remote import download_media

    seen = {}

    class FakeDownloader:
        def __init__(self, options):
            seen.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            assert download is True
            assert url == "https://example.com/audio.mp3"
            target = tmp_path / "source.mp3"
            target.write_bytes(b"audio")
            seen["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 50,
                                       "total_bytes": 100})
            seen["progress_hooks"][0]({"status": "finished"})
            return {"title": "Entrevista", "requested_downloads": [{"filepath": str(target)}]}

        def prepare_filename(self, info):
            return str(tmp_path / "source.mp3")

    import sys
    import types
    monkeypatch.setattr("transcreve.remote.shutil.which", lambda name: "C:/Program Files/nodejs/node.exe")
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeDownloader))
    progress = []
    source, title = download_media("https://example.com/audio.mp3", tmp_path, progress.append)
    assert source == Path(tmp_path / "source.mp3")
    assert title == "Entrevista"
    assert seen["format"] == "bestaudio/best"
    assert seen["noplaylist"] is True
    assert seen["js_runtimes"] == {"node": {"path": "C:/Program Files/nodejs/node.exe"}}
    assert progress == [50, 100]
