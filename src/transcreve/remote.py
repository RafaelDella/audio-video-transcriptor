"""Resolve user-provided media links into temporary local media files."""

from __future__ import annotations

import ipaddress
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def validate_url(value: str) -> str:
    """Accept only public HTTP(S) media links without embedded credentials."""
    url = value.strip()
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("Cole um link HTTP ou HTTPS válido, sem usuário e senha.")
    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise ValueError("Links para este computador não são aceitos.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Use um link público de mídia.")
    return url


def source_name(url: str) -> tuple[str, str, str]:
    """Return a recognizable label, default output stem, and origin label."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        key = parse_qs(parsed.query).get("v", [""])[0] or parsed.path.strip("/").split("/")[-1]
        origin = "YouTube"
    elif host in {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}:
        key = parsed.path.strip("/").split("/")[-1]
        origin = "Vimeo"
    else:
        key = Path(parsed.path).stem or host.split(".")[0]
        origin = host.removeprefix("www.")
    display = Path(parsed.path).name if origin not in {"YouTube", "Vimeo"} else key
    slug = re.sub(r"[^\w.-]+", "-", key, flags=re.UNICODE).strip(" .-")[:70]
    stem = f"{origin.lower()}-{slug}" if origin in {"YouTube", "Vimeo"} else slug
    return f"{origin}: {display or 'mídia'}", stem or "transcricao", origin


def download_media(url: str, directory: Path,
                   progress: Callable[[float | None], None]) -> tuple[Path, str]:
    """Download one audio-capable item without retaining the media after transcription."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError as error:
        raise RuntimeError("Suporte a links ausente. Reinstale a interface com pip install -e '.[gui]'.") from error

    def on_progress(event):
        if event.get("status") == "downloading":
            total = event.get("total_bytes") or event.get("total_bytes_estimate")
            progress(event.get("downloaded_bytes", 0) / total * 100 if total else None)
        elif event.get("status") == "finished":
            progress(100)

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(directory / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [on_progress],
    }
    if node := shutil.which("node"):
        options["js_runtimes"] = {"node": {"path": node}}
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        if not info or info.get("_type") == "playlist":
            raise ValueError("O link precisa apontar para um único áudio ou vídeo.")
        candidates = [Path(item["filepath"]) for item in info.get("requested_downloads", [])
                      if item.get("filepath")]
        candidates.append(Path(downloader.prepare_filename(info)))
    candidates.extend(directory.glob("source.*"))
    source = next((path for path in candidates if path.is_file() and
                   path.suffix not in {".part", ".ytdl"}), None)
    if source is None:
        raise RuntimeError("Não foi possível localizar o áudio obtido do link.")
    return source, str(info.get("title") or source.name)
