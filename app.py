from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


APP_TITLE = "File Renamer"
HISTORY_FILE = Path(__file__).with_name(".file_renamer_history.json")
APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #0f141a;
    color: #d7dee7;
    font-family: "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 12px;
}
QGroupBox {
    background: #161d24;
    border: 1px solid #283341;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox:disabled {
    background: #11161c;
    border: 1px solid #1d2631;
    color: #5b6674;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #aeb9c7;
}
QGroupBox::title:disabled {
    color: #5b6674;
}
QLineEdit, QPlainTextEdit, QTreeWidget {
    background: #121920;
    border: 1px solid #2d3948;
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: #2f81f7;
    selection-color: #f5f9ff;
}
QLineEdit:focus, QPlainTextEdit:focus, QTreeWidget:focus {
    border: 1px solid #4c8dff;
}
QLineEdit:disabled, QPlainTextEdit:disabled {
    background: #0f141a;
    border: 1px solid #1d2631;
    color: #617080;
}
QPushButton {
    background: #202a35;
    color: #e8eef6;
    border: 1px solid #304055;
    border-radius: 8px;
    padding: 4px 10px;
    min-height: 26px;
    font-weight: 600;
}
QPushButton:hover {
    background: #273444;
    border: 1px solid #3a4d67;
}
QPushButton:pressed {
    background: #18222d;
}
QPushButton:disabled {
    background: #161d24;
    color: #738091;
    border: 1px solid #243140;
}
QPushButton[variant="primary"] {
    background: #2f81f7;
    color: #f5f9ff;
    border: 1px solid #4c8dff;
}
QPushButton[variant="primary"]:hover {
    background: #2674e8;
}
QPushButton[variant="danger"] {
    background: #2b1f24;
    color: #ffb4bf;
    border: 1px solid #5a303d;
}
QRadioButton, QCheckBox, QLabel {
    color: #d7dee7;
}
QRadioButton:disabled, QCheckBox:disabled, QLabel:disabled {
    color: #5b6674;
}
QHeaderView::section {
    background: #182029;
    color: #96a4b5;
    border: none;
    border-bottom: 1px solid #2d3948;
    padding: 8px 10px;
    font-weight: 700;
}
QTreeWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #182029;
}
QTreeWidget::item:selected {
    background: #1d2b3b;
    color: #f5f9ff;
}
QScrollBar:vertical {
    background: #111821;
    width: 10px;
    margin: 4px;
}
QScrollBar::handle:vertical {
    background: #334154;
    min-height: 28px;
    border-radius: 5px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QMenuBar {
    background: #0f141a;
    color: #d7dee7;
}
QMenuBar::item:selected {
    background: #182029;
    border-radius: 4px;
}
"""


@dataclass
class RenameRecord:
    source: str
    destination: str


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[RenameRecord]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, dict):
            return []
        records = data.get("last_batch", [])
        if not isinstance(records, list):
            return []
        output: list[RenameRecord] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            destination = item.get("destination")
            if isinstance(source, str) and isinstance(destination, str):
                output.append(RenameRecord(source=source, destination=destination))
        return output

    def save(self, records: list[RenameRecord]) -> None:
        payload = {"last_batch": [asdict(record) for record in records]}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class FilePairTreeWidget(QTreeWidget):
    files_dropped = Signal(list)
    order_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setColumnCount(2)
        self.setHeaderLabels(["Source Files", "Preview New Names"])
        self.setAcceptDrops(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setIndentation(0)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        urls = event.mimeData().urls()
        paths = []
        for url in urls:
            local_file = url.toLocalFile()
            if local_file:
                paths.append(local_file)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        self.order_changed.emit()


class RenameEngine:
    @staticmethod
    def wildcard_to_regex(pattern: str) -> re.Pattern[str]:
        chunks: list[str] = []
        for char in pattern:
            if char == "*":
                chunks.append("(.*)")
            elif char == "?":
                chunks.append("(.)")
            else:
                chunks.append(re.escape(char))
        return re.compile(f"^{''.join(chunks)}$")

    @staticmethod
    def build_replacement(replacement: str, captured: list[str]) -> str:
        if captured:
            parts = replacement.split("*")
            rebuilt = []
            for index, part in enumerate(parts):
                rebuilt.append(part)
                if index < len(parts) - 1:
                    rebuilt.append(captured[index] if index < len(captured) else "")
            candidate = "".join(rebuilt)
        else:
            candidate = replacement

        for idx, value in enumerate(captured, start=1):
            candidate = candidate.replace(f"{{{idx}}}", value)
        return candidate

    @staticmethod
    def apply_pattern(name: str, search: str, replacement: str) -> str:
        if not search:
            return name

        if "*" not in search and "?" not in search:
            return name.replace(search, replacement)

        regex = RenameEngine.wildcard_to_regex(search)
        match = regex.search(name)
        if not match or match.start() == match.end():
            return name

        captured = list(match.groups())
        candidate = RenameEngine.build_replacement(replacement, captured)
        return f"{name[:match.start()]}{candidate}{name[match.end():]}"

    @staticmethod
    def build_destination(
        source_path: Path,
        new_name: str,
        target_text: str,
        rename_in_place: bool,
    ) -> Path:
        if rename_in_place:
            return source_path.with_name(new_name)

        target_path = Path(target_text).expanduser() if target_text else Path("renamed")
        if not target_path.is_absolute():
            target_path = source_path.parent / target_path
        return target_path / new_name

    @staticmethod
    def apply_sequence_pattern(pattern: str, index: int, suffix: str) -> str:
        sequence_pattern = pattern or "sequence.####.ext"
        ext_value = suffix or ""

        def replace_hashes(match: re.Match[str]) -> str:
            width = len(match.group(0))
            return str(index).zfill(width)

        name = re.sub(r"#+", replace_hashes, sequence_pattern, count=1)
        name = name.replace(".ext", ext_value)
        name = name.replace("{ext}", ext_value.lstrip("."))
        if ".ext" not in sequence_pattern and "{ext}" not in sequence_pattern and ext_value:
            name = f"{name}{ext_value}"
        return name


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 760)

        self.history_store = HistoryStore(HISTORY_FILE)
        self.last_batch = self.history_store.load()
        self.source_files: list[Path] = []

        self._build_ui()
        self.setStyleSheet(APP_STYLESHEET)
        self._apply_table_fonts()
        self.refresh_preview()
        self._update_undo_state()

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        title = QLabel("File Renamer")
        title.setStyleSheet("font-size: 28px; font-weight: 700; color: #f4f7fb;")
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_controls_panel())
        splitter.addWidget(self._build_source_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.setSizes([340, 480, 480])

        root_layout.addWidget(title)
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        exit_action = QAction("Quit", self)
        exit_action.triggered.connect(self.close)
        self.menuBar().addAction(exit_action)

    def _build_controls_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)

        add_button = QPushButton("Add Files")
        add_button.clicked.connect(self.pick_files)

        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_selected_files)
        remove_button.setProperty("variant", "danger")

        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self.clear_files)
        clear_button.setProperty("variant", "danger")

        self.status_label = QLabel("No files loaded.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("padding: 4px 2px; color: #8a98a8;")

        mode_group = QGroupBox("Rename Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.search_mode_radio = QRadioButton("Search and Replace")
        self.sequence_mode_radio = QRadioButton("Rename to Sequence")
        self.search_mode_radio.setChecked(True)
        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.addButton(self.search_mode_radio)
        self.mode_button_group.addButton(self.sequence_mode_radio)
        self.search_mode_radio.toggled.connect(self.refresh_preview)
        self.sequence_mode_radio.toggled.connect(self.refresh_preview)

        mode_layout.addWidget(self.search_mode_radio)
        mode_layout.addWidget(self.sequence_mode_radio)

        form_group = QGroupBox("Search and Replace")
        self.search_group = form_group
        form_layout = QFormLayout(form_group)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("example: IMG_* or draft_??")
        self.search_input.textChanged.connect(self.refresh_preview)

        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("example: project_* or final_{1}")
        self.replace_input.textChanged.connect(self.refresh_preview)

        self.target_input = QLineEdit("renamed")
        self.target_input.setPlaceholderText("renamed")
        self.target_input.textChanged.connect(self.refresh_preview)

        self.rename_in_place_checkbox = QCheckBox("Rename in place")
        self.rename_in_place_checkbox.toggled.connect(self._toggle_target_enabled)
        self.rename_in_place_checkbox.toggled.connect(self.refresh_preview)

        self.allow_overwrite_checkbox = QCheckBox("Allow overwrite existing files")
        self.allow_overwrite_checkbox.toggled.connect(self.refresh_preview)

        form_layout.addRow("Search", self.search_input)
        form_layout.addRow("Replace", self.replace_input)
        form_layout.addRow("Target Folder", self.target_input)
        form_layout.addRow("", self.rename_in_place_checkbox)
        form_layout.addRow("", self.allow_overwrite_checkbox)

        sequence_group = QGroupBox("Rename to Sequence")
        self.sequence_group = sequence_group
        sequence_form = QFormLayout(sequence_group)

        self.sequence_pattern_input = QLineEdit("sequence.####.ext")
        self.sequence_pattern_input.setPlaceholderText("sequence.####.ext")
        self.sequence_pattern_input.textChanged.connect(self.refresh_preview)

        self.sequence_target_input = QLineEdit("sequence")
        self.sequence_target_input.setPlaceholderText("sequence")
        self.sequence_target_input.textChanged.connect(self.refresh_preview)

        sequence_form.addRow("Naming Pattern", self.sequence_pattern_input)
        sequence_form.addRow("Target Folder", self.sequence_target_input)

        help_box = QPlainTextEdit()
        help_box.setReadOnly(True)
        help_box.setPlainText(
            "Wildcard help:\n"
            "* matches any run of characters\n"
            "? matches a single character\n"
            "Use * in Replace to reinsert wildcard captures in order\n"
            "You can also use {1}, {2}, ... for explicit captured values"
        )
        help_box.setMaximumHeight(120)
        help_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        rename_button = QPushButton("Rename Files")
        rename_button.clicked.connect(self.rename_files)
        rename_button.setProperty("variant", "primary")

        undo_button = QPushButton("Undo Last Rename")
        undo_button.clicked.connect(self.undo_last_rename)
        self.undo_button = undo_button

        utility_row = QHBoxLayout()
        utility_row.setSpacing(8)
        utility_row.addWidget(add_button)
        utility_row.addWidget(remove_button)
        utility_row.addWidget(clear_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(rename_button)
        action_row.addWidget(undo_button)

        layout.addWidget(mode_group)
        layout.addWidget(form_group)
        layout.addWidget(sequence_group)
        layout.addWidget(help_box)
        layout.addLayout(utility_row)
        layout.addLayout(action_row)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        self._update_mode_sections()
        return panel

    def _build_source_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        title = QLabel("Source Files")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f4f7fb;")

        self.file_tree = FilePairTreeWidget()
        self.file_tree.setColumnCount(1)
        self.file_tree.setHeaderLabels(["Source Files"])
        self.file_tree.setHeaderHidden(True)
        self.file_tree.files_dropped.connect(self.add_files)
        self.file_tree.order_changed.connect(self.sync_source_order_from_view)

        layout.addWidget(title)
        layout.addWidget(self.file_tree)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        title = QLabel("Preview New Names")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f4f7fb;")

        self.preview_tree = QTreeWidget()
        self.preview_tree.setColumnCount(1)
        self.preview_tree.setHeaderLabels(["Preview New Names"])
        self.preview_tree.setHeaderHidden(True)
        self.preview_tree.setRootIsDecorated(False)
        self.preview_tree.setUniformRowHeights(True)
        self.preview_tree.setIndentation(0)
        self.preview_tree.setAlternatingRowColors(True)
        self.preview_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.preview_tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.preview_tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.file_tree.verticalScrollBar().valueChanged.connect(
            self.preview_tree.verticalScrollBar().setValue
        )
        self.preview_tree.verticalScrollBar().valueChanged.connect(
            self.file_tree.verticalScrollBar().setValue
        )

        layout.addWidget(title)
        layout.addWidget(self.preview_tree)
        return panel

    def _apply_table_fonts(self) -> None:
        list_font = QFont("SF Mono")
        list_font.setStyleHint(QFont.Monospace)
        list_font.setPointSize(11)
        self.file_tree.setFont(list_font)
        self.preview_tree.setFont(list_font)

    def _toggle_target_enabled(self, _checked: bool) -> None:
        rename_in_place = self.rename_in_place_checkbox.isChecked()
        self.target_input.setEnabled(not rename_in_place)

    def _update_mode_sections(self) -> None:
        is_search_mode = self.search_mode_radio.isChecked()
        self.search_group.setEnabled(is_search_mode)
        self.sequence_group.setEnabled(not is_search_mode)

    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select files")
        if files:
            self.add_files(files)

    def add_files(self, paths: list[str]) -> None:
        seen = {path.resolve() for path in self.source_files}
        for path_text in paths:
            path = Path(path_text).expanduser()
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            self.source_files.append(path)
            seen.add(resolved)
        self._sync_file_view()
        self.refresh_preview()

    def remove_selected_files(self) -> None:
        selected_paths = {
            Path(item.data(0, Qt.UserRole))
            for item in self.file_tree.selectedItems()
            if item.data(0, Qt.UserRole)
        }
        if not selected_paths:
            return
        self.source_files = [path for path in self.source_files if path not in selected_paths]
        self._sync_file_view()
        self.refresh_preview()

    def clear_files(self) -> None:
        self.source_files.clear()
        self._sync_file_view()
        self.refresh_preview()

    def _sync_file_view(self) -> None:
        self.file_tree.clear()
        self.preview_tree.clear()
        for path in self.source_files:
            item = QTreeWidgetItem([str(path)])
            item.setData(0, Qt.UserRole, str(path))
            self.file_tree.addTopLevelItem(item)
            self.preview_tree.addTopLevelItem(QTreeWidgetItem([""]))

    def sync_source_order_from_view(self) -> None:
        ordered_files: list[Path] = []
        for index in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(index)
            if item is None:
                continue
            item_path = item.data(0, Qt.UserRole)
            if item_path:
                ordered_files.append(Path(item_path))
        self.source_files = ordered_files
        self.refresh_preview()

    def current_mode(self) -> str:
        if self.sequence_mode_radio.isChecked():
            return "sequence"
        return "search"

    def build_preview_entries(self) -> list[tuple[Path, Path, str]]:
        preview_entries: list[tuple[Path, Path, str]] = []
        mode = self.current_mode()

        if mode == "search":
            search = self.search_input.text().strip()
            replacement = self.replace_input.text()
            target_text = self.target_input.text().strip() or "renamed"
            rename_in_place = self.rename_in_place_checkbox.isChecked()

            for source_path in self.source_files:
                new_stem = RenameEngine.apply_pattern(source_path.stem, search, replacement)
                new_name = f"{new_stem}{source_path.suffix}"
                destination = RenameEngine.build_destination(
                    source_path=source_path,
                    new_name=new_name,
                    target_text=target_text,
                    rename_in_place=rename_in_place,
                )
                status = "ready"
                if destination == source_path:
                    status = "unchanged"
                elif destination.exists() and not self.allow_overwrite_checkbox.isChecked():
                    status = "blocked: target exists"
                preview_entries.append((source_path, destination, status))
            return preview_entries

        target_text = self.sequence_target_input.text().strip() or "sequence"
        pattern = self.sequence_pattern_input.text().strip() or "sequence.####.ext"

        for index, source_path in enumerate(self.source_files, start=1):
            new_name = RenameEngine.apply_sequence_pattern(pattern, index, source_path.suffix)
            destination = RenameEngine.build_destination(
                source_path=source_path,
                new_name=new_name,
                target_text=target_text,
                rename_in_place=False,
            )
            status = "ready"
            if destination.exists() and not self.allow_overwrite_checkbox.isChecked():
                status = "blocked: target exists"
            preview_entries.append((source_path, destination, status))

        return preview_entries

    def refresh_preview(self, *_args) -> None:
        self._update_mode_sections()
        preview_entries = self.build_preview_entries()
        ready_count = 0
        self._sync_file_view()
        for row, (source_path, destination, status) in enumerate(preview_entries):
            if status == "ready":
                ready_count += 1
            source_item = self.file_tree.topLevelItem(row)
            preview_item = self.preview_tree.topLevelItem(row)
            if source_item is None or preview_item is None:
                continue
            source_item.setText(0, source_path.name)
            source_item.setToolTip(0, str(source_path))
            source_item.setData(0, Qt.UserRole, str(source_path))
            preview_item.setText(0, f"{destination.name} [{status}]")
            preview_item.setToolTip(0, str(destination))

        if not self.source_files:
            self.status_label.setText("No files loaded.")
        else:
            self.status_label.setText(
                f"{len(self.source_files)} files loaded. {ready_count} ready to rename."
            )

    def rename_files(self) -> None:
        preview_entries = self.build_preview_entries()
        actionable = [(src, dst) for src, dst, status in preview_entries if status == "ready"]

        if not actionable:
            QMessageBox.information(self, APP_TITLE, "Nothing is ready to rename.")
            return

        errors: List[str] = []
        completed: list[RenameRecord] = []
        succeeded_sources: set[Path] = set()

        for source_path, destination in actionable:
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    if self.allow_overwrite_checkbox.isChecked():
                        if destination.is_dir():
                            raise IsADirectoryError(destination)
                        destination.unlink()
                    else:
                        raise FileExistsError(destination)
                shutil.move(str(source_path), str(destination))
                completed.append(
                    RenameRecord(source=str(source_path), destination=str(destination))
                )
                succeeded_sources.add(source_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source_path.name}: {exc}")

        refreshed_files: list[Path] = []
        for source_path, destination, status in preview_entries:
            if status == "ready" and source_path in succeeded_sources:
                refreshed_files.append(destination)
            else:
                refreshed_files.append(source_path)

        if completed:
            self.last_batch = completed
            self.history_store.save(completed)
            self._update_undo_state()

        self.source_files = refreshed_files
        self._sync_file_view()
        self.refresh_preview()

        if errors:
            QMessageBox.warning(
                self,
                APP_TITLE,
                "Rename completed with issues:\n" + "\n".join(errors),
            )
            return

        QMessageBox.information(
            self,
            APP_TITLE,
            f"Renamed {len(completed)} file(s) successfully.",
        )

    def undo_last_rename(self) -> None:
        records = self.history_store.load()
        if not records:
            QMessageBox.information(self, APP_TITLE, "No rename batch is available to undo.")
            return

        errors: List[str] = []
        for record in reversed(records):
            source = Path(record.source)
            destination = Path(record.destination)
            try:
                if not destination.exists():
                    raise FileNotFoundError(destination)
                source.parent.mkdir(parents=True, exist_ok=True)
                if source.exists():
                    raise FileExistsError(source)
                shutil.move(str(destination), str(source))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{destination.name}: {exc}")

        if errors:
            QMessageBox.warning(
                self,
                APP_TITLE,
                "Undo completed with issues:\n" + "\n".join(errors),
            )
            return

        self.history_store.clear()
        self.last_batch = []
        self.source_files = [Path(record.source) for record in records]
        self._sync_file_view()
        self._update_undo_state()
        self.refresh_preview()
        QMessageBox.information(self, APP_TITLE, "Last rename batch was undone.")

    def _update_undo_state(self) -> None:
        self.undo_button.setEnabled(bool(self.last_batch))


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
