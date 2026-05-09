"""Launch the CSV/Excel Comparison Tool.

Run this file from anywhere:
    python main.py
"""
import sys
from pathlib import Path

# Add csv_compare_tool/ to the path so all imports resolve correctly
_pkg = Path(__file__).parent / "csv_compare_tool"
if str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))

from gui.main_window import run_app

if __name__ == "__main__":
    run_app()
