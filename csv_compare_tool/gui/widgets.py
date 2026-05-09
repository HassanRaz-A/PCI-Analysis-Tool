"""Shared Qt widgets used across multiple tabs."""
from __future__ import annotations
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

from core.loaders import discover_files, SUPPORTED_EXTS


class DropList(QListWidget):
    """QListWidget that accepts drag-and-drop of files and folders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_dir():
                for f in discover_files(p):
                    self.add_path(f)
            elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                self.add_path(p)

    def add_path(self, path: Path):
        s = str(path)
        if not any(self.item(i).text() == s for i in range(self.count())):
            self.addItem(QListWidgetItem(s))

    def files(self) -> List[Path]:
        return [Path(self.item(i).text()) for i in range(self.count())]

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete:
            for it in self.selectedItems():
                self.takeItem(self.row(it))
        else:
            super().keyPressEvent(e)
