"""
Tracer for UnitEditorView.load_project
"""

import sys
import os
import time
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from fmeda_tool.models import Project
from fmeda_tool.ui.unit_editor_view import UnitEditorView, FunctionalGroupTab
from fmeda_tool.ui.main_window import MainWindow


def trace_uniteditorview():
    test_path = "scratch/realistic_large_project.json"
    with open(test_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    project = Project.model_validate(data)
    
    window = MainWindow()
    editor = window.unit_editor_view
    
    print("\nTracing editor.load_project(project)...")
    
    # Measure overview refresh
    t0 = time.perf_counter()
    editor.overview_tab.refresh(project)
    print(f"1. overview_tab.refresh: {(time.perf_counter()-t0)*1000:.2f} ms")
    
    # Measure FunctionalGroupTab creations
    for idx, unit in enumerate(project.units):
        t0 = time.perf_counter()
        fg_tab = FunctionalGroupTab(unit, project, editor)
        t_tab_init = (time.perf_counter()-t0)*1000
        
        t0 = time.perf_counter()
        editor.unit_tabs.addTab(fg_tab, unit.name)
        t_add_tab = (time.perf_counter()-t0)*1000
        print(f"2.{idx+1}. FunctionalGroupTab.__init__ for '{unit.name}': {t_tab_init:.2f} ms, addTab: {t_add_tab:.2f} ms")
        
    # Measure setCurrentIndex
    t0 = time.perf_counter()
    editor.unit_tabs.setCurrentIndex(1)
    print(f"3. unit_tabs.setCurrentIndex(1): {(time.perf_counter()-t0)*1000:.2f} ms")
    
    # Measure active tab ensure_populated
    tab1 = editor.unit_tabs.widget(1)
    t0 = time.perf_counter()
    tab1.ensure_populated()
    print(f"4. tab1.ensure_populated(): {(time.perf_counter()-t0)*1000:.2f} ms")
    
    # Measure event loop processing
    t0 = time.perf_counter()
    app.processEvents()
    print(f"5. app.processEvents(): {(time.perf_counter()-t0)*1000:.2f} ms")


if __name__ == "__main__":
    trace_uniteditorview()
