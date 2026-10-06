from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .scanner import scan_folder

DEFAULT_SCAN_FOLDERS = (
    Path(r"C:\StabilityMatrix\Data\Models\Lora"),
    Path(r"C:\StabilityMatrix\Data\Models\LyCORIS"),
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LoRA Character Overlap Finder")
        self.resize(1200, 720)

        self.status_label = QLabel("Ready. Scan the Stability Matrix folders or choose another folder.")
        self.default_button = QPushButton("Scan Default Folders")
        self.default_button.clicked.connect(self.scan_defaults)
        self.choose_button = QPushButton("Choose Folder")
        self.choose_button.clicked.connect(self.choose_folder)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Source", "File", "Size", "SHA-256", "Errors"])
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.default_button)
        buttons.addWidget(self.choose_button)
        buttons.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

    def _scan_folders(self, folders: list[Path]) -> None:
        existing = [folder for folder in folders if folder.is_dir()]
        if not existing:
            self.status_label.setText("None of the selected scan folders exist.")
            return

        self.default_button.setEnabled(False)
        self.choose_button.setEnabled(False)
        self.status_label.setText("Scanning: " + ", ".join(str(folder) for folder in existing))
        QApplication.processEvents()

        rows = []
        try:
            for folder in existing:
                source = folder.name
                for record in scan_folder(folder):
                    rows.append((source, record))
        finally:
            self.default_button.setEnabled(True)
            self.choose_button.setEnabled(True)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for row, (source, record) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(source))
            self.table.setItem(row, 1, QTableWidgetItem(str(record.path)))
            size_item = QTableWidgetItem()
            size_item.setData(Qt.ItemDataRole.DisplayRole, record.file_size)
            self.table.setItem(row, 2, size_item)
            self.table.setItem(row, 3, QTableWidgetItem(record.sha256 or ""))
            self.table.setItem(row, 4, QTableWidgetItem("; ".join(record.scan_errors)))

        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        self.status_label.setText(
            f"Found {len(rows)} model files across {len(existing)} folder(s)."
        )

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
