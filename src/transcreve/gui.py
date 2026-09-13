"""Desktop interface for local transcription."""

from __future__ import annotations

import sys
from pathlib import Path
from string import Template

from PySide6.QtCore import QPoint, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .config import PROFILES, profile
from .engine import ProgressEvent, Transcriber

COLORS = {
    "background": "#F7F8F7",
    "surface": "#FFFFFF",
    "text": "#202923",
    "muted": "#526058",
    "border": "#DCE3DD",
    "accent": "#22753B",
    "accent_hover": "#195E2F",
    "accent_tint": "#ECF5EE",
    "disabled": "#A9BBAE",
    "error": "#A3342A",
}
SPACE = (4, 8, 12, 16, 24, 32, 48)
CONTROL_HEIGHT = 42

STYLE = Template("""
QWidget { color: $text; font-family: 'Segoe UI'; font-size: 14px; }
QMainWindow, QWidget#page, QScrollArea { background: $background; }
QScrollArea { border: 0; }
QFrame#section { background: $surface; border: 1px solid $border; border-radius: 10px; }
QFrame#dropZone { background: #FBFCFB; border: 1px dashed #A8B8AB; border-radius: 8px; }
QFrame#divider { background: $border; max-height: 1px; }
QLabel#appTitle { font-size: 29px; font-weight: 600; }
QLabel#sectionTitle { font-size: 18px; font-weight: 600; }
QLabel#muted, QLabel#helper, QLabel#fileSize { color: $muted; }
QLabel#helper, QLabel#fileSize { font-size: 12px; }
QLabel#error { color: $error; font-size: 13px; }
QLabel#success { color: $accent; font-size: 16px; font-weight: 600; }
QPushButton { background: $surface; border: 1px solid #B9C7BC; border-radius: 8px;
    padding: 0 16px; min-height: 40px; }
QPushButton:hover { background: #F4F8F5; border-color: $accent; }
QPushButton:focus, QComboBox:focus, QLineEdit:focus,
QListWidget:focus, QPlainTextEdit:focus { border: 2px solid $accent; }
QPushButton:disabled { color: #586B5D; background: #EFF2EF; border-color: #D3DCD5; }
QPushButton#primary { background: $accent; color: $surface; border-color: $accent;
    font-weight: 600; min-width: 174px; }
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:disabled { background: $disabled; color: $surface;
    border-color: $disabled; }
QPushButton#textButton { background: transparent; border: 0; color: $accent;
    padding: 0 4px; min-height: 28px; }
QPushButton#textButton:hover { color: $accent_hover; text-decoration: underline; }
QComboBox, QLineEdit { background: $surface; border: 1px solid #B9C7BC;
    border-radius: 8px; padding: 0 12px; min-height: 40px; }
QLineEdit:read-only { background: #F9FAF9; color: $muted; }
QComboBox QAbstractItemView { background: $surface; selection-background-color: $accent_tint; }
QListWidget, QPlainTextEdit { background: $surface; border: 1px solid $border;
    border-radius: 8px; padding: 4px; }
QListWidget::item:selected { background: $accent_tint; color: $text; }
QProgressBar { background: #E4EAE5; border: 0; border-radius: 4px; }
QProgressBar::chunk { background: $accent; border-radius: 4px; }
""").substitute(**COLORS)

PROFILE_HELP = {
    "economico": "Modelo base. Usa menos memória e tende a terminar mais rápido; pode perder detalhes.",
    "equilibrado": "Modelo small. Ponto de partida para a maioria dos arquivos.",
    "qualidade": "Modelo medium. Pode reconhecer melhor falas difíceis, com mais tempo e memória.",
    "maximo": "Modelo large-v3. Maior demanda de memória e processamento; indicado para GPU.",
}
PROFILE_LABELS = {
    "economico": "Econômico",
    "equilibrado": "Equilibrado",
    "qualidade": "Qualidade",
    "maximo": "Máximo",
}
FORMAT_HELP = {
    "txt": "Texto simples, sem marcações de tempo.",
    "srt": "Legendas com tempo, para vídeos e editores.",
    "vtt": "Legendas WebVTT para reprodução na web.",
    "json": "Trechos com tempos e texto em formato estruturado.",
}


def valid_output_stem(name: str) -> bool:
    """Keep output names as safe single-file stems on Windows and other platforms."""
    if not name or name != name.strip(" ."):
        return False
    if any(character in name for character in '<>:"/\\|?*'):
        return False
    if any(ord(character) < 32 for character in name):
        return False
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    return name.split(".")[0].upper() not in reserved


def file_size_text(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def section(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("section")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 20, 24, 24)
    layout.setSpacing(16)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    return frame, layout


def field(label_text: str, control: QWidget, helper: QLabel | None = None,
          buddy: QWidget | None = None) -> QWidget:
    container = QWidget()
    container.setMinimumWidth(0)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    label = QLabel(label_text)
    label.setBuddy(buddy or control)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    layout.addWidget(label)
    layout.addWidget(control)
    if helper is not None:
        helper.setObjectName("helper")
        helper.setWordWrap(True)
        layout.addWidget(helper)
    layout.addStretch()
    return container


class UploadMark(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(32, 32)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(COLORS["accent"]), 2))
        painter.drawLine(16, 5, 16, 21)
        painter.drawLine(10, 11, 16, 5)
        painter.drawLine(16, 5, 22, 11)
        painter.drawLine(5, 20, 5, 27)
        painter.drawLine(5, 27, 27, 27)
        painter.drawLine(27, 27, 27, 20)


class DropZone(QFrame):
    files_added = Signal(list)

    def __init__(self, pick_files):
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(UploadMark(), alignment=Qt.AlignCenter)
        title = QLabel("Arraste áudio ou vídeo para cá")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        hint = QLabel("ou selecione arquivos do computador")
        hint.setObjectName("helper")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        button = QPushButton("Selecionar arquivos")
        button.clicked.connect(pick_files)
        layout.addWidget(button, alignment=Qt.AlignCenter)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        self.files_added.emit([path for path in paths if path.is_file()])
        event.acceptProposedAction()


class FileRow(QWidget):
    selected = Signal(object)
    removed = Signal(object)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(12)
        name = QLabel(path.name)
        name.setToolTip(str(path))
        name.setMinimumWidth(0)
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(name, 1)
        size = QLabel(file_size_text(path.stat().st_size))
        size.setObjectName("fileSize")
        size.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(size)
        self.remove_button = QPushButton("Remover")
        self.remove_button.setObjectName("textButton")
        self.remove_button.setToolTip(f"Remover {path.name} da lista")
        self.remove_button.clicked.connect(lambda: self.removed.emit(self.path))
        layout.addWidget(self.remove_button)

    def mousePressEvent(self, event):
        self.selected.emit(self.path)
        super().mousePressEvent(event)


class FileList(QListWidget):
    files_added = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SingleSelection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        self.files_added.emit([path for path in paths if path.is_file()])
        event.acceptProposedAction()


class TranscriptionWorker(QThread):
    progress = Signal(object)
    current_file = Signal(str, int, int)
    file_done = Signal(str)
    failed = Signal(str)

    def __init__(self, files: list[tuple[Path, str]], output_dir: Path | None, format_name: str,
                 profile_name: str):
        super().__init__()
        self.files = files
        self.output_dir = output_dir
        self.format_name = format_name
        self.profile_name = profile_name

    def run(self):
        try:
            transcriber = Transcriber(profile(self.profile_name))
            for number, (source, stem) in enumerate(self.files, 1):
                self.current_file.emit(source.name, number, len(self.files))
                output = (self.output_dir or source.parent) / f"{stem}.{self.format_name}"
                transcriber.transcribe(source, output, format_name=self.format_name,
                                       progress=self.progress.emit)
                self.file_done.emit(str(output))
        except Exception as error:  # noqa: BLE001 - worker boundary
            self.failed.emit(str(error))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Transcreve Local")
        self.resize(1030, 820)
        self.setMinimumSize(560, 520)
        self.setAcceptDrops(True)
        self.files: list[Path] = []
        self.output_names: dict[Path, str] = {}
        self.output_dir: Path | None = None
        self.worker: TranscriptionWorker | None = None
        self.result_paths: list[Path] = []
        self.failed = False
        self.file_number = 0
        self.file_total = 0

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)
        root = QWidget()
        root.setObjectName("page")
        scroll.setWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(20, 24, 20, 24)
        outer.addStretch(1)
        content = QWidget()
        content.setMaximumWidth(1040)
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        outer.addWidget(content, 8)
        outer.addStretch(1)
        self.main_layout = QVBoxLayout(content)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(16)

        self._build_header()
        self._build_files()
        self._build_config()
        self._build_activity()
        self.main_layout.addStretch()
        self._layout_config_fields()

    def _build_header(self):
        title = QLabel("Transcreve Local")
        title.setObjectName("appTitle")
        self.main_layout.addWidget(title)
        subtitle = QLabel("Áudio e vídeo em texto ou legenda, processados no seu computador.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.main_layout.addWidget(subtitle)

    def _build_files(self):
        frame, layout = section("Arquivos")
        self.drop_zone = DropZone(self.pick_files)
        self.drop_zone.files_added.connect(self.add_files)
        layout.addWidget(self.drop_zone)

        self.files_panel = QWidget()
        files_layout = QVBoxLayout(self.files_panel)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(12)
        self.file_count = QLabel()
        self.file_count.setObjectName("muted")
        files_layout.addWidget(self.file_count)
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.pick_files)
        toolbar.addWidget(self.add_button)
        self.clear_button = QPushButton("Limpar lista")
        self.clear_button.setObjectName("textButton")
        self.clear_button.clicked.connect(self.clear_files)
        toolbar.addWidget(self.clear_button)
        toolbar.addStretch()
        files_layout.addLayout(toolbar)
        self.file_list = FileList()
        self.file_list.files_added.connect(self.add_files)
        self.file_list.currentRowChanged.connect(self.on_file_selected)
        files_layout.addWidget(self.file_list)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nome do arquivo de saída")
        self.name_edit.setToolTip("Altera apenas o resultado; o original permanece igual.")
        self.name_edit.textChanged.connect(self.on_name_changed)
        self.rename_field = field("Nome da transcrição", self.name_edit)
        files_layout.addWidget(self.rename_field)
        self.files_panel.setVisible(False)
        layout.addWidget(self.files_panel)
        self.main_layout.addWidget(frame)

    def _build_config(self):
        frame, layout = section("Configuração")
        self.config_grid = QGridLayout()
        self.config_grid.setContentsMargins(0, 0, 0, 0)
        self.config_grid.setHorizontalSpacing(24)
        self.config_grid.setVerticalSpacing(16)

        self.format_box = QComboBox()
        for format_name in FORMAT_HELP:
            self.format_box.addItem(format_name.upper(), format_name)
        self.format_summary = QLabel()
        self.format_box.currentIndexChanged.connect(self.update_format_help)
        self.format_field = field("Formato de saída", self.format_box, self.format_summary)
        self.update_format_help()

        self.profile_box = QComboBox()
        for name in PROFILES:
            self.profile_box.addItem(PROFILE_LABELS[name], name)
            self.profile_box.setItemData(self.profile_box.count() - 1,
                                         PROFILE_HELP[name], Qt.ToolTipRole)
        self.profile_box.setCurrentIndex(list(PROFILES).index("equilibrado"))
        self.profile_summary = QLabel()
        self.profile_box.currentIndexChanged.connect(self.update_profile_tooltip)
        self.profile_field = QWidget()
        profile_layout = QVBoxLayout(self.profile_field)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(8)
        profile_heading = QHBoxLayout()
        profile_label = QLabel("Perfil de transcrição")
        profile_label.setBuddy(self.profile_box)
        profile_label.setMinimumWidth(0)
        profile_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        profile_heading.addWidget(profile_label)
        profile_heading.addStretch()
        self.profile_help_button = QPushButton("Comparar perfis")
        self.profile_help_button.setObjectName("textButton")
        self.profile_help_button.setToolTip("Compare os quatro perfis de transcrição")
        self.profile_help_button.clicked.connect(self.show_profile_help)
        profile_heading.addWidget(self.profile_help_button)
        profile_layout.addLayout(profile_heading)
        profile_layout.addWidget(self.profile_box)
        self.profile_summary.setObjectName("helper")
        self.profile_summary.setWordWrap(True)
        profile_layout.addWidget(self.profile_summary)
        profile_layout.addStretch()
        self.update_profile_tooltip()
        layout.addLayout(self.config_grid)

        self.folder_edit = QLineEdit("Ao lado de cada arquivo")
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setToolTip("Cada resultado será salvo junto do arquivo de origem.")
        self.folder_button = QPushButton("Escolher")
        self.folder_button.clicked.connect(self.pick_folder)
        folder_control = QWidget()
        folder_row = QHBoxLayout(folder_control)
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(8)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.folder_button)
        layout.addWidget(field("Pasta de destino", folder_control, buddy=self.folder_edit))

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        actions = QHBoxLayout()
        self.action_hint = QLabel("Selecione pelo menos um arquivo para continuar.")
        self.action_hint.setObjectName("helper")
        self.action_hint.setWordWrap(True)
        actions.addWidget(self.action_hint, 1)
        self.start_button = QPushButton("Transcrever arquivos")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        actions.addWidget(self.start_button)
        layout.addLayout(actions)
        self.input_error = QLabel()
        self.input_error.setObjectName("error")
        self.input_error.setWordWrap(True)
        self.input_error.setVisible(False)
        layout.addWidget(self.input_error)
        self.main_layout.addWidget(frame)

    def _build_activity(self):
        frame, layout = section("Atividade")
        self.activity_empty = QLabel(
            "Nenhuma transcrição em andamento. Selecione arquivos e inicie para acompanhar aqui."
        )
        self.activity_empty.setObjectName("muted")
        self.activity_empty.setWordWrap(True)
        layout.addWidget(self.activity_empty)

        self.activity_work = QWidget()
        work_layout = QVBoxLayout(self.activity_work)
        work_layout.setContentsMargins(0, 0, 0, 0)
        work_layout.setSpacing(12)
        self.file_count_label = QLabel()
        self.file_count_label.setObjectName("muted")
        work_layout.addWidget(self.file_count_label)
        self.current_file_label = QLabel()
        self.current_file_label.setWordWrap(True)
        work_layout.addWidget(self.current_file_label)
        self.status_label = QLabel()
        self.status_label.setObjectName("muted")
        work_layout.addWidget(self.status_label)
        progress_row = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        progress_row.addWidget(self.bar, 1)
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("muted")
        progress_row.addWidget(self.percent_label)
        work_layout.addLayout(progress_row)
        self.global_label = QLabel("Progresso total")
        self.global_label.setObjectName("helper")
        work_layout.addWidget(self.global_label)
        self.global_bar = QProgressBar()
        self.global_bar.setTextVisible(False)
        self.global_bar.setFixedHeight(8)
        work_layout.addWidget(self.global_bar)
        self.global_label.setVisible(False)
        self.global_bar.setVisible(False)
        log_label = QLabel("Log")
        log_label.setObjectName("helper")
        work_layout.addWidget(log_label)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(112)
        work_layout.addWidget(self.log)
        self.activity_work.setVisible(False)
        layout.addWidget(self.activity_work)

        self.activity_results = QWidget()
        results_layout = QVBoxLayout(self.activity_results)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(12)
        self.result_title = QLabel("Transcrição concluída")
        self.result_title.setObjectName("success")
        results_layout.addWidget(self.result_title)
        self.results_list = QListWidget()
        self.results_list.setFixedHeight(92)
        results_layout.addWidget(self.results_list)
        result_actions = QHBoxLayout()
        self.open_file_button = QPushButton("Abrir arquivo")
        self.open_file_button.clicked.connect(self.open_result)
        result_actions.addWidget(self.open_file_button)
        self.open_folder_button = QPushButton("Abrir pasta")
        self.open_folder_button.clicked.connect(self.open_result_folder)
        result_actions.addWidget(self.open_folder_button)
        result_actions.addStretch()
        results_layout.addLayout(result_actions)
        self.activity_results.setVisible(False)
        layout.addWidget(self.activity_results)
        self.main_layout.addWidget(frame)

    def _layout_config_fields(self):
        if not hasattr(self, "config_grid"):
            return
        narrow = self.width() < 760
        if getattr(self, "_narrow_config", None) == narrow:
            return
        self._narrow_config = narrow
        self.config_grid.removeWidget(self.format_field)
        self.config_grid.removeWidget(self.profile_field)
        self.config_grid.addWidget(self.format_field, 0, 0)
        self.config_grid.addWidget(self.profile_field, 1 if narrow else 0,
                                   0 if narrow else 1)
        self.config_grid.setColumnStretch(0, 1)
        self.config_grid.setColumnStretch(1, 0 if narrow else 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_config_fields()

    def _refresh_files(self):
        has_files = bool(self.files)
        self.drop_zone.setVisible(not has_files)
        self.files_panel.setVisible(has_files)
        self.start_button.setEnabled(has_files and self.worker is None)
        self.action_hint.setText("" if has_files else "Selecione pelo menos um arquivo para continuar.")
        self.file_count.setText(f"{len(self.files)} arquivo(s) selecionado(s)")
        self.file_list.setFixedHeight(min(184, max(48, 48 * len(self.files) + 8)))
        if has_files and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def add_files(self, paths):
        for path in paths:
            if path.is_file() and path not in self.files:
                self.files.append(path)
                self.output_names[path] = path.stem
                row = FileRow(path)
                item = QListWidgetItem()
                item.setSizeHint(row.sizeHint())
                item.setToolTip(str(path))
                self.file_list.addItem(item)
                row.selected.connect(self.select_file)
                row.removed.connect(self.remove_file)
                self.file_list.setItemWidget(item, row)
        self._refresh_files()

    def select_file(self, path: Path):
        if path in self.files:
            self.file_list.setCurrentRow(self.files.index(path))

    def remove_file(self, path: Path):
        if self.worker is not None or path not in self.files:
            return
        row = self.files.index(path)
        self.files.pop(row)
        self.output_names.pop(path)
        self.file_list.takeItem(row)
        self._refresh_files()

    def on_file_selected(self, row: int):
        self.name_edit.blockSignals(True)
        self.name_edit.setText(self.output_names[self.files[row]] if 0 <= row < len(self.files)
                               else "")
        self.name_edit.blockSignals(False)

    def on_name_changed(self, name: str):
        row = self.file_list.currentRow()
        if 0 <= row < len(self.files):
            self.output_names[self.files[row]] = name

    def update_format_help(self):
        self.format_summary.setText(FORMAT_HELP[self.format_box.currentData()])

    def update_profile_tooltip(self):
        name = self.profile_box.currentData()
        self.profile_box.setToolTip(PROFILE_HELP[name])
        self.profile_summary.setText(PROFILE_HELP[name])

    def show_profile_help(self):
        descriptions = "\n".join(
            f"{PROFILE_LABELS[name]}: {description}"
            for name, description in PROFILE_HELP.items()
        )
        position = self.profile_help_button.mapToGlobal(QPoint(0, self.profile_help_button.height()))
        QToolTip.showText(position, descriptions, self.profile_help_button)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self.worker is None:
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        self.add_files(paths)
        event.acceptProposedAction()

    def pick_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Selecionar arquivos")
        self.add_files([Path(name) for name in names])

    def clear_files(self):
        self.files.clear()
        self.output_names.clear()
        self.file_list.clear()
        self._refresh_files()

    def pick_folder(self):
        name = QFileDialog.getExistingDirectory(self, "Escolher pasta de destino")
        if name:
            self.output_dir = Path(name)
            self.folder_edit.setText(name)
            self.folder_edit.setToolTip(name)

    def _show_input_error(self, message: str):
        self.input_error.setText(message)
        self.input_error.setVisible(True)

    def start(self):
        if not self.files:
            return
        outputs = []
        for source in self.files:
            stem = self.output_names[source]
            if not valid_output_stem(stem):
                self.select_file(source)
                self._show_input_error("Informe um nome válido para a transcrição selecionada.")
                self.name_edit.setFocus()
                return
            outputs.append((self.output_dir or source.parent) /
                           f"{stem}.{self.format_box.currentData()}")
        if len(set(outputs)) != len(outputs):
            self._show_input_error("Dois arquivos produziriam a mesma saída. Altere um nome.")
            return
        self.input_error.setVisible(False)
        self.result_paths.clear()
        self.results_list.clear()
        self.failed = False
        self.log.clear()
        self.activity_empty.setVisible(False)
        self.activity_results.setVisible(False)
        self.activity_work.setVisible(True)
        self._set_busy(True)
        jobs = [(source, self.output_names[source]) for source in self.files]
        self.worker = TranscriptionWorker(jobs, self.output_dir,
                                          self.format_box.currentData(),
                                          self.profile_box.currentData())
        self.worker.current_file.connect(self.on_current_file)
        self.worker.progress.connect(self.on_progress)
        self.worker.file_done.connect(self.on_file_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def _set_busy(self, busy: bool):
        self.start_button.setEnabled(not busy and bool(self.files))
        self.add_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)
        self.drop_zone.setAcceptDrops(not busy)
        self.file_list.setAcceptDrops(not busy)
        self.name_edit.setEnabled(not busy)
        self.format_box.setEnabled(not busy)
        self.profile_box.setEnabled(not busy)
        for row in range(self.file_list.count()):
            widget = self.file_list.itemWidget(self.file_list.item(row))
            widget.remove_button.setEnabled(not busy)

    def on_current_file(self, name, number, total):
        self.file_number = number
        self.file_total = total
        self.file_count_label.setText(f"Arquivo {number} de {total}")
        self.current_file_label.setText(name)
        self.status_label.setText("Preparando modelo e áudio...")
        self.log.appendPlainText(f"Preparando: {name}")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.percent_label.setText("0%")
        self.global_label.setVisible(total > 1)
        self.global_bar.setVisible(total > 1)
        if total > 1:
            self.global_bar.setValue(round(100 * (number - 1) / total))

    def on_progress(self, event: ProgressEvent):
        if event.phase == "started":
            total = str(event.total_chunks) if event.total_chunks is not None else "?"
            self.status_label.setText(f"Processando bloco {event.chunk_index + 1}/{total}")
            self.status_label.setToolTip("Total estimado pela duração do arquivo.")
            if event.total_chunks is None:
                self.bar.setRange(0, 0)
                self.percent_label.setText("—")
        elif event.phase == "completed":
            if event.total_chunks:
                fraction = min(0.99, event.completed_chunks / event.total_chunks)
                percent = round(100 * fraction)
                self.bar.setValue(percent)
                self.percent_label.setText(f"{percent}%")
                if self.file_total > 1:
                    global_fraction = (self.file_number - 1 + fraction) / self.file_total
                    self.global_bar.setValue(round(100 * global_fraction))
            action = "Retomado" if event.skipped else "Concluído"
            self.log.appendPlainText(
                f"{action} bloco {event.chunk_index + 1} ({event.end_seconds:.1f}s de áudio)"
            )
        elif event.phase == "finished":
            self.bar.setRange(0, 100)
            self.bar.setValue(100)
            self.percent_label.setText("100%")

    def on_file_done(self, path: str):
        output = Path(path)
        self.result_paths.append(output)
        self.results_list.addItem(output.name)
        self.results_list.setCurrentRow(self.results_list.count() - 1)
        self.log.appendPlainText(f"Concluído: {path}")
        if self.file_total > 1:
            self.global_bar.setValue(round(100 * self.file_number / self.file_total))

    def on_failed(self, message: str):
        self.failed = True
        self.status_label.setText("Falha na transcrição")
        self.log.appendPlainText(f"Erro: {message}")
        if self.result_paths:
            self.result_title.setText("Arquivos concluídos antes da falha")
            self.activity_results.setVisible(True)

    def on_finished(self):
        if not self.failed:
            self.status_label.setText("Transcrição concluída")
            self.result_title.setText("Transcrição concluída")
            self.activity_results.setVisible(bool(self.result_paths))
        self.worker = None
        self._set_busy(False)

    def _selected_result(self) -> Path | None:
        row = self.results_list.currentRow()
        return self.result_paths[row] if 0 <= row < len(self.result_paths) else None

    def open_result(self):
        if output := self._selected_result():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output)))

    def open_result_folder(self):
        if output := self._selected_result():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output.parent)))


def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
