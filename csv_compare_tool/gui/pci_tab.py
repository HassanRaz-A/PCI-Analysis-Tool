"""PCI Analysis tab - purpose-built for telecom drive test PCI lookup workflows.

Workflow:
  1. Load CSV drive test files (drag-and-drop or browse)
  2. Load reference Excel (e.g. PCI Lookup.xlsx) and pick its PCI column
  3. Auto-detect LTE / NR PCI columns (or enter manually)
  4. Run → Summary page + PCI Detail page with pie chart
  5. Export to Excel
"""
from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import List, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFormLayout,
    QPushButton, QLabel, QFileDialog, QComboBox,
    QGroupBox, QProgressBar, QPlainTextEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLineEdit,
)

from core.loaders import load_sheet, list_sheets, get_columns, discover_files, SUPPORTED_EXTS
from core.pci_analyzer import (
    PCIResult, analyze_pci, detect_pci_columns,
    detect_context_columns, find_column, csv_short_name,
)
from gui.widgets import DropList

log = logging.getLogger("pci_tab")

# ── Table cell background colors (neon dark palette) ────────────────────────
_GREEN = QColor("#0E2D1A")   # dark neon green cell
_RED   = QColor("#2D0E0E")   # dark neon red cell
_AMBER = QColor("#2D2000")   # dark amber cell

# ── Matplotlib neon palette ──────────────────────────────────────────────────
_CHART_BG      = "#0D1117"
_CHART_AX_BG   = "#111820"
_NEON_GREEN    = "#39FF14"
_NEON_RED      = "#FF2D6B"
_NEON_GREEN2   = "#7FFF00"   # lighter green for "Others in ref"
_NEON_RED2     = "#FF7799"   # lighter pink  for "Others unique"
_CYAN          = "#00D4FF"
_TEXT_MAIN     = "#C9D1D9"
_TEXT_DIM      = "#8B949E"


# ── Background worker ────────────────────────────────────────────────────────

class PCIWorker(QThread):
    progress    = pyqtSignal(int, int, str)
    file_done   = pyqtSignal(object)    # PCIResult
    finished_ok = pyqtSignal(list)      # List[PCIResult]
    failed      = pyqtSignal(str)

    def __init__(self, main_files, ref_file, ref_sheet,
                 ref_pci_col, lte_col="", nr_col="", parent=None):
        super().__init__(parent)
        self.main_files  = main_files
        self.ref_file    = Path(ref_file)
        self.ref_sheet   = ref_sheet
        self.ref_pci_col = ref_pci_col
        self.lte_col     = lte_col
        self.nr_col      = nr_col
        self._cancel     = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.progress.emit(0, 1, f"Loading reference: {self.ref_file.name}")
            ref_df = load_sheet(self.ref_file, self.ref_sheet)

            if self.ref_pci_col not in ref_df.columns:
                self.failed.emit(
                    f"Reference PCI column '{self.ref_pci_col}' not found.\n"
                    f"Available columns: {list(ref_df.columns)}"
                )
                return

            ref_pci_values = (
                set(ref_df[self.ref_pci_col].dropna().astype(str).str.strip())
                - {"", "nan", "None"}
            )
            self.progress.emit(0, 1,
                f"Reference loaded — {len(ref_pci_values)} unique PCIs in reference.")

            file_sheets: list = []
            for f in self.main_files:
                try:
                    file_sheets.append((f, list_sheets(f)))
                except Exception as e:
                    self.progress.emit(0, 1, f"⚠ Skipping {Path(f).name}: {e}")
            total = sum(len(sh) for _, sh in file_sheets) or 1

            results: List[PCIResult] = []
            done = 0
            for f, sheets in file_sheets:
                for sh in sheets:
                    if self._cancel:
                        self.progress.emit(done, total, "Cancelled.")
                        self.finished_ok.emit(results)
                        return
                    fname = Path(f).name
                    self.progress.emit(done, total, f"Processing {fname} [{sh}]")
                    try:
                        df = load_sheet(f, sh)

                        used_col = None
                        if self.lte_col:
                            used_col = find_column(df, self.lte_col)
                        if used_col is None and self.nr_col:
                            used_col = find_column(df, self.nr_col)
                        if used_col is None:
                            detected = detect_pci_columns(df)
                            used_col = detected.get("lte") or detected.get("nr")
                        if used_col is None:
                            self.progress.emit(done, total,
                                f"⚠ {fname}: No PCI column found — skipped")
                            done += 1
                            continue

                        ctx_cols = detect_context_columns(df)
                        result = analyze_pci(
                            df, used_col, ref_pci_values,
                            source=str(f), sheet=sh,
                            context_cols=ctx_cols,
                        )
                        results.append(result)
                        self.file_done.emit(result)
                    except Exception as e:
                        log.exception("Failed on %s [%s]", f, sh)
                        self.progress.emit(done, total, f"⚠ {fname} [{sh}]: {e}")
                    done += 1

            self.progress.emit(total, total,
                f"Done. {len(results)} files processed.")
            self.finished_ok.emit(results)

        except Exception as e:
            log.exception("PCIWorker crashed")
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")


# ── Pie chart widget ─────────────────────────────────────────────────────────

class PieChartWidget(QWidget):
    MAX_SLICES = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(5, 4.5), facecolor=_CHART_BG, constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet(f"background-color: {_CHART_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self._placeholder()

    def _placeholder(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(_CHART_AX_BG)
        ax.text(0.5, 0.5,
                "Select a file in the Summary tab\nto view its PCI chart",
                ha="center", va="center", fontsize=12,
                color=_CYAN, fontweight="bold",
                transform=ax.transAxes, linespacing=1.7)
        ax.axis("off")
        self.canvas.draw()

    def plot(self, result: PCIResult):
        self.figure.clear()
        counts = result.pci_counts
        if counts.empty:
            ax = self.figure.add_subplot(111)
            ax.set_facecolor(_CHART_AX_BG)
            ax.text(0.5, 0.5, "No PCI data", ha="center", va="center",
                    color=_TEXT_DIM, fontsize=11)
            ax.axis("off")
            self.canvas.draw()
            return

        if len(counts) > self.MAX_SLICES:
            top  = counts.iloc[:self.MAX_SLICES]
            rest = counts.iloc[self.MAX_SLICES:]
            labels = list(top.index)
            values = list(top.values)
            colors = [_NEON_GREEN if p in result.in_ref_pcis else _NEON_RED
                      for p in top.index]
            rest_r = int(rest[rest.index.isin(result.in_ref_pcis)].sum())
            rest_u = int(rest[rest.index.isin(result.unique_pcis)].sum())
            if rest_r:
                labels.append(
                    f"Others — In Ref ({int(rest.index.isin(result.in_ref_pcis).sum())} PCIs)")
                values.append(rest_r)
                colors.append(_NEON_GREEN2)
            if rest_u:
                labels.append(
                    f"Others — Unique ({int(rest.index.isin(result.unique_pcis).sum())} PCIs)")
                values.append(rest_u)
                colors.append(_NEON_RED2)
        else:
            labels = list(counts.index)
            values = list(counts.values)
            colors = [_NEON_GREEN if p in result.in_ref_pcis else _NEON_RED
                      for p in counts.index]

        total = sum(values)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(_CHART_AX_BG)

        wedges, _, autotexts = ax.pie(
            values, colors=colors,
            autopct=lambda pct: f"{pct:.1f}%" if pct >= 3 else "",
            startangle=90, pctdistance=0.75,
            wedgeprops={"linewidth": 1.2, "edgecolor": _CHART_BG},
        )
        for at in autotexts:
            at.set_fontsize(7)
            at.set_color("white")
            at.set_fontweight("bold")

        legend_labels = [
            f"PCI {lbl}  —  {v:,}  ({v / total * 100:.1f}%)"
            for lbl, v in zip(labels, values)
        ]
        legend = ax.legend(
            wedges, legend_labels,
            loc="lower center", bbox_to_anchor=(0.5, -0.32),
            ncol=min(2, max(1, len(labels) // 7 + 1)),
            fontsize=7, framealpha=0.85,
            facecolor="#161B22", edgecolor=_CYAN,
            labelcolor=_TEXT_MAIN,
        )
        legend.get_frame().set_linewidth(0.8)

        sname = result.short_name
        title_top = f"[{result.floor}]  {sname}" if result.floor else sname
        if len(title_top) > 55:
            title_top = title_top[:53] + "…"
        ax.set_title(
            f"{title_top}\n"
            f"{result.total_rows:,} rows  |  "
            f"{len(result.in_ref_pcis)} in ref  |  "
            f"{len(result.unique_pcis)} unique",
            fontsize=8.5,
            color=_CYAN,
            fontweight="bold",
            pad=10,
        )
        self.canvas.draw()


# ── PCI Analysis tab ─────────────────────────────────────────────────────────

class PCITab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: Optional[PCIWorker] = None
        self._results: List[PCIResult] = []
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(6, 6, 6, 4)

        # ── Step 1: Files ────────────────────────────────────────────────────
        files_box = QGroupBox("Step 1 — Load Files")
        files_layout = QHBoxLayout(files_box)
        files_layout.setSpacing(16)

        csv_col = QVBoxLayout()
        lbl_csv = QLabel("<b>Drive-test CSV files</b>  (drag & drop or browse):")
        lbl_csv.setStyleSheet("color:#C9D1D9;")
        csv_col.addWidget(lbl_csv)
        self.csv_list = DropList()
        self.csv_list.setMinimumHeight(90)
        csv_col.addWidget(self.csv_list)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        for label, slot in [
            ("Add Files…",               self._add_csv_files),
            ("Add Folder (flat)…",       self._add_csv_folder),
            ("Add Folder + Subfolders…", self._add_csv_folder_recursive),
            ("Clear",                    self.csv_list.clear),
        ]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        sub_hint = QLabel(
            "Use  <b>Add Folder + Subfolders</b>  when each subfolder is a floor / zone."
        )
        sub_hint.setStyleSheet("color:#8B949E; font-style:italic; font-size:9px;")
        csv_col.addLayout(btn_row)
        csv_col.addWidget(sub_hint)
        files_layout.addLayout(csv_col, 3)

        ref_col = QVBoxLayout()
        ref_col.setSpacing(4)
        lbl_ref = QLabel("<b>Reference file</b>  (PCI Lookup Excel):")
        lbl_ref.setStyleSheet("color:#C9D1D9;")
        ref_col.addWidget(lbl_ref)
        ref_path_row = QHBoxLayout()
        self.ref_path_edit = QLineEdit()
        self.ref_path_edit.setPlaceholderText("Select reference Excel…")
        b_pick_ref = QPushButton("Browse…")
        b_pick_ref.clicked.connect(self._pick_ref)
        ref_path_row.addWidget(self.ref_path_edit)
        ref_path_row.addWidget(b_pick_ref)
        ref_col.addLayout(ref_path_row)
        ref_col.addWidget(QLabel("Reference sheet:"))
        self.ref_sheet_combo = QComboBox()
        ref_col.addWidget(self.ref_sheet_combo)
        ref_col.addWidget(QLabel("Reference PCI column:"))
        self.ref_pci_combo = QComboBox()
        ref_col.addWidget(self.ref_pci_combo)
        b_refresh = QPushButton("Refresh columns")
        b_refresh.clicked.connect(self._refresh_ref)
        ref_col.addWidget(b_refresh)
        ref_col.addStretch()
        files_layout.addLayout(ref_col, 2)
        root.addWidget(files_box)

        # ── Step 2: PCI column names ─────────────────────────────────────────
        step2_box = QGroupBox("Step 2 — PCI Column Names  (auto-detect fills these automatically)")
        step2_form = QFormLayout(step2_box)
        step2_form.setSpacing(6)

        self.lte_col_edit = QLineEdit()
        self.lte_col_edit.setPlaceholderText("e.g.  (1)(TopN)PCI")
        step2_form.addRow("LTE PCI column:", self.lte_col_edit)

        self.nr_col_edit = QLineEdit()
        self.nr_col_edit.setPlaceholderText("e.g.  (NR TopN) Beam Cell Id")
        step2_form.addRow("NR / 5G PCI column:", self.nr_col_edit)

        b_auto = QPushButton("⚡  Auto-detect from first CSV")
        b_auto.clicked.connect(self._auto_detect)
        step2_form.addRow("", b_auto)

        hint = QLabel(
            "Column names are matched flexibly — ignores extra spaces and capitalisation.  "
            "Leave blank to skip that technology."
        )
        hint.setStyleSheet("color:#8B949E; font-style:italic; font-size:9px;")
        hint.setWordWrap(True)
        step2_form.addRow("", hint)
        root.addWidget(step2_box)

        # ── Action row ───────────────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.run_btn = QPushButton("▶  Run PCI Analysis")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.setMinimumHeight(40)
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(10)
        self.run_btn.setFont(bold)
        self.run_btn.clicked.connect(self._run)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)

        self.export_btn = QPushButton("📥  Export to Excel…")
        self.export_btn.setObjectName("exportBtn")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export)

        action_row.addWidget(self.run_btn, 4)
        action_row.addWidget(self.cancel_btn, 1)
        action_row.addWidget(self.export_btn, 2)
        root.addLayout(action_row)

        self.progress = QProgressBar()
        root.addWidget(self.progress)

        # ── Results (two-tab layout) ──────────────────────────────────────────
        results_box = QGroupBox("Results")
        results_layout = QVBoxLayout(results_box)
        results_layout.setContentsMargins(6, 10, 6, 6)

        self.results_tabs = QTabWidget()
        results_layout.addWidget(self.results_tabs, 1)

        # ── Tab 0: Summary ────────────────────────────────────────────────────
        summary_widget = QWidget()
        summary_layout = QVBoxLayout(summary_widget)
        summary_layout.setContentsMargins(4, 6, 4, 4)
        summary_layout.setSpacing(4)

        tip = QLabel("Click any row to jump to the PCI Detail tab for that file.")
        tip.setStyleSheet("color:#8B949E; font-style:italic; font-size:9px;")
        summary_layout.addWidget(tip)

        self.summary_table = QTableWidget(0, 8)
        self.summary_table.setHorizontalHeaderLabels([
            "Floor / Zone", "Measurement", "PCI Column",
            "Total Rows", "Unique PCIs", "In Reference", "NOT in Ref", "% Matched",
        ])
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.setShowGrid(False)
        hdr = self.summary_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.summary_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.summary_table.currentCellChanged.connect(
            lambda row, _c, _pr, _pc: self._on_summary_row_clicked(row)
        )
        summary_layout.addWidget(self.summary_table, 1)
        self.results_tabs.addTab(summary_widget, "📊  Summary")

        # ── Tab 1: PCI Detail ─────────────────────────────────────────────────
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(4, 6, 4, 4)
        detail_layout.setSpacing(5)

        file_row = QHBoxLayout()
        lbl_file = QLabel("File:")
        lbl_file.setStyleSheet("color:#8B949E;")
        file_row.addWidget(lbl_file)
        self.detail_file_combo = QComboBox()
        self.detail_file_combo.setMinimumWidth(340)
        self.detail_file_combo.currentIndexChanged.connect(self._on_detail_file_changed)
        file_row.addWidget(self.detail_file_combo, 1)
        b_back = QPushButton("◀  Back to Summary")
        b_back.setObjectName("backBtn")
        b_back.clicked.connect(lambda: self.results_tabs.setCurrentIndex(0))
        file_row.addWidget(b_back)
        detail_layout.addLayout(file_row)

        self.detail_info_lbl = QLabel("")
        self.detail_info_lbl.setStyleSheet(
            "font-weight:bold; color:#00D4FF; padding:3px 0; font-size:9pt;"
        )
        self.detail_info_lbl.setWordWrap(True)
        detail_layout.addWidget(self.detail_info_lbl)

        detail_note = QLabel(
            "🟢  Green = PCI found in reference     "
            "🔴  Red = PCI NOT in reference (unique / unexpected)"
        )
        detail_note.setStyleSheet("color:#8B949E; font-style:italic; font-size:9px;")
        detail_layout.addWidget(detail_note)

        detail_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.detail_table = QTableWidget(0, 4)
        self.detail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.detail_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.setShowGrid(False)
        detail_splitter.addWidget(self.detail_table)

        self.chart = PieChartWidget()
        detail_splitter.addWidget(self.chart)
        detail_splitter.setStretchFactor(0, 1)
        detail_splitter.setStretchFactor(1, 1)
        detail_layout.addWidget(detail_splitter, 1)
        self.results_tabs.addTab(detail_widget, "🔍  PCI Detail")

        root.addWidget(results_box, 1)

        # ── Log strip ─────────────────────────────────────────────────────────
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(68)
        self.log_view.setMaximumBlockCount(500)
        root.addWidget(self.log_view)

        # Wire ref combos
        self.ref_sheet_combo.currentTextChanged.connect(self._refresh_ref_pci_cols)
        self.ref_path_edit.editingFinished.connect(self._refresh_ref)

    # ── File picking ─────────────────────────────────────────────────────────

    def _add_csv_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select CSV/Excel files", "",
            "Data files (*.csv *.tsv *.xlsx *.xls);;All files (*)",
        )
        for f in files:
            self.csv_list.add_path(Path(f))

    def _add_csv_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select folder (flat — no subfolders)")
        if d:
            for f in discover_files(d, recursive=False):
                self.csv_list.add_path(f)

    def _add_csv_folder_recursive(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select root folder — all subfolders (floors) will be scanned"
        )
        if d:
            files = discover_files(d, recursive=True)
            for f in files:
                self.csv_list.add_path(f)
            self._log(f"Loaded {len(files)} files from '{Path(d).name}' and its subfolders.")

    def _pick_ref(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select reference file", "",
            "Excel/CSV files (*.xlsx *.xls *.csv);;All files (*)",
        )
        if f:
            self.ref_path_edit.setText(f)
            self._refresh_ref()

    def _refresh_ref(self):
        path = self.ref_path_edit.text().strip()
        self.ref_sheet_combo.blockSignals(True)
        self.ref_sheet_combo.clear()
        self.ref_pci_combo.clear()
        self.ref_sheet_combo.blockSignals(False)
        if not path or not Path(path).exists():
            return
        try:
            for s in list_sheets(path):
                self.ref_sheet_combo.addItem(s)
        except Exception as e:
            self._log(f"Could not read reference: {e}")

    def _refresh_ref_pci_cols(self, sheet: str):
        path = self.ref_path_edit.text().strip()
        self.ref_pci_combo.clear()
        if not path or not sheet:
            return
        try:
            cols = get_columns(path, sheet or None)
            for c in cols:
                self.ref_pci_combo.addItem(c)
            for i, c in enumerate(cols):
                if "pci" in str(c).lower():
                    self.ref_pci_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            self._log(f"Could not read reference columns: {e}")

    def _auto_detect(self):
        files = self.csv_list.files()
        if not files:
            QMessageBox.information(self, "No CSV files", "Add CSV files first.")
            return
        try:
            sample = load_sheet(files[0])
            detected = detect_pci_columns(sample)
            lte = detected.get("lte") or ""
            nr  = detected.get("nr")  or ""
            self.lte_col_edit.setText(lte)
            self.nr_col_edit.setText(nr)

            ctx = detect_context_columns(sample)
            lines = []
            if lte:
                lines.append(f"LTE PCI column:  {lte}")
            if nr:
                lines.append(f"NR / 5G column:  {nr}")
            if ctx:
                lines.append(f"Context columns: {', '.join(ctx)}")

            if lines:
                self._log("Auto-detected — " + "   |   ".join(lines))
                QMessageBox.information(
                    self, "Columns Detected",
                    "\n".join(lines) + "\n\nEdit the fields above if needed.",
                )
            else:
                self._log("Auto-detect: no LTE/NR PCI columns found.")
                QMessageBox.warning(
                    self, "No PCI Columns Found",
                    f"Could not find LTE or NR PCI columns in:\n{files[0].name}\n\n"
                    "Please type the column names manually in Step 2.",
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Run / Cancel ─────────────────────────────────────────────────────────

    def _run(self):
        files = self.csv_list.files()
        if not files:
            QMessageBox.warning(self, "No files", "Add CSV files first.")
            return
        ref = self.ref_path_edit.text().strip()
        if not ref or not Path(ref).exists():
            QMessageBox.warning(self, "No reference", "Select a valid reference file.")
            return
        ref_pci_col = self.ref_pci_combo.currentText().strip()
        if not ref_pci_col:
            QMessageBox.warning(self, "No reference PCI column",
                                "Select the PCI column from the reference file.")
            return
        lte_col = self.lte_col_edit.text().strip()
        nr_col  = self.nr_col_edit.text().strip()
        if not lte_col and not nr_col:
            QMessageBox.warning(self, "No PCI column",
                                "Click 'Auto-detect' or type column names in Step 2.")
            return

        self._results = []
        self._clear_results()
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.export_btn.setEnabled(False)
        self.progress.setValue(0)
        self._log(
            f"--- PCI Analysis started  |  "
            f"LTE='{lte_col}'  NR='{nr_col}'  "
            f"Ref col='{ref_pci_col}' ---"
        )

        self.worker = PCIWorker(
            main_files=files,
            ref_file=Path(ref),
            ref_sheet=self.ref_sheet_combo.currentText() or None,
            ref_pci_col=ref_pci_col,
            lte_col=lte_col,
            nr_col=nr_col,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()

    # ── Worker callbacks ─────────────────────────────────────────────────────

    def _on_progress(self, cur: int, total: int, msg: str):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(cur)
        if msg:
            self._log(msg)

    def _on_file_done(self, result: PCIResult):
        self._results.append(result)
        self._append_summary_row(result)
        label = f"{result.floor}  /  {result.short_name}" if result.floor else result.short_name
        self.detail_file_combo.addItem(label)

    def _on_done(self, results: list):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if not results:
            self._log("No results produced.")
            return
        self.export_btn.setEnabled(True)
        in_ref_rows = sum(r.in_ref_row_count for r in results)
        total_rows  = sum(r.total_rows        for r in results)
        self._log(
            f"--- Done: {len(results)} files  |  "
            f"{total_rows:,} PCI rows  |  "
            f"{in_ref_rows:,} matched reference "
            f"({100 * in_ref_rows / max(total_rows, 1):.1f}%)  |  "
            f"{total_rows - in_ref_rows:,} unmatched ---"
        )
        if self.summary_table.rowCount() > 0:
            self.summary_table.selectRow(0)

    def _on_failed(self, msg: str):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._log(f"FAILED: {msg}")
        QMessageBox.critical(self, "Analysis failed", msg)

    # ── Results display ───────────────────────────────────────────────────────

    def _clear_results(self):
        self.summary_table.setRowCount(0)
        self.detail_table.setRowCount(0)
        self.detail_table.setColumnCount(4)
        self.detail_file_combo.clear()
        self.detail_info_lbl.setText("")
        self.chart._placeholder()

    def _append_summary_row(self, result: PCIResult):
        row = self.summary_table.rowCount()
        self.summary_table.insertRow(row)
        s = result.summary
        pct = s["% Rows Matched"]
        bg_pct = _GREEN if pct >= 80 else (_AMBER if pct >= 40 else _RED)
        values = [
            result.floor,
            result.short_name,
            s["PCI Column Used"],
            f"{s['Total Rows (with PCI)']:,}",
            str(s["Unique PCIs Found"]),
            str(s["PCIs in Reference"]),
            str(s["PCIs NOT in Reference"]),
            f"{pct}%",
        ]
        for col_idx, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if col_idx == 7:
                item.setBackground(bg_pct)
            elif col_idx == 5:
                item.setBackground(_GREEN)
            elif col_idx == 6 and s["PCIs NOT in Reference"] > 0:
                item.setBackground(_RED)
            self.summary_table.setItem(row, col_idx, item)

    def _on_summary_row_clicked(self, row: int):
        if row < 0 or row >= len(self._results):
            return
        self.detail_file_combo.blockSignals(True)
        self.detail_file_combo.setCurrentIndex(row)
        self.detail_file_combo.blockSignals(False)
        self._update_detail(row)
        self.results_tabs.setCurrentIndex(1)

    def _on_detail_file_changed(self, idx: int):
        if idx >= 0:
            self._update_detail(idx)

    def _update_detail(self, idx: int):
        if idx < 0 or idx >= len(self._results):
            return
        result = self._results[idx]
        self._show_detail(result)
        self.chart.plot(result)
        s = result.summary
        ctx_info = (f"  |  Context: {', '.join(result.context_cols)}"
                    if result.context_cols else "")
        floor_tag = f"[{result.floor}]  " if result.floor else ""
        self.detail_info_lbl.setText(
            f"{floor_tag}{result.short_name}  |  "
            f"PCI col: {s['PCI Column Used']}  |  "
            f"{s['Total Rows (with PCI)']:,} rows  |  "
            f"{s['PCIs in Reference']} in ref  |  "
            f"{s['PCIs NOT in Reference']} unique  |  "
            f"{s['% Rows Matched']}% matched"
            + ctx_info
        )

    def _show_detail(self, result: PCIResult):
        df = result.detail_df()
        cols = list(df.columns)

        self.detail_table.setColumnCount(len(cols))
        self.detail_table.setHorizontalHeaderLabels(cols)
        hdr = self.detail_table.horizontalHeader()
        for i in range(len(cols)):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        if cols:
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)

        self.detail_table.setRowCount(len(df))
        for row_idx, (_, row_data) in enumerate(df.iterrows()):
            in_ref = str(row_data.get("In Reference", "")) == "Yes"
            row_bg = _GREEN if in_ref else _RED
            for col_idx, col_name in enumerate(cols):
                val = row_data[col_name]
                if col_name == "Count":
                    text = f"{int(val):,}" if str(val) not in ("", "nan") else ""
                elif col_name == "% of Total":
                    text = f"{val}%"
                else:
                    text = str(val) if str(val) not in ("nan", "None") else ""
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx < 4:
                    item.setBackground(row_bg)
                self.detail_table.setItem(row_idx, col_idx, item)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self):
        if not self._results:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, "Save PCI Report", "pci_analysis_report.xlsx",
            "Excel workbook (*.xlsx)",
        )
        if not out:
            return
        try:
            from core.exporter import export_pci_results
            path = export_pci_results(self._results, out)
            self._log(f"Report saved → {path}")
            QMessageBox.information(self, "Saved", f"Report saved to:\n{path}")
        except Exception as e:
            log.exception("PCI export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log_view.appendPlainText(msg)
        log.info(msg)
