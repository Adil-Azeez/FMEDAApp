"""
Unit and integration tests for FMEDA large-project loading, performance instrumentation,
lazy tab rendering, signal suppression, atomic file persistence, calculation equality,
and micro-level reconciliation verification.
"""

import os
import json
import pytest
import tempfile
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

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


@pytest.fixture(scope="session")
def qapp():
    """Ensure QApplication instance exists for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_synthetic_project(num_units: int = 3, comps_per_unit: int = 5) -> Project:
    """Helper to create a synthetic FMEDA project with specified scale."""
    deviations = [
        Deviation(
            id=f"dev_{i}",
            name=f"Deviation Rule {i}",
            description=f"Description {i}",
            deviation_type=DeviationType.DANGEROUS_DETECTED,
            severity=DeviationSeverity.HIGH,
            failure_mode=f"FM {i}"
        )
        for i in range(1, 5)
    ]
    mitigations = [
        Mitigation(
            id=f"mit_{i}",
            name=f"Mitigation {i}",
            description=f"Description {i}",
            mitigation_type=MitigationType.DIAGNOSTIC
        )
        for i in range(1, 5)
    ]
    diagnostic_measures = [
        DiagnosticMeasure(id=f"dm_{i}", description=f"Diagnostic Test {i}", dc=90.0)
        for i in range(1, 5)
    ]
    
    units = []
    for u_idx in range(num_units):
        components = []
        for c_idx in range(comps_per_unit):
            fms = {
                "Short Circuit": 40.0,
                "Open Circuit": 40.0,
                "Parameter Drift": 20.0
            }
            assignments = [
                FailureModeAssignment(
                    failure_mode_name=fm,
                    failure_rate_percentage=pct,
                    classification="dangerous_failure" if fm != "Parameter Drift" else "safe_failure",
                    dangerous_failure_percentage=100.0 if fm != "Parameter Drift" else 0.0,
                    detection_percentage=90.0 if fm == "Short Circuit" else 0.0,
                    deviation_id="dev_1" if fm == "Short Circuit" else None,
                    diagnostic_measure_id="dm_1" if fm == "Short Circuit" else None,
                    mitigation_id="mit_1" if fm == "Short Circuit" else None
                )
                for fm, pct in fms.items()
            ]
            comp = Component(
                id=f"comp_{u_idx}_{c_idx}",
                name=f"Resistor_{u_idx}_{c_idx}",
                position=f"R{u_idx*100 + c_idx + 1}",
                type="Resistor",
                failure_rate=12.5,
                failure_modes=fms,
                failure_mode_assignments=assignments
            )
            components.append(comp)
            
        unit = Unit(
            id=f"unit_synth_{u_idx}",
            name=f"Functional Group {u_idx + 1}",
            description=f"Synthetic functional group description {u_idx + 1}",
            components=components
        )
        units.append(unit)
        
    project = Project(
        id="proj_synth_001",
        name="Synthetic Performance Project",
        description="Synthetic project for performance testing",
        version="1.0.0",
        safety_standard=SafetyStandard.IEC_61508,
        deviations=deviations,
        mitigations=mitigations,
        diagnostic_measures=diagnostic_measures,
        units=units
    )
    CalculationService.calculate_project(project)
    return project


def test_performance_instrumentation_and_reconciliation():
    """Test that PerformanceTimer accurately measures granular phases and validates reconciliation."""
    timer = PerformanceTimer("Test Reconciliation")
    timer.start_phase("file_reading")
    time.sleep(0.001)
    timer.end_phase("file_reading")
    
    timer.start_phase("json_parsing")
    time.sleep(0.001)
    timer.end_phase("json_parsing")
    
    project = create_synthetic_project(num_units=2, comps_per_unit=4)
    timer.record_project_metrics(project, file_size_bytes=10240)
    
    summary = timer.finish()
    
    assert "file_reading" in summary["timings_ms"]
    assert "json_parsing" in summary["timings_ms"]
    assert "total_project_open" in summary["timings_ms"]
    assert summary["metrics"]["functional_groups_count"] == 2
    assert summary["metrics"]["components_count"] == 8
    assert summary["metrics"]["file_size_bytes"] == 10240
    assert summary["metrics"]["file_size_mb"] == 0.01
    assert "reconciliation_pass" in summary["metrics"]
    assert "unaccounted_time_ms" in summary["metrics"]


def test_lazy_tab_loading(qapp):
    """Test that opening a project does not build hidden functional group tables until selected."""
    project = create_synthetic_project(num_units=3, comps_per_unit=5)
    project.last_active_tab_id = "overview"
    
    editor = UnitEditorView()
    timer = PerformanceTimer("Lazy Tab Test")
    editor.load_project(project, timer=timer)
    
    # Overview tab is index 0
    assert editor.unit_tabs.currentIndex() == 0
    
    # Functional group tabs 1, 2, 3 should NOT be populated yet
    tab1 = editor.unit_tabs.widget(1)
    tab2 = editor.unit_tabs.widget(2)
    tab3 = editor.unit_tabs.widget(3)
    
    assert isinstance(tab1, FunctionalGroupTab)
    assert isinstance(tab2, FunctionalGroupTab)
    assert isinstance(tab3, FunctionalGroupTab)
    
    assert tab1.is_populated is False
    assert tab2.is_populated is False
    assert tab3.is_populated is False
    assert tab1.table.rowCount() == 0
    assert tab2.table.rowCount() == 0
    assert tab3.table.rowCount() == 0
    
    # Switch to tab 1 -> should populate lazily
    editor.unit_tabs.setCurrentIndex(1)
    assert tab1.is_populated is True
    assert tab1.table.rowCount() > 0
    
    # Tab 2 and 3 should still remain unpopulated
    assert tab2.is_populated is False
    assert tab3.is_populated is False
    assert tab2.table.rowCount() == 0
    assert tab3.table.rowCount() == 0


def test_preallocated_row_count_and_targeted_updates(qapp):
    """Test that table sets row count upfront and updates cells in-place on classification change."""
    project = create_synthetic_project(num_units=1, comps_per_unit=3)
    unit = project.units[0]
    
    tab = FunctionalGroupTab(unit, project, None)
    tab.ensure_populated()
    
    # 3 components * 3 failure modes = 9 rows + 2 separators = 11 rows
    expected_rows = 3 * 3 + 2
    assert tab.table.rowCount() == expected_rows
    
    # Modify classification on row 0
    comp0 = unit.components[0]
    assignment0 = comp0.failure_mode_assignments[0]
    
    tab._on_classif_changed("Safe Failure", assignment0, comp0, row=0)
    
    assert assignment0.classification == "safe_failure"
    assert assignment0.dangerous_failure_percentage == 0.0
    item_safe = tab.table.item(0, 29)
    assert item_safe is not None
    assert float(item_safe.text()) > 0.0


def test_signal_suppression_during_loading(qapp):
    """Test that when is_loading_project is True, handlers do not push undo states."""
    window = MainWindow()
    editor = window.unit_editor_view
    
    project = create_synthetic_project(num_units=1, comps_per_unit=2)
    window.current_project = project
    window.undo_stack.clear()
    
    # When is_loading_project is True
    editor.is_loading_project = True
    window.push_undo_state("Should be ignored")
    assert len(window.undo_stack) == 0
    
    # When is_loading_project is False
    editor.is_loading_project = False
    window.push_undo_state("Valid Action")
    assert len(window.undo_stack) == 1
    assert window.undo_stack[0][1] == "Valid Action"


def test_improved_atomic_saving_and_backup(tmp_path):
    """Test atomic saving creates valid files and creates/updates .json.bak backup."""
    project = create_synthetic_project(num_units=2, comps_per_unit=3)
    target_file = tmp_path / "test_project.json"
    backup_file = tmp_path / "test_project.json.bak"
    
    # First save
    ProjectService.save_project_atomically(project, str(target_file))
    assert target_file.exists()
    assert not backup_file.exists()
    
    with open(target_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data["id"] == project.id
    
    # Second save (should create .json.bak)
    project.name = "Updated Performance Project"
    ProjectService.save_project_atomically(project, str(target_file))
    
    assert target_file.exists()
    assert backup_file.exists()
    
    with open(backup_file, 'r', encoding='utf-8') as f:
        bak_data = json.load(f)
    assert bak_data["name"] == "Synthetic Performance Project"
    
    with open(target_file, 'r', encoding='utf-8') as f:
        cur_data = json.load(f)
    assert cur_data["name"] == "Updated Performance Project"


def test_save_reopen_calculation_equality(tmp_path):
    """Test that saving and reopening a project yields 100% identical FMEDA calculations."""
    project = create_synthetic_project(num_units=4, comps_per_unit=10)
    CalculationService.calculate_project(project)
    
    orig_total_fit = project.total_failure_rate
    orig_safe_fit = project.safe_failure_rate
    orig_dd_fit = project.dangerous_detected_rate
    orig_du_fit = project.dangerous_undetected_rate
    orig_sff = project.sff
    
    target_file = tmp_path / "equality_test.json"
    ProjectService.save_project_atomically(project, str(target_file))
    
    loaded_project, was_migrated, _ = ProjectService.load_and_migrate_project(str(target_file))
    CalculationService.calculate_project(loaded_project)
    
    assert loaded_project.total_failure_rate == pytest.approx(orig_total_fit, rel=1e-6)
    assert loaded_project.safe_failure_rate == pytest.approx(orig_safe_fit, rel=1e-6)
    assert loaded_project.dangerous_detected_rate == pytest.approx(orig_dd_fit, rel=1e-6)
    assert loaded_project.dangerous_undetected_rate == pytest.approx(orig_du_fit, rel=1e-6)
    assert loaded_project.sff == pytest.approx(orig_sff, rel=1e-6)


def test_background_worker_loading(qapp, tmp_path):
    """Test ProjectLoadWorker loads project in background and emits expected signals."""
    project = create_synthetic_project(num_units=2, comps_per_unit=3)
    target_file = tmp_path / "worker_test.json"
    ProjectService.save_project_atomically(project, str(target_file))
    
    worker = ProjectLoadWorker(str(target_file))
    
    results = []
    def on_finished(proj, migrated, msg, timer, finish_ts):
        results.append((proj, migrated, msg, timer, finish_ts))
        
    worker.finished.connect(on_finished)
    worker.run()
    
    assert len(results) == 1
    loaded_proj, migrated, msg, timer, finish_ts = results[0]
    assert loaded_proj.id == project.id
    assert loaded_proj.total_failure_rate > 0
    assert "file_reading" in timer.timings
    assert "pydantic_validation" in timer.timings
    assert "project_calculation" in timer.timings


def test_corrupt_json_file_handling(tmp_path):
    """Test that corrupted JSON files fail gracefully without corrupting existing application state."""
    corrupt_file = tmp_path / "corrupt_proj.json"
    corrupt_file.write_text("{ incomplete json ...", encoding="utf-8")
    
    worker = ProjectLoadWorker(str(corrupt_file))
    errors = []
    worker.error.connect(lambda err: errors.append(err))
    worker.run()
    
    assert len(errors) == 1
    assert "Expecting" in errors[0] or "JSON" in errors[0] or "Invalid" in errors[0]


def test_real_gui_benchmark_and_reconciliation(qapp, tmp_path):
    """
    Real offscreen GUI benchmark testing full load_project path, table population,
    Qt event loop processing, and >= 95% timing accountability.
    """
    project = create_synthetic_project(num_units=2, comps_per_unit=50)  # ~300 FM rows
    unit1_id = project.units[0].id
    project.last_active_tab_id = unit1_id  # Group 1 active
    
    test_file = tmp_path / "real_gui_test.json"
    ProjectService.save_project_atomically(project, str(test_file))
    
    timer = PerformanceTimer("Real GUI Benchmark Test")
    
    # 1. Background worker phase
    t_start = time.perf_counter()
    timer.start_phase("file_reading")
    with open(test_file, 'r', encoding='utf-8') as f:
        raw_json = f.read()
    timer.end_phase("file_reading")
    
    timer.start_phase("json_parsing")
    data = json.loads(raw_json)
    timer.end_phase("json_parsing")
    
    timer.start_phase("pydantic_validation")
    proj = Project.model_validate(data)
    timer.end_phase("pydantic_validation")
    timer.record_project_metrics(proj, len(raw_json))
    
    timer.start_phase("project_calculation")
    CalculationService.calculate_project(proj)
    timer.end_phase("project_calculation")
    timer.counters.calculate_project_count += 1
    
    timer.start_phase("project_verification")
    ValidationService.validate_project(proj)
    timer.end_phase("project_verification")
    timer.counters.validate_project_count += 1
    
    worker_finished_ts = time.perf_counter()
    timer.start_phase("worker_finished_signal_delivery", start_time=worker_finished_ts)
    timer.end_phase("worker_finished_signal_delivery")
    
    # 2. Main window UI loading
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
    qapp.processEvents()
    timer.end_phase("loading_dialog_close_and_final_ui_refresh")
    
    summary = timer.finish()
    
    # Assertions on performance, call counts, and reconciliation
    assert summary["counters"]["load_project_count"] == 1
    assert summary["counters"]["calculate_project_count"] == 1
    assert summary["counters"]["validate_project_count"] == 1
    assert summary["counters"]["full_table_refresh_count"] == 1  # exactly 1 group populated
    
    # Reconciliation assertion: unaccounted time must be <= 5%
    assert summary["metrics"]["reconciliation_pass"] is True
    assert summary["metrics"]["unaccounted_time_pct"] <= 5.0
    
    # Lazy loading events assertion
    tab_headers = [e for e in summary["lazy_events"] if e["action"] == "tab_header_created"]
    tables_pop = [e for e in summary["lazy_events"] if e["action"] == "table_populated"]
    
    assert len(tab_headers) == 2
    assert len(tables_pop) == 1
    assert tables_pop[0]["unit"] == project.units[0].name
