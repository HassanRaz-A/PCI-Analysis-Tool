"""Main window - hosts the PCI Analysis tab and the General Compare tab."""
from __future__ import annotations
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QComboBox, QGroupBox, QFormLayout,
    QDoubleSpinBox, QProgressBar, QPlainTextEdit, QMessageBox, QStatusBar,
    QCheckBox, QLineEdit, QSplitter, QTabWidget,
)

from core.loaders import discover_files, list_sheets, get_columns, SUPPORTED_EXTS
from core.comparator import CompareConfig, Mode
from core.exporter import export_results
from gui.workers import CompareWorker
from gui.widgets import DropList
from gui.pci_tab import PCITab

APP_DIR     = Path.home() / ".csv_compare_tool"
CONFIG_PATH = APP_DIR / "config.json"
LOG_DIR     = APP_DIR / "logs"

# ── Neon Dark Stylesheet ─────────────────────────────────────────────────────

_NEON_STYLE = """
/* ══════════════  NEON DARK THEME  ══════════════ */

QWidget {
    background-color: #0D1117;
    color: #C9D1D9;
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 9pt;
}
QMainWindow, QDialog {
    background-color: #0D1117;
}

/* ── Tabs ─────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #21262D;
    background: #0D1117;
    border-radius: 0 6px 6px 6px;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background: #161B22;
    color: #8B949E;
    padding: 9px 24px;
    border: 1px solid #21262D;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
    font-size: 9pt;
}
QTabBar::tab:selected {
    background: #0D1117;
    color: #00D4FF;
    border-color: #00D4FF;
    border-bottom: 2px solid #0D1117;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background: #1C2128;
    color: #C9D1D9;
    border-color: #30363D;
}

/* ── Group Boxes ──────────────────────────────── */
QGroupBox {
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    color: #00D4FF;
    font-weight: bold;
    font-size: 9pt;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 8px;
    color: #00D4FF;
    background: #0D1117;
    border-radius: 3px;
}

/* ── Push Buttons ─────────────────────────────── */
QPushButton {
    background: #1C2128;
    color: #C9D1D9;
    border: 1px solid #30363D;
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 26px;
}
QPushButton:hover {
    background: #22303F;
    border-color: #00D4FF;
    color: #00D4FF;
}
QPushButton:pressed {
    background: #0D1117;
    border-color: #0099BB;
    color: #0099BB;
}
QPushButton:disabled {
    background: #13181F;
    color: #3D444D;
    border-color: #21262D;
}

/* Run button — neon green */
QPushButton#runBtn {
    background: #071A0D;
    color: #39FF14;
    border: 1.5px solid #39FF14;
    font-weight: bold;
    font-size: 10pt;
    letter-spacing: 0.5px;
}
QPushButton#runBtn:hover {
    background: #0D2C14;
    border-color: #50FF30;
    color: #50FF30;
}
QPushButton#runBtn:pressed {
    background: #040E07;
    color: #2ACC0D;
    border-color: #2ACC0D;
}
QPushButton#runBtn:disabled {
    background: #0D1117;
    color: #1A3A1A;
    border-color: #152510;
}

/* Export button — neon amber */
QPushButton#exportBtn {
    background: #1A1200;
    color: #FFB800;
    border: 1.5px solid #FFB800;
    font-weight: bold;
}
QPushButton#exportBtn:hover {
    background: #252000;
    color: #FFD700;
    border-color: #FFD700;
}
QPushButton#exportBtn:pressed {
    background: #100C00;
    color: #CC9600;
    border-color: #CC9600;
}
QPushButton#exportBtn:disabled {
    background: #0D1117;
    color: #3A2E00;
    border-color: #2A2000;
}

/* Cancel button — neon red */
QPushButton#cancelBtn {
    background: #1A0808;
    color: #FF5555;
    border: 1.5px solid #FF5555;
}
QPushButton#cancelBtn:hover {
    background: #250D0D;
    color: #FF7777;
    border-color: #FF7777;
}
QPushButton#cancelBtn:disabled {
    background: #0D1117;
    color: #3A1010;
    border-color: #2A0808;
}

/* Back button */
QPushButton#backBtn {
    background: #161B22;
    color: #8B949E;
    border: 1px solid #30363D;
    padding: 4px 12px;
    font-size: 8pt;
}
QPushButton#backBtn:hover {
    color: #00D4FF;
    border-color: #00D4FF;
    background: #1C2128;
}

/* ── Line Edit ────────────────────────────────── */
QLineEdit {
    background: #0A0E1A;
    color: #C9D1D9;
    border: 1px solid #30363D;
    border-radius: 5px;
    padding: 5px 9px;
    selection-background-color: #1C4E6E;
    selection-color: #00D4FF;
}
QLineEdit:focus {
    border-color: #00D4FF;
    background: #0D1117;
}
QLineEdit:disabled {
    background: #161B22;
    color: #484F58;
    border-color: #21262D;
}

/* ── Combo Box ────────────────────────────────── */
QComboBox {
    background: #0A0E1A;
    color: #C9D1D9;
    border: 1px solid #30363D;
    border-radius: 5px;
    padding: 4px 9px;
    min-height: 26px;
}
QComboBox:focus, QComboBox:on {
    border-color: #00D4FF;
}
QComboBox::drop-down {
    border: none;
    background: #1C2128;
    width: 24px;
    border-radius: 0 5px 5px 0;
    border-left: 1px solid #30363D;
}
QComboBox QAbstractItemView {
    background: #161B22;
    color: #C9D1D9;
    border: 1px solid #00D4FF;
    selection-background-color: #1C4E6E;
    selection-color: #00D4FF;
    outline: 0;
    padding: 2px;
}

/* ── Tables ───────────────────────────────────── */
QTableWidget {
    background: #0D1117;
    color: #C9D1D9;
    gridline-color: #1C2128;
    border: 1px solid #21262D;
    selection-background-color: #1C4E6E;
    selection-color: #E8F4FD;
    alternate-background-color: #111820;
}
QTableWidget::item {
    padding: 5px 6px;
    border: none;
}
QTableWidget::item:selected {
    background: #1C4E6E;
    color: #00D4FF;
}
QTableCornerButton::section {
    background: #161B22;
    border: none;
    border-right: 1px solid #21262D;
    border-bottom: 2px solid #00D4FF;
}
QHeaderView::section {
    background: #161B22;
    color: #00D4FF;
    border: none;
    border-right: 1px solid #21262D;
    border-bottom: 2px solid #00D4FF;
    padding: 7px 8px;
    font-weight: bold;
    font-size: 9pt;
    letter-spacing: 0.3px;
}
QHeaderView::section:hover {
    background: #1C2128;
    color: #33DFFF;
}

/* ── Progress Bar ─────────────────────────────── */
QProgressBar {
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 6px;
    text-align: center;
    color: #00D4FF;
    font-size: 8pt;
    font-weight: bold;
    min-height: 14px;
    max-height: 14px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #005577, stop:0.5 #00D4FF, stop:1 #39FF14);
    border-radius: 5px;
}

/* ── List Widget (file drop area) ─────────────── */
QListWidget {
    background: #0A0E1A;
    color: #C9D1D9;
    border: 1px solid #30363D;
    border-radius: 6px;
    padding: 4px;
    font-size: 8pt;
}
QListWidget::item {
    padding: 4px 6px;
    border-radius: 3px;
    border-bottom: 1px solid #161B22;
}
QListWidget::item:selected {
    background: #1C4E6E;
    color: #00D4FF;
}
QListWidget::item:hover {
    background: #1C2128;
    color: #C9D1D9;
}

/* ── PlainTextEdit (console log) ──────────────── */
QPlainTextEdit {
    background: #050A0D;
    color: #39FF14;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8pt;
    border: 1px solid #0D2010;
    border-radius: 4px;
    selection-background-color: #1C4E6E;
}

/* ── Scrollbars ───────────────────────────────── */
QScrollBar:vertical {
    background: #0D1117;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #21262D;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #00D4FF;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #0D1117;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #21262D;
    border-radius: 5px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #00D4FF;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Labels ───────────────────────────────────── */
QLabel {
    background: transparent;
    color: #C9D1D9;
}

/* ── Splitter ─────────────────────────────────── */
QSplitter::handle {
    background: #21262D;
}
QSplitter::handle:hover {
    background: #00D4FF;
}
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical   { height: 4px; }

/* ── CheckBox ─────────────────────────────────── */
QCheckBox {
    color: #C9D1D9;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background: #0D1117;
    border: 1px solid #30363D;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background: #00D4FF;
    border-color: #00D4FF;
}
QCheckBox::indicator:hover {
    border-color: #00D4FF;
}

/* ── SpinBox ──────────────────────────────────── */
QDoubleSpinBox, QSpinBox {
    background: #0A0E1A;
    color: #C9D1D9;
    border: 1px solid #30363D;
    border-radius: 5px;
    padding: 4px 8px;
}
QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #00D4FF;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {
    background: #1C2128;
    border: none;
    width: 18px;
    border-radius: 0 4px 4px 0;
}

/* ── Status Bar ───────────────────────────────── */
QStatusBar {
    background: #161B22;
    color: #8B949E;
    border-top: 1px solid #21262D;
    font-size: 8pt;
}

/* ── Tooltips ─────────────────────────────────── */
QToolTip {
    background: #161B22;
    color: #00D4FF;
    border: 1px solid #00D4FF;
    padding: 5px 10px;
    border-radius: 4px;
    font-size: 8pt;
}

/* ── Message Box ──────────────────────────────── */
QMessageBox {
    background: #161B22;
}
QMessageBox QLabel {
    color: #C9D1D9;
    background: #161B22;
    min-width: 300px;
}
QMessageBox QPushButton {
    min-width: 80px;
}
"""


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
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
               for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📡  PCI Drive Test Analyzer")
        self.resize(1260, 900)
        self.worker = None
        self.log = logging.getLogger("app")
        self._build_ui()
        self._load_config()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(4)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        root.addWidget(self.tabs, 1)

        # Tab 1 — PCI Analysis (primary use-case)
        self.pci_tab = PCITab()
        self.tabs.addTab(self.pci_tab, "📡  PCI Analysis")

        # Tab 2 — General Compare (original tool)
        compare_widget = QWidget()
        self._build_compare_tab(compare_widget)
        self.tabs.addTab(compare_widget, "⚖  General Compare")

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready — select the  📡 PCI Analysis  tab to begin.")

    def _build_compare_tab(self, parent: QWidget):
        root = QVBoxLayout(parent)
        root.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, 1)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Files
        files_box = QGroupBox("Step 1 — Files")
        files_layout = QHBoxLayout(files_box)

        main_col = QVBoxLayout()
        main_col.addWidget(QLabel("<b>Main files</b> (drag & drop folder or files):"))
        self.main_list = DropList()
        self.main_list.setMinimumHeight(110)
        main_col.addWidget(self.main_list)
        btn_row = QHBoxLayout()
        b_files  = QPushButton("Add Files…")
        b_folder = QPushButton("Add Folder…")
        b_clear  = QPushButton("Clear")
        b_files.clicked.connect(self._add_files)
        b_folder.clicked.connect(self._add_folder)
        b_clear.clicked.connect(self.main_list.clear)
        for b in (b_files, b_folder, b_clear):
            btn_row.addWidget(b)
        main_col.addLayout(btn_row)
        files_layout.addLayout(main_col, 2)

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
        b_show_main = QPushButton("Show columns of selected main file")
        b_show_main.clicked.connect(self._show_main_columns)
        ref_col.addWidget(b_show_main)
        b_show_ref = QPushButton("Show reference columns")
        b_show_ref.clicked.connect(self._show_ref_columns)
        ref_col.addWidget(b_show_ref)
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

        action_row = QHBoxLayout()
        self.run_btn = QPushButton("▶  Run Comparison")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.setMinimumHeight(38)
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        action_row.addWidget(self.run_btn, 3)
        action_row.addWidget(self.cancel_btn, 1)
        top_layout.addLayout(action_row)

        self.progress = QProgressBar()
        top_layout.addWidget(self.progress)

        splitter.addWidget(top)

        log_box = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        log_layout.addWidget(self.log_view)
        splitter.addWidget(log_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self.ref_path_edit.editingFinished.connect(self._refresh_ref_sheets)

    # ── Slots (General Compare tab) ──────────────────────────────────────────

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
        keys_ref  = [c.strip() for c in self.ref_keys_edit.text().split(",") if c.strip()]
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
        total_matched   = sum(len(r.matched)   for r in results)
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

    # ── Config persist ───────────────────────────────────────────────────────

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
            idx = self.mode_combo.findText(data.get("mode", Mode.EXISTS.value))
            if idx >= 0:
                self.mode_combo.setCurrentIndex(idx)
            self.case_check.setChecked(data.get("case_insensitive", True))
            self.main_keys_edit.setText(data.get("main_keys", ""))
            self.ref_keys_edit.setText(data.get("ref_keys", ""))
            self.diff_cols_edit.setText(data.get("diff_cols", ""))
            self.thr_main_edit.setText(data.get("thr_main", ""))
            self.thr_ref_edit.setText(data.get("thr_value", ""))
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
    app.setStyle("Fusion")

    # Dark Fusion palette (covers native widgets like QMessageBox, QFileDialog)
    palette = QPalette()
    _c = QColor
    palette.setColor(QPalette.ColorRole.Window,          _c("#0D1117"))
    palette.setColor(QPalette.ColorRole.WindowText,      _c("#C9D1D9"))
    palette.setColor(QPalette.ColorRole.Base,            _c("#0A0E1A"))
    palette.setColor(QPalette.ColorRole.AlternateBase,   _c("#161B22"))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     _c("#161B22"))
    palette.setColor(QPalette.ColorRole.ToolTipText,     _c("#00D4FF"))
    palette.setColor(QPalette.ColorRole.Text,            _c("#C9D1D9"))
    palette.setColor(QPalette.ColorRole.Button,          _c("#1C2128"))
    palette.setColor(QPalette.ColorRole.ButtonText,      _c("#C9D1D9"))
    palette.setColor(QPalette.ColorRole.BrightText,      _c("#00D4FF"))
    palette.setColor(QPalette.ColorRole.Link,            _c("#00D4FF"))
    palette.setColor(QPalette.ColorRole.Highlight,       _c("#1C4E6E"))
    palette.setColor(QPalette.ColorRole.HighlightedText, _c("#00D4FF"))
    palette.setColor(QPalette.ColorRole.Mid,             _c("#161B22"))
    palette.setColor(QPalette.ColorRole.Dark,            _c("#0D1117"))
    palette.setColor(QPalette.ColorRole.Shadow,          _c("#000000"))
    app.setPalette(palette)

    app.setStyleSheet(_NEON_STYLE)
    app.setApplicationName("PCI Drive Test Analyzer")

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
