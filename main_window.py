"""Main window for the CSV/Excel Comparison Tool."""
from __future__ import annotations
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem,
    QComboBox, QGroupBox, QFormLayout, QDoubleSpinBox, QProgressBar,
    QPlainTextEdit, QMessageBox, QStatusBar, QCheckBox, QLineEdit,
    QSplitter,
)

from core.loaders import discover_files, list_sheets, get_columns, SUPPORTED_EXTS
from core.comparator import CompareConfig, Mode
from core.exporter import export_results
from gui.workers import CompareWorker

APP_DIR = Path.home() / ".csv_compare_tool"
CONFIG_PATH = APP_DIR / "config.json"
LOG_DIR = APP_DIR / "logs"


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=3
    )
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    # Console too
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
               for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


class DropList(QListWidget):
    """A QListWidget that accepts drag-and-drop of files and folders."""

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSV / Excel Comparison Tool")
        self.resize(1100, 780)
        self.worker = None
        self.log = logging.getLogger("app")
        self._build_ui()
        self._load_config()

    # --------------------------------------------------------------- UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, 1)

        # === Top: Files + Config ===
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Files
        files_box = QGroupBox("Step 1 — Files")
        files_layout = QHBoxLayout(files_box)

        # Main files
        main_col = QVBoxLayout()
        main_col.addWidget(QLabel("<b>Main files</b> (drag & drop folder or files):"))
        self.main_list = DropList()
        self.main_list.setMinimumHeight(110)
        main_col.addWidget(self.main_list)
        btn_row = QHBoxLayout()
        b_files = QPushButton("Add Files…")
        b_folder = QPushButton("Add Folder…")
        b_clear = QPushButton("Clear")
        b_files.clicked.connect(self._add_files)
        b_folder.clicked.connect(self._add_folder)
        b_clear.clicked.connect(self.main_list.clear)
        for b in (b_files, b_folder, b_clear):
            btn_row.addWidget(b)
        main_col.addLayout(btn_row)
        files_layout.addLayout(main_col, 2)

        # Reference
        ref_col = QVBoxLayout()
        ref_col.addWidget(QLabel("<b>Reference file:</b>"))
        ref_path_row = QHBoxLayout()
        self.ref_path_edit = QLineEdit()
        self.ref_path_edit.setPlaceholderText("Select reference file…")
        b_pick_ref = QPushButton("Browse…")
        b_pick_ref.clicked.connect(self._pick_ref)
        ref_path_row.addWidget(self.ref_path_edit)
        ref_path_row.addWidget(b_pick_ref)
        ref_col.addLayout(ref_path_row)
        ref_col.addWidget(QLabel("Reference sheet:"))
        self.ref_sheet_combo = QComboBox()
        ref_col.addWidget(self.ref_sheet_combo)
        b_show_main_cols = QPushButton("Show columns of selected main file")
        b_show_main_cols.clicked.connect(self._show_main_columns)
        ref_col.addWidget(b_show_main_cols)
        b_show_ref_cols = QPushButton("Show reference columns")
        b_show_ref_cols.clicked.connect(self._show_ref_columns)
        ref_col.addWidget(b_show_ref_cols)
        ref_col.addStretch()
        files_layout.addLayout(ref_col, 1)

        top_layout.addWidget(files_box)

        # Config
        cfg_box = QGroupBox("Step 2 — Comparison Configuration")
        cfg_layout = QFormLayout(cfg_box)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([m.value for m in Mode])
        self.mode_combo.setToolTip(
            "exists: row's key found in reference (lookup)\n"
            "diff:   for matched rows, show columns whose values changed\n"
            "threshold: numeric drift |main - ref| > value"
        )
        cfg_layout.addRow("Mode:", self.mode_combo)

        self.case_check = QCheckBox("Case-insensitive matching")
        self.case_check.setChecked(True)
        cfg_layout.addRow("", self.case_check)

        self.main_keys_edit = QLineEdit()
        self.main_keys_edit.setPlaceholderText("e.g. eNodeB_ID, Cell_ID, PCI")
        cfg_layout.addRow("Main key columns (comma-sep):", self.main_keys_edit)

        self.ref_keys_edit = QLineEdit()
        self.ref_keys_edit.setPlaceholderText("e.g. eNodeB, Cell, PCI")
        cfg_layout.addRow("Reference key columns (comma-sep):", self.ref_keys_edit)

        self.diff_cols_edit = QLineEdit()
        self.diff_cols_edit.setPlaceholderText("(diff mode) columns to compare, comma-sep")
        cfg_layout.addRow("Diff columns:", self.diff_cols_edit)

        self.thr_main_edit = QLineEdit()
        self.thr_main_edit.setPlaceholderText("(threshold mode) numeric col in main")
        cfg_layout.addRow("Threshold main col:", self.thr_main_edit)

        self.thr_ref_edit = QLineEdit()
        self.thr_ref_edit.setPlaceholderText("(threshold mode) numeric col in reference")
        cfg_layout.addRow("Threshold reference col:", self.thr_ref_edit)

        self.thr_value = QDoubleSpinBox()
        self.thr_value.setRange(0, 1e9)
        self.thr_value.setDecimals(3)
        self.thr_value.setValue(0)
        cfg_layout.addRow("Threshold |Δ| >:", self.thr_value)

        top_layout.addWidget(cfg_box)

        # Action row
        action_row = QHBoxLayout()
        self.run_btn = QPushButton("▶  Run Comparison")
        self.run_btn.setMinimumHeight(36)
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        action_row.addWidget(self.run_btn, 3)
        action_row.addWidget(self.cancel_btn, 1)
        top_layout.addLayout(action_row)

        self.progress = QProgressBar()
        top_layout.addWidget(self.progress)

        splitter.addWidget(top)

        # === Bottom: Log panel ===
        log_box = QGroupBox("Activity log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        log_layout.addWidget(self.log_view)
        splitter.addWidget(log_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")

        # Wire up auto-refresh of sheet list
        self.ref_path_edit.editingFinished.connect(self._refresh_ref_sheets)

    # --------------------------------------------------------------- Slots
    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select main files", "",
            "Data files (*.csv *.tsv *.xlsx *.xls);;All files (*)"
        )
        for f in files:
            self.main_list.add_path(Path(f))

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select folder")
        if d:
            for f in discover_files(d):
                self.main_list.add_path(f)

    def _pick_ref(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select reference file", "",
            "Data files (*.csv *.tsv *.xlsx *.xls);;All files (*)"
        )
        if f:
            self.ref_path_edit.setText(f)
            self._refresh_ref_sheets()

    def _refresh_ref_sheets(self):
        path = self.ref_path_edit.text().strip()
        self.ref_sheet_combo.clear()
        if not path or not Path(path).exists():
            return
        try:
            for s in list_sheets(path):
                self.ref_sheet_combo.addItem(s)
        except Exception as e:
            self._log(f"Could not list reference sheets: {e}")

    def _show_main_columns(self):
        items = self.main_list.selectedItems() or (
            [self.main_list.item(0)] if self.main_list.count() else []
        )
        if not items:
            QMessageBox.information(self, "No file", "Select a main file first.")
            return
        path = items[0].text()
        try:
            sheets = list_sheets(path)
            cols_text = []
            for s in sheets:
                cols_text.append(f"=== {s} ===")
                cols_text.extend(get_columns(path, s))
                cols_text.append("")
            QMessageBox.information(self, f"Columns in {Path(path).name}",
                                    "\n".join(cols_text))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _show_ref_columns(self):
        path = self.ref_path_edit.text().strip()
        if not path:
            QMessageBox.information(self, "No reference", "Pick a reference file first.")
            return
        sheet = self.ref_sheet_combo.currentText() or None
        try:
            cols = get_columns(path, sheet)
            QMessageBox.information(self, "Reference columns", "\n".join(cols))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _log(self, msg: str):
        self.log_view.appendPlainText(msg)
        self.log.info(msg)

    def _run(self):
        files = self.main_list.files()
        if not files:
            QMessageBox.warning(self, "No files", "Add at least one main file.")
            return
        ref = self.ref_path_edit.text().strip()
        if not ref or not Path(ref).exists():
            QMessageBox.warning(self, "No reference", "Pick a valid reference file.")
            return

        keys_main = [c.strip() for c in self.main_keys_edit.text().split(",") if c.strip()]
        keys_ref = [c.strip() for c in self.ref_keys_edit.text().split(",") if c.strip()]
        if not keys_main or not keys_ref:
            QMessageBox.warning(self, "Keys missing",
                                "Provide key columns for both main and reference.")
            return
        if len(keys_main) != len(keys_ref):
            QMessageBox.warning(self, "Keys mismatch",
                                f"Main has {len(keys_main)} keys but reference has "
                                f"{len(keys_ref)}. They must match.")
            return

        cfg = CompareConfig(
            mode=Mode(self.mode_combo.currentText()),
            keys_main=keys_main,
            keys_ref=keys_ref,
            diff_columns=[c.strip() for c in self.diff_cols_edit.text().split(",") if c.strip()],
            threshold_column_main=self.thr_main_edit.text().strip(),
            threshold_column_ref=self.thr_ref_edit.text().strip(),
            threshold_value=self.thr_value.value(),
            case_insensitive=self.case_check.isChecked(),
        )

        self._save_config()
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self._log(f"--- Run started: mode={cfg.mode.value}, keys={keys_main} ↔ {keys_ref} ---")

        self.worker = CompareWorker(
            main_files=files,
            ref_file=Path(ref),
            ref_sheet=self.ref_sheet_combo.currentText() or None,
            cfg=cfg,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self._log("Cancellation requested…")

    def _on_progress(self, cur: int, total: int, msg: str):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(cur)
        self.statusBar().showMessage(msg)
        if msg:
            self._log(msg)

    def _on_file_done(self, source: str, summary: dict):
        name = Path(source).name
        self._log(
            f"  ✓ {name} [{summary['sheet']}] "
            f"matched={summary['matched']}, unmatched={summary['unmatched']}, "
            f"diffs={summary['diffs_or_breaches']}"
        )

    def _on_done(self, results):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if not results:
            self._log("No results produced.")
            return
        total_matched = sum(len(r.matched) for r in results)
        total_unmatched = sum(len(r.unmatched) for r in results)
        self._log(f"--- Run finished: {len(results)} comparisons, "
                  f"{total_matched} matched / {total_unmatched} unmatched ---")

        out, _ = QFileDialog.getSaveFileName(
            self, "Save report as…", "comparison_report.xlsx",
            "Excel workbook (*.xlsx)"
        )
        if not out:
            return
        try:
            path = export_results(results, out)
            self._log(f"Report saved → {path}")
            QMessageBox.information(self, "Done", f"Report saved to:\n{path}")
        except Exception as e:
            self.log.exception("Export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_failed(self, msg: str):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._log(f"FAILED: {msg}")
        QMessageBox.critical(self, "Comparison failed", msg)

    # --------------------------------------------------------------- Config
    def _save_config(self):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "mode": self.mode_combo.currentText(),
                "case_insensitive": self.case_check.isChecked(),
                "main_keys": self.main_keys_edit.text(),
                "ref_keys": self.ref_keys_edit.text(),
                "diff_cols": self.diff_cols_edit.text(),
                "thr_main": self.thr_main_edit.text(),
                "thr_ref": self.thr_ref_edit.text(),
                "thr_value": self.thr_value.value(),
                "last_ref": self.ref_path_edit.text(),
            }
            CONFIG_PATH.write_text(json.dumps(data, indent=2))
        except Exception as e:
            self.log.warning("Could not save config: %s", e)

    def _load_config(self):
        if not CONFIG_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text())
            mode = data.get("mode", Mode.EXISTS.value)
            idx = self.mode_combo.findText(mode)
            if idx >= 0:
                self.mode_combo.setCurrentIndex(idx)
            self.case_check.setChecked(data.get("case_insensitive", True))
            self.main_keys_edit.setText(data.get("main_keys", ""))
            self.ref_keys_edit.setText(data.get("ref_keys", ""))
            self.diff_cols_edit.setText(data.get("diff_cols", ""))
            self.thr_main_edit.setText(data.get("thr_main", ""))
            self.thr_ref_edit.setText(data.get("thr_ref", ""))
            self.thr_value.setValue(float(data.get("thr_value", 0)))
            ref = data.get("last_ref", "")
            if ref and Path(ref).exists():
                self.ref_path_edit.setText(ref)
                self._refresh_ref_sheets()
        except Exception as e:
            self.log.warning("Could not load config: %s", e)


def run_app():
    setup_logging()
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("CSV/Excel Comparison Tool")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
