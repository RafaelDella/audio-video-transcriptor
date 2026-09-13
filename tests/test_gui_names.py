import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolTip

from transcreve.engine import ProgressEvent
from transcreve.gui import PROFILE_HELP, MainWindow, valid_output_stem


def test_output_name_rejects_paths_and_windows_reserved_names():
    assert valid_output_stem("Entrevista final")
    for name in ("", "../saida", "pasta\\saida", "CON", "LPT1.txt", "nome.", " nome"):
        assert not valid_output_stem(name)


def test_profile_help_and_chunk_status():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    for index in range(window.profile_box.count()):
        name = window.profile_box.itemData(index)
        assert window.profile_box.itemData(index, Qt.ToolTipRole) == PROFILE_HELP[name]
        window.profile_box.setCurrentIndex(index)
        assert window.profile_box.toolTip() == PROFILE_HELP[name]
        assert window.profile_summary.text() == PROFILE_HELP[name]

    window.profile_help_button.click()
    assert "Econômico:" in QToolTip.text()
    assert "Máximo:" in QToolTip.text()
    QToolTip.hideText()

    window.on_progress(ProgressEvent("started", 1, 1, 5))
    assert window.status_label.text() == "Processando bloco 2/5"
    window.on_progress(ProgressEvent("started", 2, 2, None))
    assert window.status_label.text() == "Processando bloco 3/?"
    window.close()
    assert app is not None


def test_file_list_and_activity_states(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    first = tmp_path / "reuniao.ogg"
    second = tmp_path / "aula.mp4"
    first.write_bytes(b"audio")
    second.write_bytes(b"video")

    assert window.activity_empty.isVisible()
    assert not window.bar.isVisible()
    window.add_files([first, second])
    assert window.file_list.count() == 2
    window.select_file(second)
    window.name_edit.setText("aula-final")
    assert window.output_names[second] == "aula-final"
    window.remove_file(first)
    assert window.files == [second]

    window.resize(600, 700)
    app.processEvents()
    assert window.centralWidget().horizontalScrollBar().maximum() == 0
    assert window.config_grid.getItemPosition(1)[:2] == (1, 0)

    window.activity_empty.hide()
    window.activity_work.show()
    window.on_current_file(second.name, 1, 1)
    window.on_progress(ProgressEvent("completed", 0, 1, 2, False, 0, 60))
    assert window.percent_label.text() == "50%"
    window.on_file_done(str(tmp_path / "aula-final.txt"))
    window.on_finished()
    assert window.activity_results.isVisible()
    assert window.results_list.count() == 1
    window.close()
