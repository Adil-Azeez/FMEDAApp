"""
Real GUI Benchmark and Profiling Script.
Simulates loading a real FMEDA project matching the user's observed metrics:
- 2 Functional Groups
- 299 Components
- 1,414 FMEDA Rows (max 782 rows in one group)
- Measures all 21 phases, widget allocations, and call counters.
"""

import sys
import os
import time
import json
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Force offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, ProjectStatus, SafetyStandard,
    Deviation, Mitigation, DiagnosticMeasure, DeviationType, DeviationSeverity, MitigationType
)
from fmeda_tool.utils.performance import PerformanceTimer
from fmeda_tool.services.project_service import ProjectService
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.ui.unit_editor_view import UnitEditorView, FunctionalGroupTab
from fmeda_tool.ui.main_window import MainWindow, ProjectLoadWorker


def generate_realistic_project(filepath: str):
    """Generates a project with 2 functional groups, 299 components, and 1,414 FMEDA rows."""
    deviations = [
        Deviation(
            id=f"dev_{i}",
            name=f"Deviation Rule {i}",
            description=f"Description for deviation {i}",
            deviation_type=DeviationType.DANGEROUS_DETECTED,
            severity=DeviationSeverity.HIGH,
            failure_mode=f"Failure mode for rule {i}"
        )
        for i in range(1, 10)
    ]
    mitigations = [
        Mitigation(
            id=f"mit_{i}",
            name=f"Mitigation Measure {i}",
            description=f"Description for mitigation {i}",
            mitigation_type=MitigationType.DIAGNOSTIC
        )
        for i in range(1, 10)
    ]
    diagnostic_measures = [
        DiagnosticMeasure(id=f"dm_{i}", description=f"Diagnostic Test {i}", dc=90.0 + (i % 10))
        for i in range(1, 15)
    ]
    
    # Group 1: 165 components (~825 failure mode rows)
    # Group 2: 134 components (~670 failure mode rows)
    groups_config = [
        ("FG 1 - Main Processor Subsystem", 165),
        ("FG 2 - Peripheral Power Subsystem", 134)
    ]
    
    units = []
    comp_global_idx = 1
    for group_name, comp_count in groups_config:
        components = []
        for c in range(comp_count):
            fms = {
                "Short Circuit": 35.0,
                "Open Circuit": 35.0,
                "Parameter Drift / Value Change": 15.0,
                "Intermittent Fault": 10.0,
                "Stuck at High/Low": 5.0
            }
            assignments = []
            for fm_idx, (fm_name, pct) in enumerate(fms.items()):
                assignments.append(
                    FailureModeAssignment(
                        failure_mode_name=fm_name,
                        failure_rate_percentage=pct,
                        classification="dangerous_failure" if fm_idx % 2 == 0 else "safe_failure",
                        dangerous_failure_percentage=100.0 if fm_idx % 2 == 0 else 0.0,
                        detection_percentage=90.0 if fm_idx == 0 else 0.0,
                        diagnostic_measure_id=f"dm_{(c % 14) + 1}" if fm_idx == 0 else None,
                        deviation_id=f"dev_{(c % 9) + 1}" if fm_idx == 1 else None,
                        mitigation_id=f"mit_{(c % 9) + 1}" if fm_idx == 2 else None,
                        notes="Automated realistic test assignment"
                    )
                )
            comp = Component(
                id=f"comp_real_{comp_global_idx}",
                name=f"IC_Component_{comp_global_idx}",
                position=f"U{comp_global_idx}",
                type="Microcontroller" if comp_global_idx % 5 == 0 else "Integrated Circuit",
                failure_rate=24.5,
                failure_modes=fms,
                failure_mode_assignments=assignments
            )
            components.append(comp)
            comp_global_idx += 1
            
        unit = Unit(
            id=f"unit_real_{len(units)+1}",
            name=group_name,
            description=f"Detailed functional group description for {group_name}",
            components=components
        )
        units.append(unit)
        
    project = Project(
        id="proj_realistic_large_001",
        name="Realistic Industrial Controller FMEDA",
        description="Realistic 1.4 MB project with 299 components and 1,414 rows",
        version="2.1.0",
        safety_standard=SafetyStandard.IEC_61508,
        deviations=deviations,
        mitigations=mitigations,
        diagnostic_measures=diagnostic_measures,
        units=units,
        last_active_tab_id=units[0].id  # Group 1 active
    )
    
    CalculationService.calculate_project(project)
    ProjectService.save_project_atomically(project, filepath)
    print(f"[OK] Generated realistic test project: {filepath} ({Path(filepath).stat().st_size / (1024*1024):.3f} MB)")
    return project


def run_benchmark():
    test_path = "scratch/realistic_large_project.json"
    os.makedirs("scratch", exist_ok=True)
    generate_realistic_project(test_path)
    
    print("\n--- Running Real GUI Load Benchmark ---")
    timer = PerformanceTimer("Real GUI Open Project")
    
    # 1. Background worker simulation (file read, json parse, migration, validation, calculation)
    t0 = time.perf_counter()
    timer.start_phase("file_reading")
    with open(test_path, 'r', encoding='utf-8') as f:
        raw_json = f.read()
    timer.end_phase("file_reading")
    
    timer.start_phase("json_parsing")
    data = json.loads(raw_json)
    timer.end_phase("json_parsing")
    
    timer.start_phase("pydantic_validation")
    project = Project.model_validate(data)
    timer.end_phase("pydantic_validation")
    timer.record_project_metrics(project, len(raw_json))
    
    timer.start_phase("project_calculation")
    CalculationService.calculate_project(project)
    timer.end_phase("project_calculation")
    
    timer.start_phase("project_verification")
    ValidationService.validate_project(project)
    timer.end_phase("project_verification")
    
    worker_elapsed = (time.perf_counter() - t0) * 1000.0
    print(f"[Worker Phase Complete] {worker_elapsed:.2f} ms")
    
    # 2. Main thread GUI construction
    main_window = MainWindow()
    
    timer.start_phase("mainwindow_project_assignment")
    main_window.current_project = project
    main_window.setWindowTitle(f"FMEDA Tool - {project.name}")
    main_window.undo_stack.clear()
    timer.end_phase("mainwindow_project_assignment")
    
    # 3. UnitEditorView load_project
    timer.start_phase("uniteditorview_load_project")
    main_window.unit_editor_view.load_project(project, timer=timer)
    timer.end_phase("uniteditorview_load_project")
    
    # 4. Qt event loop processing (layout calculation and widget rendering)
    timer.start_phase("qt_event_loop_processing")
    app.processEvents()
    timer.end_phase("qt_event_loop_processing")
    
    summary = timer.finish()
    
    print("\n" + "="*70)
    print(f"BENCHMARK COMPLETED: Total Time = {summary['total_ms']} ms")
    print("="*70)
    for phase, ms in summary["timings_ms"].items():
        print(f"  {phase:<45}: {ms:>10.2f} ms")
    print("="*70)
    print("Call Counters:")
    for k, v in summary["counters"].items():
        print(f"  {k:<45}: {v:>10}")
    print("="*70)
    print("Lazy Load Events:")
    for ev in summary["lazy_events"]:
        print(f"  {ev['unit']:<35} | {ev['action']:<20} | Rows: {ev['rows']:<5} | Time: {ev['ms']:>7.2f} ms | Reason: {ev['reason']}")
    print("="*70)


if __name__ == "__main__":
    run_benchmark()
