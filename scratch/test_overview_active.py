"""
Test opening project with Overview as active tab.
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
from fmeda_tool.utils.performance import PerformanceTimer
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.ui.main_window import MainWindow


def test_overview_active():
    test_path = "scratch/realistic_large_project.json"
    with open(test_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    project = Project.model_validate(data)
    project.last_active_tab_id = "overview"  # Overview active
    
    timer = PerformanceTimer("Open Project (Overview Active)")
    
    timer.start_phase("file_reading")
    with open(test_path, 'r', encoding='utf-8') as f:
        raw = f.read()
    timer.end_phase("file_reading")
    
    timer.start_phase("json_parsing")
    p_data = json.loads(raw)
    timer.end_phase("json_parsing")
    
    timer.start_phase("pydantic_validation")
    proj = Project.model_validate(p_data)
    proj.last_active_tab_id = "overview"
    timer.end_phase("pydantic_validation")
    timer.record_project_metrics(proj, len(raw))
    
    timer.start_phase("project_calculation")
    CalculationService.calculate_project(proj)
    timer.end_phase("project_calculation")
    timer.counters.calculate_project_count += 1
    
    timer.start_phase("project_verification")
    ValidationService.validate_project(proj)
    timer.end_phase("project_verification")
    timer.counters.validate_project_count += 1
    
    worker_finished_timestamp = time.perf_counter()
    timer.start_phase("worker_finished_signal_delivery", start_time=worker_finished_timestamp)
    timer.end_phase("worker_finished_signal_delivery")
    
    timer.start_phase("mainwindow_project_assignment")
    window = MainWindow()
    window.current_project = proj
    window.setWindowTitle(f"FMEDA Tool - {proj.name}")
    window.undo_stack.clear()
    timer.end_phase("mainwindow_project_assignment")
    
    timer.start_phase("uniteditorview_load_project")
    window.unit_editor_view.load_project(proj, timer=timer)
    timer.end_phase("uniteditorview_load_project")
    
    timer.start_phase("loading_dialog_close_and_final_ui_refresh")
    app.processEvents()
    timer.end_phase("loading_dialog_close_and_final_ui_refresh")
    
    summary = timer.finish()
    
    print("\n" + "="*70)
    print("OVERVIEW ACTIVE - TIMING RECONCILIATION SUMMARY:")
    print("="*70)
    print(f"Total Open Duration   : {summary['total_ms']:.2f} ms")
    print(f"Accounted Phases Sum  : {summary['metrics']['accounted_phases_sum_ms']:.2f} ms")
    print(f"Unaccounted Duration  : {summary['metrics']['unaccounted_time_ms']:.2f} ms ({summary['metrics']['unaccounted_time_pct']:.2f}%)")
    print(f"Reconciliation Passed : {summary['metrics']['reconciliation_pass']}")
    print("="*70)
    for ph, ms in summary["timings_ms"].items():
        print(f"  {ph:<45}: {ms:>10.2f} ms")
    print("="*70)
    print("Call Counters:")
    for k, v in summary["counters"].items():
        print(f"  {k:<45}: {v:>10}")
    print("="*70)
    print("Lazy Loading Events:")
    for ev in summary["lazy_events"]:
        print(f"  {ev['unit']:<35} | {ev['action']:<20} | Rows: {ev['rows']:<5} | Time: {ev['ms']:>7.2f} ms | Reason: {ev['reason']}")
    print("="*70)


if __name__ == "__main__":
    test_overview_active()
