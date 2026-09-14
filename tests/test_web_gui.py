import json
import os
import time
from concurrent.futures import CancelledError
from pathlib import Path
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWebEngineWidgets")

from PySide6.QtWidgets import QApplication, QMainWindow

from transcreve.engine import ProgressEvent
from transcreve.ui_options import valid_output_stem
from transcreve.web_gui import Bridge, MainWindow, Worker


def wait_for(app, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("A interface não respondeu dentro do prazo")


def evaluate(app, window, script):
    result = []
    window.view.page().runJavaScript(script, result.append)
    wait_for(app, lambda: bool(result))
    return result[0]


def test_output_name_rejects_paths_and_windows_reserved_names():
    assert valid_output_stem("Entrevista final")
    for name in ("", "../saida", "pasta\\saida", "CON", "LPT1.txt", "nome.", " nome"):
        assert not valid_output_stem(name)


def test_bridge_validates_output_names_and_collisions(tmp_path):
    app = QApplication.instance() or QApplication([])
    bridge = Bridge(QMainWindow())
    events = []
    bridge.changed.connect(lambda raw: events.append(json.loads(raw)))
    first = tmp_path / "one.wav"
    second = tmp_path / "two.wav"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    bridge.add_paths([first, second, first])
    assert len(bridge.files) == 2

    bridge.rename_file(str(first), "CON")
    bridge.start("txt", "equilibrado")
    assert events[-1]["type"] == "input_error"
    assert bridge.worker is None

    bridge.rename_file(str(first), "same")
    bridge.rename_file(str(second), "same")
    bridge.start("txt", "equilibrado")
    assert "mesma saída" in events[-1]["message"]
    assert bridge.worker is None
    assert app is not None


def test_link_requires_destination_and_can_be_removed(tmp_path):
    app = QApplication.instance() or QApplication([])
    bridge = Bridge(QMainWindow())
    events = []
    bridge.changed.connect(lambda raw: events.append(json.loads(raw)))
    url = "https://vimeo.com/123456"
    bridge.add_url(url)
    bridge.add_url(url)
    assert bridge.links == [url]
    assert bridge.names[url] == "vimeo-123456"
    bridge.start("txt", "equilibrado")
    assert "pasta de destino" in events[-1]["message"]
    assert bridge.worker is None
    bridge.remove_file(url)
    assert bridge.links == []
    assert app is not None


def test_offline_mode_requires_local_model_and_files(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    bridge = Bridge(QMainWindow())
    events = []
    bridge.changed.connect(lambda raw: events.append(json.loads(raw)))
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    bridge.add_paths([source])
    monkeypatch.setattr("transcreve.web_gui.cached_model", lambda model: None)
    bridge.start("txt", "equilibrado", True)
    assert "Prepare o modelo" in events[-1]["message"]
    assert bridge.worker is None

    bridge.add_url("https://vimeo.com/123456")
    bridge.folder = tmp_path
    bridge.start("txt", "equilibrado", True)
    assert "Remova os links" in events[-1]["message"]
    assert bridge.worker is None
    assert app is not None


def test_worker_downloads_link_then_transcribes_and_cleans_temp(tmp_path, monkeypatch):
    url = "https://vimeo.com/123456"
    events = []
    downloaded = []

    def fake_download(url, directory, progress):
        assert url == "https://vimeo.com/123456"
        source = directory / "source.mp3"
        source.write_bytes(b"audio")
        downloaded.append(source)
        progress(40)
        progress(100)
        return source, "Vídeo autorizado"

    class FakeTranscriber:
        def __init__(self, config):
            pass

        def prepare_model(self):
            pass

        def transcribe(self, source, output, format_name, progress, cancel=None):
            assert source.exists()
            progress(ProgressEvent("started", 0, 0, 1))
            output.write_text("transcrição")
            progress(ProgressEvent("finished", None, 1, 1))

    monkeypatch.setattr("transcreve.web_gui.download_media", fake_download)
    monkeypatch.setattr("transcreve.web_gui.Transcriber", FakeTranscriber)
    worker = Worker([(url, "vimeo-123456")], tmp_path, "txt", "equilibrado")
    worker.event.connect(lambda raw: events.append(json.loads(raw)))
    worker.run()
    assert [event["type"] for event in events] == [
        "current", "download", "download", "download", "downloaded",
        "model_loading", "model_ready", "progress", "progress", "result",
    ]
    assert (tmp_path / "vimeo-123456.txt").read_text() == "transcrição"
    assert not downloaded[0].exists()


def test_worker_forwards_final_progress_without_chunk_number(tmp_path, monkeypatch):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"sample")
    events = []

    class FakeTranscriber:
        def __init__(self, config):
            pass

        def transcribe(self, source, output, format_name, progress, cancel=None):
            progress(ProgressEvent("started", 0, 0, 1))
            progress(ProgressEvent("completed", 0, 1, 1, False, 0, 5))
            output.write_text("done")
            progress(ProgressEvent("finished", None, 1, 1))

    monkeypatch.setattr("transcreve.web_gui.Transcriber", FakeTranscriber)
    worker = Worker([(source, "sample")], None, "txt", "equilibrado")
    worker.event.connect(lambda raw: events.append(json.loads(raw)))
    worker.run()

    assert [event["type"] for event in events] == [
        "current", "progress", "progress", "progress", "result"
    ]
    assert events[3]["phase"] == "finished"
    assert events[3]["chunk"] is None
    assert (tmp_path / "sample.txt").read_text() == "done"


def test_cancel_download_stops_current_and_queued_links(tmp_path, monkeypatch):
    first = "https://vimeo.com/123456"
    second = "https://vimeo.com/789012"
    events = []
    downloads = []

    def fake_download(url, directory, progress):
        downloads.append(url)
        worker.cancel()
        progress(20)
        pytest.fail("Download deveria parar ao receber o cancelamento")

    monkeypatch.setattr("transcreve.web_gui.download_media", fake_download)
    worker = Worker([(first, "first"), (second, "second")], tmp_path, "txt", "economico")
    worker.event.connect(lambda raw: events.append(json.loads(raw)))
    worker.run()
    assert downloads == [first]
    assert events[-1]["type"] == "cancelled"
    assert not list(tmp_path.glob("*.txt"))


@pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") != "windows",
                    reason="QtWebEngine precisa da janela real do Windows para este teste")
def test_web_controls_and_visual_progress(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "sample.wav"
    source.write_bytes(b"sample")
    extra = tmp_path / "extra.wav"
    extra.write_bytes(b"extra")
    destination = tmp_path / "results"
    destination.mkdir()
    choices = iter([str(source), str(source), str(extra)])
    monkeypatch.setattr("transcreve.web_gui.QFileDialog.getOpenFileNames",
                        lambda *_: ([next(choices)], ""))
    monkeypatch.setattr("transcreve.web_gui.QFileDialog.getExistingDirectory",
                        lambda *_: str(destination))
    opened_urls = []
    monkeypatch.setattr("transcreve.web_gui.QDesktopServices.openUrl",
                        lambda url: opened_urls.append(url.toLocalFile()) or True)
    release = Event()

    class FakeTranscriber:
        def __init__(self, config):
            self.config = config

        def transcribe(self, source, output, format_name, progress, cancel=None):
            progress(ProgressEvent("started", 0, 0, 2))
            release.wait(20)
            progress(ProgressEvent("completed", 0, 1, 2, False, 0, 5))
            output.write_text("done")
            progress(ProgressEvent("finished", None, 1, 2))

    monkeypatch.setattr("transcreve.web_gui.Transcriber", FakeTranscriber)
    window = MainWindow()
    bridge_events = []
    window.bridge.changed.connect(lambda raw: bridge_events.append(json.loads(raw)))
    loaded = []
    window.view.loadFinished.connect(loaded.append)
    window.show()
    try:
        wait_for(app, lambda: bool(loaded))
        assert loaded == [True], (window.view.url().toString(),
                                  evaluate(app, window, "document.URL + ' | ' + document.body.innerText.slice(0,300)"))
        wait_for(app, lambda: evaluate(app, window, "document.querySelectorAll('#profile option').length") == 4)

        evaluate(app, window, "document.getElementById('pick-files').click()")
        wait_for(app, lambda: len(window.bridge.files) == 1)
        wait_for(app, lambda: evaluate(app, window, "document.querySelectorAll('.file-row').length") == 1)
        assert evaluate(app, window, "document.querySelectorAll('.file-row').length") == 1
        assert evaluate(app, window, "document.getElementById('start').disabled") is False

        evaluate(app, window, "document.querySelector('.file-row .remove').click()")
        wait_for(app, lambda: not window.bridge.files)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('start').disabled") is True)
        assert evaluate(app, window, "document.getElementById('start').disabled") is True

        evaluate(app, window, "document.getElementById('pick-files').click()")
        wait_for(app, lambda: len(window.bridge.files) == 1)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('add-files').disabled") is False)
        evaluate(app, window, "document.getElementById('add-files').click()")
        wait_for(app, lambda: len(window.bridge.files) == 2)
        wait_for(app, lambda: evaluate(app, window, "document.querySelectorAll('.file-row').length") == 2)
        evaluate(app, window, "document.querySelectorAll('.file-row .remove')[1].click()")
        wait_for(app, lambda: len(window.bridge.files) == 1)
        assert window.bridge.files == [source]
        evaluate(app, window, "document.getElementById('pick-folder').click()")
        wait_for(app, lambda: window.bridge.folder == destination)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('folder-name').textContent") == str(destination))
        assert evaluate(app, window, "document.getElementById('folder-name').textContent") == str(destination)
        evaluate(app, window, "document.getElementById('reset-folder').click()")
        wait_for(app, lambda: window.bridge.folder is None)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('folder-name').textContent") == "Ao lado de cada arquivo")
        evaluate(app, window, "document.getElementById('pick-folder').click()")
        wait_for(app, lambda: window.bridge.folder == destination)

        assert evaluate(app, window, "Array.from(document.querySelectorAll('#profile option')).map(o => o.value).join(',')") == (
            "economico,equilibrado,qualidade,maximo"
        )
        for value in ("economico", "equilibrado", "qualidade", "maximo"):
            evaluate(app, window, f"document.getElementById('profile').value='{value}'; document.getElementById('profile').dispatchEvent(new Event('change'))")
            assert evaluate(app, window, "document.getElementById('profile-help').textContent")
        evaluate(app, window, "document.querySelector('.profiles summary').click()")
        assert evaluate(app, window, "document.querySelector('.profiles').open") is True
        assert evaluate(app, window, "document.querySelectorAll('#profile-comparison p').length") == 4
        evaluate(app, window, "document.getElementById('format').value='txt'; document.getElementById('format').dispatchEvent(new Event('change'))")
        assert evaluate(app, window, "document.getElementById('format-help').textContent")

        evaluate(app, window, "document.getElementById('start').click()")
        wait_for(app, lambda: window.bridge.worker is not None)
        assert window.bridge.worker.profile_name == "maximo"
        assert window.bridge.worker.format_name == "txt"
        wait_for(app, lambda: any(event.get('phase') == 'started' for event in bridge_events))
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('work-status').textContent").startswith("Processando bloco"))
        assert evaluate(app, window, "document.getElementById('work-status').textContent").startswith("Processando bloco"), (
            bridge_events,
            evaluate(app, window, "document.getElementById('action-hint').textContent"),
            evaluate(app, window, "document.getElementById('status-pill').textContent"),
        )
        assert evaluate(app, window, "document.getElementById('work-status').textContent") == "Processando bloco 1/2"
        assert evaluate(app, window, "document.getElementById('action-hint').textContent") == "Processando bloco 1/2"
        assert evaluate(app, window, "document.getElementById('start').disabled") is True
        release.set()
        wait_for(app, lambda: window.bridge.worker is None)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('status-pill').textContent") == "Concluído")
        assert evaluate(app, window, "document.querySelectorAll('.result-row').length") == 1
        assert (destination / "sample.txt").read_text() == "done"
        evaluate(app, window, "document.querySelectorAll('.result-row button')[0].click()")
        evaluate(app, window, "document.querySelectorAll('.result-row button')[1].click()")
        wait_for(app, lambda: len(opened_urls) == 2)
        assert list(map(Path, opened_urls)) == [destination / "sample.txt", destination]
        evaluate(app, window, "document.getElementById('clear-files').click()")
        wait_for(app, lambda: not window.bridge.files)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('start').disabled") is True)
    finally:
        release.set()
        if window.bridge.worker:
            window.bridge.worker.wait(5000)
        window.close()


@pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") != "windows",
                    reason="QtWebEngine precisa da janela real do Windows para este teste")
def test_link_flow_shows_download_then_transcription(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    destination = tmp_path / "results"
    destination.mkdir()
    monkeypatch.setattr("transcreve.web_gui.QFileDialog.getExistingDirectory",
                        lambda *_: str(destination))
    release_download = Event()
    release_model = Event()
    release_transcription = Event()

    def fake_download(url, directory, progress):
        assert url == "https://vimeo.com/123456"
        progress(35)
        release_download.wait(20)
        source = directory / "source.mp3"
        source.write_bytes(b"audio")
        progress(100)
        return source, "Vídeo autorizado"

    class FakeTranscriber:
        def __init__(self, config):
            pass

        def prepare_model(self):
            release_model.wait(20)

        def transcribe(self, source, output, format_name, progress, cancel=None):
            progress(ProgressEvent("started", 0, 0, 2))
            release_transcription.wait(20)
            output.write_text("concluído")
            progress(ProgressEvent("finished", None, 1, 2))

    monkeypatch.setattr("transcreve.web_gui.download_media", fake_download)
    monkeypatch.setattr("transcreve.web_gui.Transcriber", FakeTranscriber)
    window = MainWindow()
    loaded = []
    window.view.loadFinished.connect(loaded.append)
    window.show()
    try:
        wait_for(app, lambda: bool(loaded))
        assert loaded == [True]
        wait_for(app, lambda: evaluate(app, window, "document.querySelectorAll('#format option').length") == 4)
        evaluate(app, window, "document.getElementById('source-url').value='https://vimeo.com/123456'; document.getElementById('add-link').click()")
        wait_for(app, lambda: window.bridge.links == ["https://vimeo.com/123456"])
        wait_for(app, lambda: evaluate(app, window, "document.querySelectorAll('.file-row.link').length") == 1)
        assert evaluate(app, window, "document.getElementById('start').disabled") is True
        assert evaluate(app, window, "document.getElementById('action-hint').textContent") == (
            "Escolha uma pasta de destino para os links."
        )
        evaluate(app, window, "document.getElementById('pick-folder').click()")
        wait_for(app, lambda: window.bridge.folder == destination)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('start').disabled") is False)
        evaluate(app, window, "document.getElementById('start').click()")
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('progress-label').textContent") == "Download")
        assert evaluate(app, window, "document.getElementById('percent').textContent") == "35%"
        assert evaluate(app, window, "document.getElementById('work-status').textContent") == (
            "Conectando ao site e obtendo mídia..."
        )
        release_download.set()
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('work-status').textContent").startswith("Carregando modelo"))
        assert evaluate(app, window, "document.getElementById('progress-label').textContent") == "Modelo"
        release_model.set()
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('work-status').textContent") == "Processando bloco 1/2")
        assert evaluate(app, window, "document.getElementById('progress-label').textContent") == "Transcrição"
        release_transcription.set()
        wait_for(app, lambda: window.bridge.worker is None)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('status-pill').textContent") == "Concluído")
        assert (destination / "vimeo-123456.txt").read_text() == "concluído"
    finally:
        release_download.set()
        release_model.set()
        release_transcription.set()
        if window.bridge.worker:
            window.bridge.worker.wait(5000)
        window.close()


@pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") != "windows",
                    reason="QtWebEngine precisa da janela real do Windows para este teste")
def test_cancel_button_stops_transcription_and_remaining_queue(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    release = Event()
    processed = []

    class FakeTranscriber:
        def __init__(self, config):
            pass

        def transcribe(self, source, output, format_name, progress, cancel=None):
            processed.append(source)
            progress(ProgressEvent("started", 0, 0, 1))
            release.wait(20)
            if cancel and cancel():
                raise CancelledError()
            output.write_text("done")

    monkeypatch.setattr("transcreve.web_gui.Transcriber", FakeTranscriber)
    window = MainWindow()
    loaded = []
    window.view.loadFinished.connect(loaded.append)
    window.show()
    try:
        wait_for(app, lambda: bool(loaded))
        window.bridge.add_paths([first, second])
        wait_for(app, lambda: evaluate(app, window, "document.querySelectorAll('.file-row').length") == 2)
        evaluate(app, window, "document.getElementById('start').click()")
        wait_for(app, lambda: len(processed) == 1)
        wait_for(app, lambda: evaluate(app, window, "!document.getElementById('cancel').classList.contains('hidden')"))
        evaluate(app, window, "document.getElementById('cancel').click()")
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('status-pill').textContent") == "Cancelando")
        assert evaluate(app, window, "document.getElementById('cancel').disabled") is True
        release.set()
        wait_for(app, lambda: window.bridge.worker is None)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('status-pill').textContent") == "Cancelado")
        assert processed == [first]
        assert not (tmp_path / "first.txt").exists()
        assert evaluate(app, window, "document.getElementById('cancel').classList.contains('hidden')") is True
        assert evaluate(app, window, "document.getElementById('start').disabled") is False
    finally:
        release.set()
        if window.bridge.worker:
            window.bridge.worker.wait(5000)
        window.close()


@pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") != "windows",
                    reason="QtWebEngine precisa da janela real do Windows para este teste")
def test_model_preparation_and_offline_controls(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    prepared = set()
    monkeypatch.setattr("transcreve.web_gui.cached_model",
                        lambda model: tmp_path if model in prepared else None)
    monkeypatch.setattr("transcreve.web_gui.model_bytes",
                        lambda model: 123 * 1048576 if model in prepared else None)
    monkeypatch.setattr("transcreve.web_gui.prepare_model",
                        lambda model: prepared.add(model))
    window = MainWindow()
    loaded = []
    window.view.loadFinished.connect(loaded.append)
    window.show()
    try:
        wait_for(app, lambda: bool(loaded))
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('profile').options.length") == 4)
        assert evaluate(app, window, "document.getElementById('model-status').textContent") == "Modelo ainda não foi baixado"
        assert evaluate(app, window, "document.getElementById('selected-model').textContent") == "small"
        assert "244 milhões" in evaluate(app, window, "document.getElementById('model-parameters').textContent")
        assert evaluate(app, window, "document.getElementById('model-disk').textContent") == "Ainda não salvo"
        evaluate(app, window, "document.getElementById('profile').value='maximo'; document.getElementById('profile').dispatchEvent(new Event('change'))")
        assert evaluate(app, window, "document.getElementById('selected-model').textContent") == "large-v3"
        assert "1.550 milhões" in evaluate(app, window, "document.getElementById('model-parameters').textContent")
        evaluate(app, window, "document.getElementById('profile').value='equilibrado'; document.getElementById('profile').dispatchEvent(new Event('change'))")
        assert evaluate(app, window, "document.getElementById('model-info').open") is False
        evaluate(app, window, "document.querySelector('#model-info summary').click()")
        assert evaluate(app, window, "document.getElementById('model-info').open") is True
        assert "Links do YouTube, Vimeo" in evaluate(app, window, "document.querySelector('.model-info-body').textContent")
        source = tmp_path / "audio.wav"
        source.write_bytes(b"audio")
        window.bridge.add_paths([source])
        evaluate(app, window, "document.getElementById('offline-mode').click()")
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('start').disabled") is True)
        evaluate(app, window, "document.getElementById('prepare-model').click()")
        wait_for(app, lambda: "small" in prepared)
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('model-status').textContent") == "Modelo salvo neste computador")
        assert evaluate(app, window, "document.getElementById('prepare-model').classList.contains('hidden')") is True
        assert evaluate(app, window, "document.getElementById('model-saved').classList.contains('hidden')") is False
        assert evaluate(app, window, "document.getElementById('model-saved').textContent.trim()") == "Salvo localmente"
        assert evaluate(app, window, "document.getElementById('model-disk').textContent") == "123 MB neste computador"
        wait_for(app, lambda: evaluate(app, window, "document.getElementById('start').disabled") is False)
    finally:
        if window.bridge.model_worker:
            window.bridge.model_worker.wait(5000)
        window.close()
