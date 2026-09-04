"""
Tests for lightweight delegates:
- FmedaComboBoxDelegate
- FmedaSpinBoxDelegate
- FmedaLineEditDelegate
- Verification that zero permanent cell widgets exist on QTableView
"""

import pytest
from PyQt6.QtWidgets import (
    QApplication, QTableView, QComboBox, QDoubleSpinBox, QLineEdit, QStyleOptionViewItem
)
from PyQt6.QtCore import Qt

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, Deviation, SafetyStandard,
    DeviationType, DeviationSeverity
)
from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel
from fmeda_tool.ui.delegates.fmeda_delegates import (
    FmedaComboBoxDelegate, FmedaSpinBoxDelegate, FmedaLineEditDelegate
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_sample_project() -> Project:
    dev = Deviation(
        id="dev_01",
        name="Loss of Signal",
        description="Signal broken",
        deviation_type=DeviationType.DANGEROUS_DETECTED,
        severity=DeviationSeverity.HIGH,
        failure_mode="Open",
        effect="Loss of control"
    )
    comp = Component(
        id="comp_1",
        position="R1",
        name="Resistor",
        type="Resistor",
        failure_rate=10.0,
        function="Biasing",
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
        name="Analog Unit",
        description="Analog Unit Subsystem",
        components=[comp]
    )
    return Project(
        id="proj_del_test",
        name="Delegate Test Project",
        description="Testing delegates",
        safety_standard=SafetyStandard.IEC_61508,
        deviations=[dev],
        units=[unit]
    )


def test_combo_box_delegate_lifecycle(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)
    model.set_edit_mode(True)
    delegate = FmedaComboBoxDelegate()

    idx = model.index(0, 15)  # Classification column
    opt = QStyleOptionViewItem()

    # 1. Create temporary editor
    editor = delegate.createEditor(None, opt, idx)
    assert isinstance(editor, QComboBox)
    assert editor.count() == 3  # Not Evaluated, Safe Failure, Dangerous Failure

    # 2. Set editor data
    delegate.setEditorData(editor, idx)
    assert editor.currentText() == "Not Evaluated"

    # 3. Simulate user selecting "Safe Failure" and committing
    editor.setCurrentIndex(1)
    delegate.setModelData(editor, model, idx)

    assert model.data(idx, Qt.ItemDataRole.EditRole) == "safe_failure"
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "Safe Failure"


def test_spin_box_delegate_lifecycle(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)
    model.set_edit_mode(True)
    delegate = FmedaSpinBoxDelegate(min_val=0.0, max_val=100.0, step=1.0, decimals=2, suffix="%")

    idx = model.index(0, 16)  # Dangerous % column
    opt = QStyleOptionViewItem()

    # 1. Create editor
    editor = delegate.createEditor(None, opt, idx)
    assert isinstance(editor, QDoubleSpinBox)

    # 2. Set editor data
    delegate.setEditorData(editor, idx)
    assert editor.value() == 100.0

    # 3. Modify value and commit
    editor.setValue(75.5)
    delegate.setModelData(editor, model, idx)

    assert model.data(idx, Qt.ItemDataRole.EditRole) == 75.5
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "75.5%"


def test_line_edit_delegate_lifecycle(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)
    model.set_edit_mode(True)
    delegate = FmedaLineEditDelegate()

    idx = model.index(0, 2)  # Function column
    opt = QStyleOptionViewItem()

    # 1. Create editor
    editor = delegate.createEditor(None, opt, idx)
    assert isinstance(editor, QLineEdit)

    # 2. Set editor data
    delegate.setEditorData(editor, idx)
    assert editor.text() == "Biasing"

    # 3. Modify text and commit
    editor.setText("Input Filtering")
    delegate.setModelData(editor, model, idx)

    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "Input Filtering"


def test_zero_permanent_cell_widgets(qapp):
    project = create_sample_project()
    unit = project.units[0]
    model = FmedaTableModel(unit, project)
    view = QTableView()
    view.setModel(model)

    # Table has cells rendered
    assert model.rowCount() == 1
    assert model.columnCount() == 41

    # In QTableView with delegates, cellWidget is None for all cells!
    # No permanent widgets are ever created or retained
    for r in range(model.rowCount()):
        for c in range(model.columnCount()):
            # QTableView does not populate child widgets for regular cells
            assert view.indexWidget(model.index(r, c)) is None
