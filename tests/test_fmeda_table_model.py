"""
Tests for FmedaTableModel:
- Row/Column counting
- DisplayRole, EditRole, CheckStateRole, BackgroundRole, ToolTipRole
- Flags in View Mode vs Edit Mode
- setData on text, numbers, dropdowns, classifications, and checkboxes
- Metric recalculations and linked component updates
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


def create_sample_project() -> Project:
    dev = Deviation(
        id="dev_01",
        name="Output High Deviation",
        description="Pin held high",
        deviation_type=DeviationType.DANGEROUS_DETECTED,
        severity=DeviationSeverity.MEDIUM,
        failure_mode="Stuck High",
        effect="Saturated output"
    )
    mit = Mitigation(
        id="mit_01",
        name="Clamping Diode",
        description="Clamps high voltage",
        effectiveness=0.95
    )
    dm = DiagnosticMeasure(
        id="dm_01",
        description="Cyclic Loopback Test",
        dc=90.0
    )
    comp1 = Component(
        id="comp_1",
        position="U1",
        name="OpAmp",
        type="Integrated Circuit",
        failure_rate=20.0,
        function="Amplification",
        value="LMV358",
        internal_pn="PN-1001",
        fitted_status="Fitted",
        failure_modes={"Stuck High": 50.0, "Stuck Low": 50.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Stuck High",
                failure_rate_percentage=50.0,
                classification="dangerous_failure",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0,
                deviation_id="dev_01",
                diagnostic_measure_id="dm_01",
                mitigation_id="mit_01"
            ),
            FailureModeAssignment(
                failure_mode_name="Stuck Low",
                failure_rate_percentage=50.0,
                classification="safe_failure",
                dangerous_failure_percentage=0.0,
                detection_percentage=0.0
            )
        ]
    )
    comp2 = Component(
        id="comp_2",
        position="R1",
        name="Resistor 10k",
        type="Resistor",
        failure_rate=5.0,
        function="Pull-up",
        value="10k",
        internal_pn="PN-2002",
        failure_modes={"Open": 100.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Open",
                failure_rate_percentage=100.0,
                classification="not_evaluated",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            )
        ]
    )
    unit = Unit(
        id="unit_1",
        name="Analog Front End",
        description="AFE Subsystem",
        components=[comp1, comp2]
    )
    return Project(
        id="proj_1",
        name="Test FMEDA Project",
        description="Project for table model testing",
        safety_standard=SafetyStandard.IEC_61508,
        deviations=[dev],
        mitigations=[mit],
        diagnostic_measures=[dm],
        units=[unit]
    )


def test_model_structure_and_headers(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)

    assert model.columnCount() == 41
    # comp1 has 2 failure modes, comp2 has 1 failure mode, plus 1 separator between them = 4 rows
    assert model.rowCount() == 4

    assert model.headerData(0, Qt.Orientation.Horizontal) == "Component ID / Designator"
    assert model.headerData(15, Qt.Orientation.Horizontal) == "Failure Classification"
    assert model.headerData(27, Qt.Orientation.Horizontal) == "No Part / No Effect"
    assert model.headerData(40, Qt.Orientation.Horizontal) == "MTTFd (y)"


def test_model_flags_in_view_vs_edit_mode(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)

    # In Locked View Mode (default):
    idx_func = model.index(0, 2)  # Function (normally editable)
    idx_class = model.index(0, 15)  # Classification (normally editable)
    idx_chk = model.index(0, 27)  # Checkbox

    assert not (model.flags(idx_func) & Qt.ItemFlag.ItemIsEditable)
    assert not (model.flags(idx_class) & Qt.ItemFlag.ItemIsEditable)
    assert not (model.flags(idx_chk) & Qt.ItemFlag.ItemIsUserCheckable)

    # In Edit Mode:
    model.set_edit_mode(True)
    assert bool(model.flags(idx_func) & Qt.ItemFlag.ItemIsEditable)
    assert bool(model.flags(idx_class) & Qt.ItemFlag.ItemIsEditable)
    assert bool(model.flags(idx_chk) & Qt.ItemFlag.ItemIsUserCheckable)

    # Separator row (row 2) remains unselectable / uneditable
    idx_sep = model.index(2, 0)
    assert model.flags(idx_sep) == Qt.ItemFlag.NoItemFlags


def test_model_data_display_and_edit_roles(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)

    # Row 0: U1 Stuck High
    idx_des = model.index(0, 0)
    assert model.data(idx_des, Qt.ItemDataRole.DisplayRole) == "U1"

    idx_func = model.index(0, 2)
    assert model.data(idx_func, Qt.ItemDataRole.DisplayRole) == "Amplification"

    idx_fm = model.index(0, 7)
    assert model.data(idx_fm, Qt.ItemDataRole.DisplayRole) == "Stuck High"

    idx_fm_pct = model.index(0, 8)
    assert model.data(idx_fm_pct, Qt.ItemDataRole.DisplayRole) == "50.0%"
    assert model.data(idx_fm_pct, Qt.ItemDataRole.EditRole) == 50.0

    idx_dev = model.index(0, 13)
    assert model.data(idx_dev, Qt.ItemDataRole.DisplayRole) == "Output High Deviation"
    assert model.data(idx_dev, Qt.ItemDataRole.EditRole) == "dev_01"

    idx_class = model.index(0, 15)
    assert model.data(idx_class, Qt.ItemDataRole.DisplayRole) == "Dangerous Failure"
    assert model.data(idx_class, Qt.ItemDataRole.EditRole) == "dangerous_failure"


def test_model_set_data_and_recalculation(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)
    model.set_edit_mode(True)

    # Edit Dangerous % from 100 to 40
    idx_dp = model.index(0, 16)
    success = model.setData(idx_dp, 40.0, Qt.ItemDataRole.EditRole)
    assert success is True

    # Check that Safe % was updated to 60.0%
    idx_safe = model.index(0, 17)
    assert model.data(idx_safe, Qt.ItemDataRole.DisplayRole) == "60.0%"

    # Check that lambda_safe and lambda_dangerous were updated
    # Total local FIT = 20.0 * 50% = 10.0 FIT
    # lambda_safe = 10.0 * 0.6 = 6.0 FIT, lambda_dangerous = 10.0 * 0.4 = 4.0 FIT
    idx_lam_s = model.index(0, 29)
    idx_lam_d = model.index(0, 30)
    assert model.data(idx_lam_s, Qt.ItemDataRole.DisplayRole) == "6.0000"
    assert model.data(idx_lam_d, Qt.ItemDataRole.DisplayRole) == "4.0000"


def test_model_checkbox_dont_care(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)
    model.set_edit_mode(True)

    idx_chk = model.index(0, 27)
    assert model.data(idx_chk, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked

    # Check the box
    model.setData(idx_chk, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert model.data(idx_chk, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert unit.components[0].failure_mode_assignments[0].dont_care is True


def test_linked_component_text_updates(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)
    model.set_edit_mode(True)

    # Edit Function on row 0 (U1 Stuck High)
    idx_func_row0 = model.index(0, 2)
    model.setData(idx_func_row0, "Preamplifier Stage", Qt.ItemDataRole.EditRole)

    # Verify that row 1 (U1 Stuck Low) also reflects "Preamplifier Stage"
    idx_func_row1 = model.index(1, 2)
    assert model.data(idx_func_row1, Qt.ItemDataRole.DisplayRole) == "Preamplifier Stage"
    assert unit.components[0].function == "Preamplifier Stage"
