from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot, QSize
from send2trash import send2trash
from PySide6.QtGui import QPixmap

from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QTreeWidget, QTreeWidgetItem,
)

from . import __version__
from .cache import Cache
from .detection import detect_overlaps, enrich_from_civitai
from .scanner import find_preview, scan_folder
from .updater import check_for_update, install_update

DEFAULT_SCAN_FOLDERS = (
    Path(r"C:\StabilityMatrix\Data\Models\Lora"),
    Path(r"C:\StabilityMatrix\Data\Models\LyCORIS"),
)


class ScanWorker(QObject):
    status = Signal(str)
    finished = Signal(object, object, object, str)
    failed = Signal(str)

    def __init__(self, folders: list[Path]) -> None:
        super().__init__()
        self.folders = folders

    @Slot()
    def run(self) -> None:
        cache = Cache()
        try:
            records = []
            sources: dict[Path, str] = {}
            self.status.emit("Scanning local models (unchanged files use the cache)...")
            for folder in self.folders:
                for record in scan_folder(folder, cache=cache):
                    records.append(record)
                    sources[record.path] = folder.name

            local_hits = sum(1 for record in records if record.from_cache)
            self.status.emit(f"Found {len(records)} files. Checking new hashes against Civitai...")
            try:
                civitai_hits, queried = enrich_from_civitai(records, cache=cache)
                warning = ""
            except Exception as exc:
                civitai_hits, queried = 0, 0
                warning = f" Civitai lookup warning: {exc}"

            self.status.emit("Analyzing character overlap...")
            overlaps = detect_overlaps(records)
            summary = (
                f"Done: {len(records)} files, {len(overlaps)} overlap group(s). "
                f"Local cache: {local_hits}/{len(records)}; Civitai cache: {civitai_hits}; "
                f"new Civitai lookups: {queried}.{warning}"
            )
            self.finished.emit(records, sources, overlaps, summary)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            cache.close()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._records = []
        self._sources = {}
        self._overlaps = []
        self.setWindowTitle(f"LoRA Character Overlap Finder v{__version__}")
        self.resize(1350, 780)

        self.status_label = QLabel("Ready. Scan the Stability Matrix folders or choose another folder.")
        self.default_button = QPushButton("Scan Default Folders")
        self.default_button.clicked.connect(self.scan_defaults)
        self.choose_button = QPushButton("Choose Folder")
        self.choose_button.clicked.connect(self.choose_folder)
        self.update_button = QPushButton("Check for Updates")
        self.update_button.clicked.connect(lambda: self.check_updates(show_current=True))
        self.style_button = QPushButton("Mark Selected as Style")
        self.style_button.clicked.connect(lambda: self.set_selected_classification("style"))
        self.character_button = QPushButton("Mark Selected as Character")
        self.character_button.clicked.connect(lambda: self.set_selected_classification("character"))
        self.delete_button = QPushButton("Send Checked to Recycle Bin")
        self.delete_button.clicked.connect(self.delete_checked)

        self.files_table = QTableWidget(0, 9)
        self.files_table.setHorizontalHeaderLabels([
            "Type", "Source", "File", "Size", "Civitai Model", "Version", "Base Model",
            "Trained Words", "Errors",
        ])
        self.files_table.setAlternatingRowColors(True)
        self.files_table.setSortingEnabled(True)

        self.overlap_table = QTreeWidget()
        self.overlap_table.setColumnCount(7)
        self.overlap_table.setHeaderLabels(
            ["Delete", "Preview", "Character / Match", "LoRA", "Confidence", "Evidence", "Path"]
        )
        self.overlap_table.setAlternatingRowColors(True)
        self.overlap_table.setIconSize(QSize(96, 96))
        self.overlap_table.setUniformRowHeights(False)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.overlap_table, "Overlaps")
        self.tabs.addTab(self.files_table, "All Models")

        buttons = QHBoxLayout()
        buttons.addWidget(self.default_button)
        buttons.addWidget(self.choose_button)
        buttons.addWidget(self.update_button)
        buttons.addWidget(self.style_button)
        buttons.addWidget(self.character_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(self.tabs)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)
        QTimer.singleShot(1200, lambda: self.check_updates(show_current=False))

    def check_updates(self, show_current: bool) -> None:
        self.update_button.setEnabled(False)
        try:
            update = check_for_update()
        except Exception as exc:
            if show_current:
                QMessageBox.warning(self, "Update Check", f"Could not check for updates.\n\n{exc}")
            return
        finally:
            self.update_button.setEnabled(True)
        if update is None:
            if show_current:
                QMessageBox.information(self, "Update Check", f"Version {__version__} is up to date.")
            return
        answer = QMessageBox.question(
            self, "Update Available",
            f"Version {update.version} is available.\n\nDownload it, replace this EXE, and restart now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            install_update(update)
        except Exception as exc:
            QMessageBox.critical(self, "Update Failed", f"Automatic update failed.\n\n{exc}")
            if update.release_url:
                webbrowser.open(update.release_url)
            return
        QApplication.quit()

    def _set_scanning(self, scanning: bool) -> None:
        self.default_button.setEnabled(not scanning)
        self.choose_button.setEnabled(not scanning)

    def _scan_folders(self, folders: list[Path]) -> None:
        existing = [folder for folder in folders if folder.is_dir()]
        if not existing:
            self.status_label.setText("None of the selected scan folders exist.")
            return
        if self._scan_thread is not None:
            return

        self._set_scanning(True)
        thread = QThread(self)
        worker = ScanWorker(existing)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.status.connect(self.status_label.setText)
        worker.finished.connect(self._scan_complete)
        worker.failed.connect(self._scan_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._scan_thread = thread
        self._scan_worker = worker
        thread.start()

    @Slot(object, object, object, str)
    def _scan_complete(self, records, sources, overlaps, summary: str) -> None:
        self._records = records
        self._sources = sources
        self._overlaps = overlaps
        self._show_files(records, sources)
        self._show_overlaps(overlaps)
        self.status_label.setText(summary)

    @Slot(str)
    def _scan_failed(self, message: str) -> None:
        self.status_label.setText(f"Scan failed: {message}")
        QMessageBox.critical(self, "Scan Failed", message)

    @Slot()
    def _thread_finished(self) -> None:
        self._scan_thread = None
        self._scan_worker = None
        self._set_scanning(False)

    def _show_files(self, records, sources) -> None:
        self.files_table.setSortingEnabled(False)
        self.files_table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.classification.title(), sources.get(record.path, ""), str(record.path),
                str(record.file_size), str(record.civitai_model_id or ""),
                str(record.civitai_model_version_id or ""), record.base_model or "",
                ", ".join(record.trained_words), "; ".join(record.scan_errors),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, str(record.path))
                self.files_table.setItem(row, column, item)
        self.files_table.resizeColumnsToContents()
        self.files_table.setSortingEnabled(True)

    def _show_overlaps(self, overlaps) -> None:
        self.overlap_table.clear()
        for overlap in overlaps:
            group = QTreeWidgetItem(self.overlap_table)
            group.setText(2, f"{overlap.character} · {len(overlap.records)} matches")
            group.setText(4, overlap.confidence)
            group.setText(5, overlap.evidence)
            group.setFirstColumnSpanned(True)
            group.setExpanded(True)
            font = group.font(2)
            font.setBold(True)
            group.setFont(2, font)

            for record in overlap.records:
                child = QTreeWidgetItem(group)
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                raw = str(record.path)
                child.setData(0, Qt.ItemDataRole.UserRole, raw)
                child.setText(2, overlap.character)
                child.setText(3, record.path.name)
                child.setText(4, overlap.confidence)
                child.setText(5, overlap.evidence)
                child.setText(6, raw)
                preview = find_preview(record.path)
                record.preview_path = preview
                if preview:
                    pixmap = QPixmap(str(preview))
                    if not pixmap.isNull():
                        child.setIcon(1, pixmap.scaled(
                            96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        ))
                child.setSizeHint(1, QSize(104, 104))
                for column in range(1, 7):
                    child.setData(column, Qt.ItemDataRole.UserRole, raw)

        for column in range(7):
            self.overlap_table.resizeColumnToContents(column)

    def _selected_paths(self) -> list[Path]:
        paths: list[Path] = []
        table = self.overlap_table if self.tabs.currentWidget() is self.overlap_table else self.files_table
        for item in table.selectedItems():
            raw = item.data(0, Qt.ItemDataRole.UserRole) if isinstance(table, QTreeWidget) else item.data(Qt.ItemDataRole.UserRole)
            if raw:
                path = Path(raw)
                if path not in paths:
                    paths.append(path)
        return paths

    def set_selected_classification(self, kind: str) -> None:
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "Classification", "Select one or more LoRA rows first.")
            return
        cache = Cache()
        try:
            for path in paths:
                cache.set_classification(path, kind)
                for record in self._records:
                    if record.path == path:
                        record.classification = kind
            self._overlaps = detect_overlaps(self._records)
        finally:
            cache.close()
        self._show_files(self._records, self._sources)
        self._show_overlaps(self._overlaps)
        self.status_label.setText(
            f"Marked {len(paths)} model(s) as {'Style / Not Character' if kind == 'style' else 'Character'}."
        )

    def delete_checked(self) -> None:
        paths: list[Path] = []
        root = self.overlap_table.invisibleRootItem()
        for group_index in range(root.childCount()):
            group = root.child(group_index)
            for child_index in range(group.childCount()):
                item = group.child(child_index)
                if item.checkState(0) == Qt.CheckState.Checked:
                    raw = item.data(0, Qt.ItemDataRole.UserRole)
                    if raw and Path(raw) not in paths:
                        paths.append(Path(raw))
        if not paths:
            QMessageBox.information(self, "Recycle Bin", "Check the LoRA files you want to remove first.")
            return

        preview = "\n".join(str(path) for path in paths[:15])
        if len(paths) > 15:
            preview += f"\n...and {len(paths) - 15} more"
        answer = QMessageBox.warning(
            self, "Confirm Recycle Bin",
            f"Send these {len(paths)} LoRA file(s) to the Windows Recycle Bin?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        failed = []
        for path in paths:
            try:
                if path.exists():
                    send2trash(str(path))
            except Exception as exc:
                failed.append(f"{path}: {exc}")
        if failed:
            QMessageBox.warning(self, "Recycle Bin", "Some files could not be removed:\n\n" + "\n".join(failed[:10]))
        else:
            QMessageBox.information(self, "Recycle Bin", f"Sent {len(paths)} file(s) to Recycle Bin.")
        self._records = [r for r in self._records if r.path not in paths]
        self._overlaps = detect_overlaps(self._records)
        self._show_files(self._records, self._sources)
        self._show_overlaps(self._overlaps)

    def scan_defaults(self) -> None:
        self._scan_folders(list(DEFAULT_SCAN_FOLDERS))

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select model folder")
        if selected:
            self._scan_folders([Path(selected)])


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
