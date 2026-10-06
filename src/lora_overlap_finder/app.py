from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import __version__
from .detection import detect_overlaps, enrich_from_civitai
from .scanner import scan_folder
from .updater import check_for_update, install_update

DEFAULT_SCAN_FOLDERS = (
    Path(r"C:\StabilityMatrix\Data\Models\Lora"),
    Path(r"C:\StabilityMatrix\Data\Models\LyCORIS"),
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"LoRA Character Overlap Finder v{__version__}")
        self.resize(1350, 780)

        self.status_label = QLabel("Ready. Scan the Stability Matrix folders or choose another folder.")
        self.default_button = QPushButton("Scan Default Folders")
        self.default_button.clicked.connect(self.scan_defaults)
        self.choose_button = QPushButton("Choose Folder")
        self.choose_button.clicked.connect(self.choose_folder)
        self.update_button = QPushButton("Check for Updates")
        self.update_button.clicked.connect(lambda: self.check_updates(show_current=True))

        self.files_table = QTableWidget(0, 8)
        self.files_table.setHorizontalHeaderLabels([
            "Source", "File", "Size", "Civitai Model", "Version", "Base Model",
            "Trained Words", "Errors",
        ])
        self.files_table.setAlternatingRowColors(True)
        self.files_table.setSortingEnabled(True)

        self.overlap_table = QTableWidget(0, 5)
        self.overlap_table.setHorizontalHeaderLabels([
            "Character / Match", "Confidence", "Files", "Evidence", "Matching Paths"
        ])
        self.overlap_table.setAlternatingRowColors(True)
        self.overlap_table.setSortingEnabled(True)

        tabs = QTabWidget()
        tabs.addTab(self.overlap_table, "Overlaps")
        tabs.addTab(self.files_table, "All Models")

        buttons = QHBoxLayout()
        buttons.addWidget(self.default_button)
        buttons.addWidget(self.choose_button)
        buttons.addWidget(self.update_button)
        buttons.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(tabs)

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

    def _scan_folders(self, folders: list[Path]) -> None:
        existing = [folder for folder in folders if folder.is_dir()]
        if not existing:
            self.status_label.setText("None of the selected scan folders exist.")
            return

        self.default_button.setEnabled(False)
        self.choose_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        records = []
        sources: dict[Path, str] = {}
        try:
            self.status_label.setText("Scanning and hashing local models...")
            QApplication.processEvents()
            for folder in existing:
                for record in scan_folder(folder):
                    records.append(record)
                    sources[record.path] = folder.name

            self.status_label.setText(f"Found {len(records)} files. Looking them up on Civitai...")
            QApplication.processEvents()
            try:
                enrich_from_civitai(records)
                civitai_status = ""
            except Exception as exc:
                civitai_status = f" Civitai lookup warning: {exc}"

            self.status_label.setText("Analyzing character overlap...")
            QApplication.processEvents()
            overlaps = detect_overlaps(records)
            self._show_files(records, sources)
            self._show_overlaps(overlaps)
            self.status_label.setText(
                f"Done: {len(records)} files, {len(overlaps)} overlap group(s).{civitai_status}"
            )
        finally:
            QApplication.restoreOverrideCursor()
            self.default_button.setEnabled(True)
            self.choose_button.setEnabled(True)

    def _show_files(self, records, sources) -> None:
        self.files_table.setSortingEnabled(False)
        self.files_table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                sources.get(record.path, ""),
                str(record.path),
                str(record.file_size),
                str(record.civitai_model_id or ""),
                str(record.civitai_model_version_id or ""),
                record.base_model or "",
                ", ".join(record.trained_words),
                "; ".join(record.scan_errors),
            ]
            for column, value in enumerate(values):
                self.files_table.setItem(row, column, QTableWidgetItem(value))
        self.files_table.resizeColumnsToContents()
        self.files_table.setSortingEnabled(True)

    def _show_overlaps(self, overlaps) -> None:
        self.overlap_table.setSortingEnabled(False)
        self.overlap_table.setRowCount(len(overlaps))
        for row, overlap in enumerate(overlaps):
            paths = [str(record.path) for record in overlap.records]
            values = [
                overlap.character,
                overlap.confidence,
                str(len(paths)),
                overlap.evidence,
                "\n".join(paths),
            ]
            for column, value in enumerate(values):
                self.overlap_table.setItem(row, column, QTableWidgetItem(value))
        self.overlap_table.resizeColumnsToContents()
        self.overlap_table.setSortingEnabled(True)

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
