"""
Unit tests for:
1. Page 3 Verification alerts handling:
   - Alert with valid location (dict, tuple/list, string, top-level unit_id/row_index)
   - Alert with null location
   - Alert without a location key
   - Project-level alert
   - Malformed alert among valid alerts (zero crashes, remaining alerts display)
   - Zero alerts handling
   - Project with no functional groups
   - Row-alert navigation and lazy-loaded target tab navigation
   - Separator-row vs model-row mapping
2. Workflow Page Titles & Header centering:
   - Pages 1, 2, 3, 4 title centering and alignment
   - Centering preserved upon window resize
   - Compatibility with Page 2 buttons (Undo, Add FG, Edit FG, Remove FG)
"""

import pytest
from PyQt6.QtWidgets import (
    QApplication, QWidget, QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QResizeEvent

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, Deviation, Mitigation,
    DiagnosticMeasure, SafetyStandard, DeviationType, DeviationSeverity, MitigationType
)
from fmeda_tool.ui.verification_view import VerificationView, normalize_alert, NormalizedAlert
from fmeda_tool.ui.create_project_view import CreateProjectView
from fmeda_tool.ui.unit_editor_view import UnitEditorView, FunctionalGroupTab
from fmeda_tool.ui.export_view import ExportView
from fmeda_tool.ui.widgets import WorkflowPageHeader
from fmeda_tool.services.validation_service import ValidationService


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_mock_project() -> Project:
    dev = Deviation(
        id="dev_v1",
        name="Overvoltage Deviation",
        description="Voltage above 3.3V",
        deviation_type=DeviationType.DANGEROUS_DETECTED,
        severity=DeviationSeverity.HIGH,
        failure_mode="Overvoltage",
        effect="Output rail saturated"
    )
    mit = Mitigation(
        id="mit_v1",
        name="Zener Clamp",
        description="Zener diode clamp",
        mitigation_type=MitigationType.DIAGNOSTIC,
        effectiveness=0.95
    )
    dm = DiagnosticMeasure(
        id="dm_v1",
        description="Voltage Comparator Check",
        dc=90.0
    )
    comp1 = Component(
        id="comp_v1",
        position="U1",
        name="Microcontroller ADC",
        type="Integrated Circuit",
        failure_rate=25.0,
        function="ADC Input",
        failure_modes={"Overvoltage": 60.0, "Undervoltage": 40.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Overvoltage",
                failure_rate_percentage=60.0,
                classification="dangerous_failure",
                dangerous_failure_percentage=100.0,
                detection_percentage=90.0,
                deviation_id="dev_v1",
                diagnostic_measure_id="dm_v1",
                mitigation_id="mit_v1"
            ),
            FailureModeAssignment(
                failure_mode_name="Undervoltage",
                failure_rate_percentage=40.0,
                classification="safe_failure",
                dangerous_failure_percentage=0.0,
                detection_percentage=0.0
            )
        ]
    )
    comp2 = Component(
        id="comp_v2",
        position="R1",
        name="Shunt Resistor",
        type="Resistor",
        failure_rate=5.0,
        function="Current sense",
        failure_modes={"Open": 100.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Open",
                failure_rate_percentage=100.0,
                classification="dangerous_failure",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            )
        ]
    )
    unit1 = Unit(
        id="unit_v1",
        name="Sensor Unit",
        description="Sensor Subsystem",
        components=[comp1, comp2]
    )
    unit2 = Unit(
        id="unit_v2",
        name="Actuator Unit",
        description="Actuator Subsystem",
        components=[]
    )
    return Project(
        id="proj_verif_test",
        name="Verification Test Project",
        description="Testing verification alerts and navigation",
        safety_standard=SafetyStandard.IEC_61508,
        deviations=[dev],
        mitigations=[mit],
        diagnostic_measures=[dm],
        units=[unit1, unit2]
    )


# ==============================================================================
# 1. ALERT NORMALIZATION TESTS
# ==============================================================================

def test_normalize_alert_with_top_level_fields(qapp):
    project = create_mock_project()
    raw = {
        "severity": "Error",
        "message": "Missing deviation assignment",
        "scope": "Component",
        "item": "R1 (Open)",
        "unit_id": "unit_v1",
        "row_index": 2
    }
    norm = normalize_alert(raw, project)
    assert norm.severity == "Error"
    assert norm.message == "Missing deviation assignment"
    assert norm.unit_id == "unit_v1"
    assert norm.row_index == 2
    assert norm.location_str == "Sensor Unit (Row 3)"
    assert norm.can_navigate is True


def test_normalize_alert_with_dict_location(qapp):
    project = create_mock_project()
    raw = {
        "severity": "Warning",
        "message": "Dangerous percentage not set",
        "location": {"unit_id": "unit_v1", "row_index": 0}
    }
    norm = normalize_alert(raw, project)
    assert norm.severity == "Warning"
    assert norm.unit_id == "unit_v1"
    assert norm.row_index == 0
    assert norm.location_str == "Sensor Unit (Row 1)"
    assert norm.can_navigate is True


def test_normalize_alert_with_tuple_location(qapp):
    project = create_mock_project()
    raw = {
        "severity": "Info",
        "message": "Review status is draft",
        "location": ("unit_v1", 1)
    }
    norm = normalize_alert(raw, project)
    assert norm.severity == "Info"
    assert norm.unit_id == "unit_v1"
    assert norm.row_index == 1
    assert norm.location_str == "Sensor Unit (Row 2)"
    assert norm.can_navigate is True


def test_normalize_alert_with_null_and_missing_location(qapp):
    project = create_mock_project()

    # Null location
    raw_null = {
        "severity": "Error",
        "message": "No reviewer assigned",
        "location": None
    }
    norm_null = normalize_alert(raw_null, project)
    assert norm_null.severity == "Error"
    assert norm_null.unit_id is None
    assert norm_null.row_index is None
    assert norm_null.location_str == "Project-Level"
    assert norm_null.can_navigate is False

    # Missing location key
    raw_missing = {
        "severity": "Warning",
        "message": "Project description is empty"
    }
    norm_missing = normalize_alert(raw_missing, project)
    assert norm_missing.severity == "Warning"
    assert norm_missing.unit_id is None
    assert norm_missing.location_str == "Project-Level"
    assert norm_missing.can_navigate is False


def test_normalize_alert_project_level(qapp):
    project = create_mock_project()
    raw = {
        "severity": "Error",
        "scope": "Global",
        "item": "Target SIL Mismatch",
        "message": "Target SIL is SIL 2 but Achieved SIL is SIL 0.",
        "unit_id": None,
        "row_index": None
    }
    norm = normalize_alert(raw, project)
    assert norm.severity == "Error"
    assert norm.location_str == "Project-Level"
    assert norm.can_navigate is False


def test_normalize_alert_malformed_inputs(qapp):
    project = create_mock_project()

    # Non-dictionary input (string)
    norm_str = normalize_alert("Corrupt error message string", project)
    assert norm_str.severity == "Info"
    assert norm_str.message == "Corrupt error message string"
    assert norm_str.location_str == "Project-Level"
    assert norm_str.can_navigate is False

    # None input
    norm_none = normalize_alert(None, project)
    assert norm_none.severity == "Info"
    assert norm_none.location_str == "Project-Level"

    # Dict with invalid types for row_index
    norm_bad_row = normalize_alert({"severity": "Error", "unit_id": "unit_v1", "row_index": "invalid_row"}, project)
    assert norm_bad_row.severity == "Error"
    assert norm_bad_row.row_index is None
    assert norm_bad_row.location_str == "Sensor Unit (Group Level)"
    assert norm_bad_row.can_navigate is False


# ==============================================================================
# 2. PAGE 3 VERIFICATION VIEW WORKFLOW TESTS
# ==============================================================================

def test_verification_view_with_mixed_and_malformed_alerts(qapp, monkeypatch):
    project = create_mock_project()
    view = VerificationView()
    view.load_project(project)

    # Mock ValidationService to return mixed alerts including malformed ones
    def mock_validate(proj):
        return [
            {"severity": "Error", "message": "Project Number missing", "location": None},
            {"severity": "Warning", "message": "Component warning", "unit_id": "unit_v1", "row_index": 0},
            {"severity": "Info", "message": "Group empty", "unit_id": "unit_v2"},
            "Raw unformatted alert string",
            {"completely_invalid": True},
            {"severity": "Error", "message": "Legacy tuple loc", "location": ("unit_v1", 2)}
        ]

    monkeypatch.setattr(ValidationService, "validate_project", mock_validate)
    
    # Refresh validation - MUST NOT CRASH
    view.refresh_validation()

    # Verify that all 6 alerts are rendered in the tree
    total_child_items = 0
    for i in range(view.validation_tree.topLevelItemCount()):
        top_item = view.validation_tree.topLevelItem(i)
        total_child_items += top_item.childCount()

    assert total_child_items == 6


def test_verification_view_zero_alerts(qapp, monkeypatch):
    project = create_mock_project()
    view = VerificationView()
    view.load_project(project)

    monkeypatch.setattr(ValidationService, "validate_project", lambda p: [])
    view.refresh_validation()

    assert view.validation_tree.topLevelItemCount() == 0
    # Secondary table and metrics cards must still render cleanly
    assert view.secondary_table.rowCount() > 0


def test_verification_view_no_functional_groups(qapp):
    project = Project(
        id="proj_empty",
        name="Empty Project",
        description="Project without functional groups",
        safety_standard=SafetyStandard.IEC_61508,
        units=[]
    )
    view = VerificationView()
    view.load_project(project)

    # Must not crash
    view.refresh_validation()
    assert view.secondary_table.rowCount() == 14  # Summary rows rendered with zero values
    assert view.validation_tree.topLevelItemCount() > 0  # Global alert: "No functional groups exist"


def test_row_alert_navigation_and_lazy_load(qapp):
    project = create_mock_project()
    editor = UnitEditorView()
    editor.load_project(project)

    # Actuator Unit is at tab index 2; verify Sensor Unit (tab 1) is populated on focus_unit_row
    assert editor.unit_tabs.count() == 3  # Tab 0: Overview, Tab 1: Sensor Unit, Tab 2: Actuator Unit
    
    # Focus row 2 in Sensor Unit (R1 Open)
    editor.focus_unit_row("unit_v1", 2)

    assert editor.unit_tabs.currentIndex() == 1
    tab = editor.unit_tabs.widget(1)
    assert isinstance(tab, FunctionalGroupTab)
    assert tab.is_populated is True
    
    # Check that model selected row accounts for separator row
    # Sensor Unit components:
    # comp1 (2 failure modes): rows 0, 1
    # separator: row 2
    # comp2 (1 failure mode): row 3
    # Therefore row_index 2 (comp2 failure mode 0) maps to model row 3!
    assert tab.table.currentIndex().row() == 3


# ==============================================================================
# 3. WORKFLOW PAGE HEADERS & CENTERING TESTS
# ==============================================================================

def test_workflow_page_headers_title_and_alignment(qapp):
    p1 = CreateProjectView()
    p2 = UnitEditorView()
    p3 = VerificationView()
    p4 = ExportView()

    assert isinstance(p1.header_frame, WorkflowPageHeader)
    assert isinstance(p2.header_frame, WorkflowPageHeader)
    assert isinstance(p3.header_frame, WorkflowPageHeader)
    assert isinstance(p4.header_frame, WorkflowPageHeader)

    assert p1.header_frame.title_label.text() == "Page 1: Project Information"
    assert p2.header_frame.title_label.text() == "Page 2: FMEDA Analysis"
    assert p3.header_frame.title_label.text() == "Page 3: Project Verification"
    assert p4.header_frame.title_label.text() == "Page 4: Export Results"

    # All titles have center alignment
    for p in [p1, p2, p3, p4]:
        assert p.header_frame.title_label.alignment() & Qt.AlignmentFlag.AlignCenter


def test_page2_header_action_buttons_and_metadata(qapp):
    project = create_mock_project()
    editor = UnitEditorView()
    editor.load_project(project)

    header = editor.header_frame
    assert isinstance(header, WorkflowPageHeader)

    # Left container holds project name and status
    assert editor.project_name_label.text() == "Verification Test Project"
    assert "Status" in editor.project_status_label.text()

    # Right container holds Undo and group management buttons
    assert editor.undo_btn.parent() == header.right_container
    assert editor.add_fg_btn.parent() == header.right_container
    assert editor.edit_fg_btn.parent() == header.right_container
    assert editor.remove_fg_btn.parent() == header.right_container


def test_workflow_header_centering_on_resize(qapp):
    header = WorkflowPageHeader("Page 2: FMEDA Analysis")
    header.resize(1200, 65)

    # Send resize event
    event = QResizeEvent(QSize(1600, 65), QSize(1200, 65))
    header.resizeEvent(event)
    header.resize(1600, 65)

    # Title label alignment remains centered
    assert header.title_label.alignment() & Qt.AlignmentFlag.AlignCenter
    assert header.grid_layout.columnStretch(0) == header.grid_layout.columnStretch(2)
