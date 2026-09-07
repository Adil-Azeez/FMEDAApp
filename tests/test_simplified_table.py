"""
Tests for simplified 37-column FMEDA table and backward compatibility:
- Column count is 37
- Removed visible columns: Fitted Status, Reliability Source, Source Reference, Environmental Profile
- Existing project files containing these fields open without data loss
- Cell values and calculations match expected positions
"""

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, Deviation, Mitigation,
    DiagnosticMeasure, SafetyStandard, DeviationType, DeviationSeverity
)
from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel, COLUMN_HEADERS


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_backward_compatible_project() -> Project:
    dev = Deviation(
        id="dev_01",
        name="Loss of Output",
        description="No signal produced",
        deviation_type=DeviationType.DANGEROUS_DETECTED,
        severity=DeviationSeverity.HIGH,
        failure_mode="Open",
        effect="System trip"
    )
    comp = Component(
        id="comp_1",
        position="R10",
        name="Resistor 10k",
        type="Resistor",
        failure_rate=15.0,
        function="Feedback Resistor",
        value="10k",
        internal_pn="RES-10K",
        fitted_status="Not Fitted",  # Legacy/BOM field preserved
        failure_modes={"Open": 60.0, "Short": 40.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Open",
                failure_rate_percentage=60.0,
                classification="dangerous_failure",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0,
                deviation_id="dev_01"
            ),
            FailureModeAssignment(
                failure_mode_name="Short",
                failure_rate_percentage=40.0,
                classification="safe_failure",
                dangerous_failure_percentage=0.0,
                detection_percentage=0.0
            )
        ]
    )
    unit = Unit(
        id="unit_1",
        name="Control Loop",
        description="Main control unit",
        components=[comp]
    )
    return Project(
        id="proj_simplified_test",
        name="Simplified Table Test",
        description="Testing 37 columns",
        safety_standard=SafetyStandard.IEC_61508,
        environmental_profile="Profile 2",
        selected_profile="Profile 2",
        reliability_database_source="Exida Database",
        deviations=[dev],
        units=[unit]
    )


def test_column_count_and_headers_structure(qapp):
    project = create_backward_compatible_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)

    assert model.columnCount() == 37
    assert len(COLUMN_HEADERS) == 37

    # Verify removed headers are NOT in COLUMN_HEADERS
    assert "Fitted Status" not in COLUMN_HEADERS
    assert "Reliability Source" not in COLUMN_HEADERS
    assert "Source Reference" not in COLUMN_HEADERS
    assert "Environmental Profile" not in COLUMN_HEADERS

    # Verify existing retained headers are in correct positions
    assert COLUMN_HEADERS[0] == "Component ID / Designator"
    assert COLUMN_HEADERS[1] == "Status"
    assert COLUMN_HEADERS[2] == "Function"
    assert COLUMN_HEADERS[3] == "Value / Description"
    assert COLUMN_HEADERS[4] == "Internal Part Number"
    assert COLUMN_HEADERS[5] == "Component Type"
    assert COLUMN_HEADERS[6] == "Failure Mode"
    assert COLUMN_HEADERS[7] == "Failure-Mode %"
    assert COLUMN_HEADERS[8] == "Base Failure Rate (FIT)"
    assert COLUMN_HEADERS[9] == "Failure Effect / Deviation"
    assert COLUMN_HEADERS[10] == "Diagnostic Function"
    assert COLUMN_HEADERS[11] == "Failure Classification"
    assert COLUMN_HEADERS[12] == "Dangerous %"
    assert COLUMN_HEADERS[13] == "Safe %"
    assert COLUMN_HEADERS[14] == "Diagnostic Measure ID"
    assert COLUMN_HEADERS[15] == "Detection % (DC)"
    assert COLUMN_HEADERS[16] == "DC Test Ref"
    assert COLUMN_HEADERS[17] == "Mitigation"
    assert COLUMN_HEADERS[18] == "Comments / Justification"
    assert COLUMN_HEADERS[19] == "Review Status"
    assert COLUMN_HEADERS[20] == "Proof Test A"
    assert COLUMN_HEADERS[21] == "Proof Test B"
    assert COLUMN_HEADERS[22] == "Proof Test C"
    assert COLUMN_HEADERS[23] == "No Part / No Effect"
    assert COLUMN_HEADERS[24] == "lambda (FIT)"
    assert COLUMN_HEADERS[36] == "MTTFd (y)"


def test_preserved_model_fields_and_data_access(qapp):
    project = create_backward_compatible_project()
    comp = project.units[0].components[0]

    # Ensure fitted_status is not deleted or overwritten
    assert comp.fitted_status == "Not Fitted"
    assert project.selected_profile == "Profile 2"
    assert project.reliability_database_source == "Exida Database"

    model = FmedaTableModel(project.units[0], project)
    # Row 0: R10 Open
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "R10"
    assert model.data(model.index(0, 2), Qt.ItemDataRole.DisplayRole) == "Feedback Resistor"
    assert model.data(model.index(0, 6), Qt.ItemDataRole.DisplayRole) == "Open"
    assert model.data(model.index(0, 7), Qt.ItemDataRole.DisplayRole) == "60.0%"
    assert model.data(model.index(0, 8), Qt.ItemDataRole.DisplayRole) == "15.0000"
    assert model.data(model.index(0, 9), Qt.ItemDataRole.DisplayRole) == "Loss of Output"
    assert model.data(model.index(0, 11), Qt.ItemDataRole.DisplayRole) == "Dangerous Failure"
    assert model.data(model.index(0, 12), Qt.ItemDataRole.DisplayRole) == "100.0%"
    assert model.data(model.index(0, 13), Qt.ItemDataRole.DisplayRole) == "0.0%"
