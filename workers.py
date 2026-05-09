"""QThread workers so the UI doesn't freeze during file I/O."""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional
import logging
import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from core.loaders import load_sheet, list_sheets
from core.comparator import compare, CompareConfig, CompareResult

log = logging.getLogger(__name__)


class CompareWorker(QThread):
    """Runs the full comparison on a background thread."""

    progress = pyqtSignal(int, int, str)         # current, total, message
    file_done = pyqtSignal(str, dict)            # source, summary dict
    finished_ok = pyqtSignal(list)               # List[CompareResult]
    failed = pyqtSignal(str)

    def __init__(
        self,
        main_files: List[Path],
        ref_file: Path,
        ref_sheet: Optional[str],
        cfg: CompareConfig,
        parent=None,
    ):
        super().__init__(parent)
        self.main_files = main_files
        self.ref_file = ref_file
        self.ref_sheet = ref_sheet
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.progress.emit(0, 1, f"Loading reference: {self.ref_file.name}")
            ref_df = load_sheet(self.ref_file, self.ref_sheet)
            log.info("Reference loaded: %d rows", len(ref_df))

            # Pre-count work units = total sheets across all files
            file_sheets = []
            for f in self.main_files:
                try:
                    sheets = list_sheets(f)
                except Exception as e:
                    log.exception("Could not list sheets for %s", f)
                    self.progress.emit(0, 1, f"⚠ Skipping {f.name}: {e}")
                    continue
                file_sheets.append((f, sheets))
            total = sum(len(sh) for _, sh in file_sheets) or 1

            results: List[CompareResult] = []
            done = 0
            for f, sheets in file_sheets:
                for sh in sheets:
                    if self._cancel:
                        self.progress.emit(done, total, "Cancelled.")
                        self.finished_ok.emit(results)
                        return
                    self.progress.emit(done, total, f"Processing {f.name} [{sh}]")
                    try:
                        df = load_sheet(f, sh)
                        result = compare(df, ref_df, self.cfg, source=str(f), sheet=sh)
                        results.append(result)
                        self.file_done.emit(str(f), result.summary)
                    except Exception as e:
                        log.exception("Failed on %s [%s]", f, sh)
                        self.progress.emit(done, total, f"⚠ {f.name} [{sh}]: {e}")
                    done += 1

            self.progress.emit(total, total, f"Done. {len(results)} comparisons completed.")
            self.finished_ok.emit(results)

        except Exception as e:
            log.exception("Worker crashed")
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")
