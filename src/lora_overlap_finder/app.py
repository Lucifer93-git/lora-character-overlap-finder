from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .scanner import scan_folder


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LoRA Character Overlap Finder")
        self.resize(1100, 700)

        self.status_label = QLabel("Choose a LoRA folder to begin.")
        self.choose_button = QPushButton("Choose LoRA Folder")
        self.choose_button.clicked.connect(self.choose_folder)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Size", "SHA-256", "Errors"])
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        layout = QVBoxLayout()
        layout.addWidget(self.choose_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select LoRA Folder")
        if not selected:
            return

        folder = Path(selected)
        self.status_label.setText(f"Scanning {folder} ...")
        QApplication.processEvents()

        records = scan_folder(folder)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(records))

        for row, record in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(str(record.path)))
            size_item = QTableWidgetItem()
            size_item.setData(Qt.ItemDataRole.DisplayRole, record.file_size)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, QTableWidgetItem(record.sha256 or ""))
            self.table.setItem(row, 3, QTableWidgetItem("; ".join(record.scan_errors)))

        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        self.status_label.setText(f"Found {len(records)} LoRA files.")


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
