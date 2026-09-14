"""HTML desktop interface backed by the existing local transcription engine."""

from __future__ import annotations

import json
import sys
import tempfile
from concurrent.futures import CancelledError
from contextlib import ExitStack
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

from .config import PROFILES, profile
from .engine import ProgressEvent, Transcriber
from .model_store import cached_model, model_bytes, prepare_model
from .remote import download_media, source_name, validate_url
from .ui_options import FORMAT_HELP, MODEL_DETAILS, PROFILE_HELP, PROFILE_LABELS, valid_output_stem


class Worker(QThread):
    event = Signal(str)

    def __init__(self, jobs: list[tuple[Path | str, str]], folder: Path | None,
                 format_name: str, profile_name: str, offline: bool = False):
        super().__init__()
        self.jobs, self.folder = jobs, folder
        self.format_name, self.profile_name = format_name, profile_name
        self.offline = offline
        self.cancel_requested = Event()

    def cancel(self):
        self.cancel_requested.set()

    def check_cancel(self):
        if self.cancel_requested.is_set():
            raise CancelledError()

    def run(self):
        try:
            configuration = profile(self.profile_name)
            transcriber = (Transcriber(configuration, offline=True) if self.offline
                           else Transcriber(configuration))
            model_ready = False
            for number, (source, stem) in enumerate(self.jobs, 1):
                self.check_cancel()
                label = source.name if isinstance(source, Path) else source_name(source)[0]
                self.event.emit(json.dumps({"type": "current", "name": label,
                                            "number": number, "total": len(self.jobs)}))
                output_folder = self.folder or source.parent
                output = output_folder / f"{stem}.{self.format_name}"
                with ExitStack() as stack:
                    if isinstance(source, str):
                        temporary = Path(stack.enter_context(
                            tempfile.TemporaryDirectory(prefix="transcreve-source-")))
                        self.event.emit(json.dumps({"type": "download", "percent": None}))

                        def report_download(percent):
                            self.check_cancel()
                            self.event.emit(json.dumps({"type": "download", "percent": percent}))

                        source, title = download_media(source, temporary, report_download)
                        self.check_cancel()
                        self.event.emit(json.dumps({"type": "downloaded", "name": title}))

                    if not model_ready and hasattr(transcriber, "prepare_model"):
                        self.event.emit(json.dumps({"type": "model_loading",
                                                    "model": configuration.model,
                                                    "profile": self.profile_name}))
                        transcriber.prepare_model()
                        self.check_cancel()
                        model_ready = True
                        self.event.emit(json.dumps({"type": "model_ready"}))

                    def report(progress: ProgressEvent):
                        if progress.phase != "finished":
                            self.check_cancel()
                        self.event.emit(json.dumps({"type": "progress", "phase": progress.phase,
                            "chunk": progress.chunk_index + 1 if progress.chunk_index is not None else None,
                            "done": progress.completed_chunks,
                            "total": progress.total_chunks,
                            "skipped": progress.skipped,
                            "seconds": progress.end_seconds}))

                    transcriber.transcribe(source, output, format_name=self.format_name,
                                           progress=report, cancel=self.cancel_requested.is_set)
                self.event.emit(json.dumps({"type": "result", "path": str(output)}))
                self.check_cancel()
        except CancelledError:
            self.event.emit(json.dumps({"type": "cancelled"}))
        except Exception as error:  # noqa: BLE001 - thread boundary
            if self.cancel_requested.is_set():
                self.event.emit(json.dumps({"type": "cancelled"}))
            else:
                self.event.emit(json.dumps({"type": "error", "message": str(error)}))


class ModelWorker(QThread):
    event = Signal(str)

    def __init__(self, model: str):
        super().__init__()
        self.model = model

    def run(self):
        try:
            prepare_model(self.model)
            self.event.emit(json.dumps({"type": "model_prepared", "model": self.model,
                                        "bytes": model_bytes(self.model)}))
        except Exception as error:  # noqa: BLE001 - thread boundary
            self.event.emit(json.dumps({"type": "model_prepare_error",
                                        "message": str(error)}))


class Bridge(QObject):
    changed = Signal(str)

    def __init__(self, window: QMainWindow):
        super().__init__()
        self.window = window
        self.files: list[Path] = []
        self.links: list[str] = []
        self.names: dict[Path | str, str] = {}
        self.folder: Path | None = None
        self.worker: Worker | None = None
        self.model_worker: ModelWorker | None = None
        self.pending: list[dict] = []

    def send(self, data: dict):
        self.pending.append(data)
        self.changed.emit(json.dumps(data, ensure_ascii=False))

    @Slot(result=str)
    def take_events(self) -> str:
        events = self.pending
        self.pending = []
        return json.dumps(events, ensure_ascii=False)

    def state(self):
        self.send({"type": "state", "files": [
            {"path": str(path), "name": path.name, "stem": self.names[path],
             "size": path.stat().st_size, "kind": "file", "origin": "Computador"}
            for path in self.files] + [
            {"path": url, "name": source_name(url)[0], "stem": self.names[url],
             "size": None, "kind": "link", "origin": source_name(url)[2]}
            for url in self.links],
            "folder": str(self.folder) if self.folder else "",
            "busy": self.worker is not None,
            "preparing_model": self.model_worker is not None})

    def add_paths(self, paths):
        if self.worker:
            return
        for path in map(Path, paths):
            if path.is_file() and path not in self.files:
                self.files.append(path)
                self.names[path] = path.stem
        self.state()

    @Slot(str)
    def add_url(self, value: str):
        if self.worker:
            return
        try:
            url = validate_url(value)
        except ValueError as error:
            self.send({"type": "input_error", "message": str(error)})
            return
        if url not in self.links:
            self.links.append(url)
            self.names[url] = source_name(url)[1]
        self.state()

    @Slot()
    def ready(self):
        self.send({"type": "options", "profiles": [
            {"value": key, "label": PROFILE_LABELS[key], "help": PROFILE_HELP[key],
             "model": PROFILES[key].model, "details": MODEL_DETAILS[key],
             "bytes": model_bytes(PROFILES[key].model)}
            for key in PROFILES], "formats": FORMAT_HELP,
            "cached_models": {key: bool(cached_model(config.model))
                              for key, config in PROFILES.items()}})
        self.state()

    @Slot(str)
    def prepare_selected_model(self, profile_name: str):
        if self.worker or self.model_worker or profile_name not in PROFILES:
            return
        model = PROFILES[profile_name].model
        if cached_model(model):
            self.send({"type": "model_prepared", "model": model,
                       "bytes": model_bytes(model)})
            return
        self.model_worker = ModelWorker(model)
        self.model_worker.event.connect(self._worker_event)
        self.model_worker.finished.connect(self._model_finished)
        self.send({"type": "model_preparing", "model": model})
        self.state()
        self.model_worker.start()

    def _model_finished(self):
        self.model_worker = None
        self.state()

    @Slot()
    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self.window, "Selecionar áudio ou vídeo")
        self.add_paths(paths)

    @Slot()
    def pick_folder(self):
        if self.worker:
            return
        folder = QFileDialog.getExistingDirectory(self.window, "Pasta de destino")
        if folder:
            self.folder = Path(folder)
            self.state()

    @Slot()
    def reset_folder(self):
        if not self.worker:
            self.folder = None
            self.state()

    @Slot(str)
    def remove_file(self, path: str):
        if self.worker:
            return
        if path in self.links:
            self.links.remove(path)
            self.names.pop(path)
        else:
            source = Path(path)
            if source not in self.files:
                return
            self.files.remove(source)
            self.names.pop(source)
        self.state()

    @Slot()
    def clear_files(self):
        if not self.worker:
            self.files.clear()
            self.links.clear()
            self.names.clear()
            self.state()

    @Slot(str, str)
    def rename_file(self, path: str, stem: str):
        source = path if path in self.links else Path(path)
        if not self.worker and source in self.names:
            self.names[source] = stem

    @Slot(str, str, bool)
    def start(self, format_name: str, profile_name: str, offline: bool = False):
        if self.worker or self.model_worker or not (self.files or self.links):
            return
        if format_name not in FORMAT_HELP or profile_name not in PROFILES:
            self.send({"type": "input_error", "message": "Escolha um formato e perfil válidos."})
            return
        if self.links and self.folder is None:
            self.send({"type": "input_error", "message":
                       "Escolha uma pasta de destino para transcrições de links."})
            return
        if offline and self.links:
            self.send({"type": "input_error", "message":
                       "Remova os links para transcrever totalmente offline."})
            return
        if offline and not cached_model(PROFILES[profile_name].model):
            self.send({"type": "input_error", "message":
                       "Prepare o modelo selecionado antes de transcrever offline."})
            return
        outputs = []
        for source in [*self.files, *self.links]:
            stem = self.names[source]
            if not valid_output_stem(stem):
                self.send({"type": "input_error", "message":
                           f"Informe um nome válido para {source_name(source)[0] if isinstance(source, str) else source.name}.",
                           "path": str(source)})
                return
            outputs.append((self.folder or source.parent) / f"{stem}.{format_name}")
        if len(outputs) != len(set(outputs)):
            self.send({"type": "input_error", "message":
                       "Dois arquivos produziriam a mesma saída. Altere um nome."})
            return
        self.worker = Worker([(source, self.names[source]) for source in [*self.files, *self.links]],
                             self.folder, format_name, profile_name, offline)
        self.worker.event.connect(self._worker_event)
        self.worker.finished.connect(self._finished)
        QTimer.singleShot(0, self._begin_worker)

    def _begin_worker(self):
        self.send({"type": "started"})
        self.state()
        self.worker.start()

    @Slot()
    def cancel(self):
        if self.worker and not self.worker.cancel_requested.is_set():
            self.worker.cancel()
            self.send({"type": "cancelling"})

    @Slot(str)
    def _worker_event(self, raw: str):
        self.send(json.loads(raw))

    def _finished(self):
        self.worker = None
        self.send({"type": "finished"})
        self.state()

    @Slot(str, bool)
    def open_result(self, path: str, folder: bool):
        target = Path(path)
        if target.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent if folder else target)))


class WebView(QWebEngineView):
    def __init__(self, bridge: Bridge):
        super().__init__()
        self.bridge = bridge
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.bridge.worker:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls() and not self.bridge.worker:
            self.bridge.add_paths(url.toLocalFile() for url in event.mimeData().urls())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Transcreve Local")
        self.resize(1160, 820)
        self.setMinimumSize(640, 540)
        self.bridge = Bridge(self)
        self.view = WebView(self.bridge)
        channel = QWebChannel(self.view.page())
        channel.registerObject("backend", self.bridge)
        self.view.page().setWebChannel(channel)
        self.setCentralWidget(self.view)
        self.view.load(QUrl.fromLocalFile(str(Path(__file__).parent / "web" / "index.html")))


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
