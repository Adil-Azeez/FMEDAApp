"""
Tests for View Mode vs Edit Mode workflow in FunctionalGroupTab and UnitEditorView:
- Initial Locked View Mode state
- Enable Editing
- Confirm Changes (recalculation, undo state, view mode restore)
- Cancel Changes (lossless rollback, no undo, view mode restore)
- Single-group edit lock
- Tab switching with unconfirmed edits
"""

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, SafetyStandard
)
from fmeda_tool.ui.unit_editor_view import UnitEditorView, FunctionalGroupTab


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_two_unit_project() -> Project:
    comp1 = Component(
        id="c1",
        position="R1",
        name="Resistor",
        type="Resistor",
        failure_rate=10.0,
        function="Initial Function 1",
        failure_modes={"Open": 100.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Open",
                failure_rate_percentage=100.0,
                classification="not_evaluated",
                dangerous_failure_percentage=100.0
            )
        ]
    )
    unit1 = Unit(
        id="u1",
        name="Unit 1",
        description="First Unit",
        components=[comp1]
    )
    comp2 = Component(
        id="c2",
        position="C1",
        name="Capacitor",
        type="Capacitor",
        failure_rate=5.0,
        function="Initial Function 2",
        failure_modes={"Short": 100.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Short",
                failure_rate_percentage=100.0,
                classification="not_evaluated",
                dangerous_failure_percentage=100.0
            )
        ]
    )
    unit2 = Unit(
        id="u2",
        name="Unit 2",
        description="Second Unit",
        components=[comp2]
    )
    return Project(
        id="proj_workflow",
        name="Workflow Test Project",
        description="Testing edit modes",
        safety_standard=SafetyStandard.IEC_61508,
        units=[unit1, unit2]
    )


def test_initial_locked_view_mode(qapp):
    project = create_two_unit_project()
    editor = UnitEditorView()
    editor.load_project(project)

    # Switch to Unit 1 tab
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    assert isinstance(tab, FunctionalGroupTab)

    # Verify View Mode UI state
    assert tab.is_in_edit_mode is False
    assert tab.model.is_edit_mode is False
    assert "View Mode" in tab.mode_badge.text()
    assert not tab.toggle_edit_btn.isHidden()
    assert tab.confirm_edit_btn.isHidden()
    assert tab.cancel_edit_btn.isHidden()

    # Verify cell is non-editable in View Mode
    idx = tab.model.index(0, 2)
    assert not (tab.model.flags(idx) & Qt.ItemFlag.ItemIsEditable)


def test_enable_and_confirm_changes(qapp):
    project = create_two_unit_project()
    editor = UnitEditorView()
    editor.load_project(project)

    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)

    # 1. Enable editing
    success = tab.enable_editing()
    assert success is True
    assert tab.is_in_edit_mode is True
    assert tab.model.is_edit_mode is True
    assert "Edit Mode" in tab.mode_badge.text()
    assert tab.toggle_edit_btn.isHidden()
    assert not tab.confirm_edit_btn.isHidden()
    assert not tab.cancel_edit_btn.isHidden()

    # 2. Modify cell data
    idx = tab.model.index(0, 2)
    tab.model.setData(idx, "Confirmed New Function", Qt.ItemDataRole.EditRole)
    assert tab.unit.components[0].function == "Confirmed New Function"

    # 3. Confirm changes
    tab.confirm_changes()
    assert tab.is_in_edit_mode is False
    assert tab.model.is_edit_mode is False
    assert "View Mode" in tab.mode_badge.text()
    assert tab.unit.components[0].function == "Confirmed New Function"
    assert tab.model.data(idx, Qt.ItemDataRole.DisplayRole) == "Confirmed New Function"


def test_enable_and_cancel_changes(qapp):
    project = create_two_unit_project()
    editor = UnitEditorView()
    editor.load_project(project)

    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)

    # 1. Enable editing
    tab.enable_editing()
    assert tab.is_in_edit_mode is True

    # 2. Modify cell data
    idx = tab.model.index(0, 2)
    tab.model.setData(idx, "Temporary Discarded Function", Qt.ItemDataRole.EditRole)
    assert tab.unit.components[0].function == "Temporary Discarded Function"

    # 3. Cancel changes
    tab.cancel_changes()
    assert tab.is_in_edit_mode is False
    assert tab.model.is_edit_mode is False
    assert "View Mode" in tab.mode_badge.text()

    # 4. Verify rollback to original value
    assert tab.unit.components[0].function == "Initial Function 1"
    assert tab.model.data(idx, Qt.ItemDataRole.DisplayRole) == "Initial Function 1"


def test_single_group_edit_lock(qapp, monkeypatch):
    project = create_two_unit_project()
    editor = UnitEditorView()
    editor.load_project(project)

    tab1 = editor.unit_tabs.widget(1)
    tab2 = editor.unit_tabs.widget(2)

    # Enable editing on Unit 1
    tab1.enable_editing()
    assert tab1.is_in_edit_mode is True

    # Attempt to enable editing on Unit 2 while Unit 1 is still in edit mode
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    success = tab2.enable_editing()
    assert success is False
    assert tab2.is_in_edit_mode is False


def test_tab_switch_with_unconfirmed_edits_confirm(qapp, monkeypatch):
    project = create_two_unit_project()
    editor = UnitEditorView()
    editor.load_project(project)

    # Select Unit 1
    editor.unit_tabs.setCurrentIndex(1)
    tab1 = editor.unit_tabs.widget(1)
    tab1.enable_editing()

    idx = tab1.model.index(0, 2)
    tab1.model.setData(idx, "Auto Confirmed On Switch", Qt.ItemDataRole.EditRole)

    # Mock QMessageBox to simulate user clicking "Confirm and Switch"
    def mock_exec(self):
        buttons = self.buttons()
        # First button is Confirm and Switch
        self._clicked_button = buttons[0]
        return 0

    monkeypatch.setattr(QMessageBox, "exec", mock_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: getattr(self, "_clicked_button", None))

    # Switch to Unit 2 tab
    editor.unit_tabs.setCurrentIndex(2)

    # Tab 1 edits should have been confirmed and returned to View Mode
    assert tab1.is_in_edit_mode is False
    assert tab1.unit.components[0].function == "Auto Confirmed On Switch"
    assert editor.unit_tabs.currentIndex() == 2
