"""
test_fmeda_block_selection_and_context_menu.py: Comprehensive test suite for
Excel-style component-block selection, right-click context menu, bulk assignments,
single-component operations, deletion with BOM release, undo, and View/Edit Mode locks.
"""

import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QMenu
from PyQt6.QtCore import Qt, QPoint, QPointF, QModelIndex
from PyQt6.QtGui import QMouseEvent, QKeyEvent

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, SafetyStandard,
    Deviation, DiagnosticMeasure, Mitigation, BOMComponent,
    DeviationType, DeviationSeverity, MitigationType
)
from fmeda_tool.ui.unit_editor_view import UnitEditorView, FunctionalGroupTab, FmedaTableView
from fmeda_tool.ui.main_window import MainWindow
from fmeda_tool.ui.dialogs.bulk_assignment_dialogs import (
    ComponentDetailsDialog, DuplicateComponentDialog, BulkItemPickerDialog,
    BulkActionSummaryDialog, DeleteComponentsConfirmDialog
)
from fmeda_tool.services.calculation_service import CalculationService


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_test_project_with_components() -> Project:
    comp1 = Component(
        id="c_c201",
        position="C201",
        name="Capacitor C201",
        type="Capacitor",
        failure_rate=10.0,
        function="Filtering",
        value="10uF",
        internal_pn="CAP-10U",
        source_type="exida",
        failure_modes={"Short Circuit": 60.0, "Open Circuit": 40.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Short Circuit",
                failure_rate_percentage=60.0,
                classification="dangerous_failure",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            ),
            FailureModeAssignment(
                failure_mode_name="Open Circuit",
                failure_rate_percentage=40.0,
                classification="not_evaluated",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            )
        ]
    )

    comp2 = Component(
        id="c_r201",
        position="R201",
        name="Resistor R201",
        type="Resistor",
        failure_rate=5.0,
        function="Current Limit",
        value="1k",
        internal_pn="RES-1K",
        source_type="exida",
        failure_modes={"Open": 70.0, "Short": 30.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Open",
                failure_rate_percentage=70.0,
                classification="not_evaluated",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            ),
            FailureModeAssignment(
                failure_mode_name="Short",
                failure_rate_percentage=30.0,
                classification="not_evaluated",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            )
        ]
    )

    comp3 = Component(
        id="c_u201",
        position="U201",
        name="Microcontroller U201",
        type="IC",
        failure_rate=20.0,
        function="Main Controller",
        value="MCU-32",
        internal_pn="MCU-01",
        source_type="Legacy",
        failure_modes={"Loss of Output": 50.0, "Erratic Output": 50.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Loss of Output",
                failure_rate_percentage=50.0,
                classification="not_evaluated",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            ),
            FailureModeAssignment(
                failure_mode_name="Erratic Output",
                failure_rate_percentage=50.0,
                classification="not_evaluated",
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            )
        ]
    )

    bom1 = BOMComponent(id="bom_c201", designator="C201", part_number="CAP-10U", value="10uF")
    bom2 = BOMComponent(id="bom_r201", designator="R201", part_number="RES-1K", value="1k")
    bom3 = BOMComponent(id="bom_u201", designator="U201", part_number="MCU-01", value="MCU-32")

    unit1 = Unit(
        id="u_power",
        name="Power Management",
        description="Functional group for power",
        components=[comp1, comp2, comp3],
        bom_components=[bom1, bom2, bom3]
    )

    dev1 = Deviation(
        id="dev_001",
        name="Overvoltage Deviation",
        description="Supply voltage exceeds 5.5V",
        deviation_type=DeviationType.DANGEROUS_DETECTED,
        severity=DeviationSeverity.MEDIUM,
        failure_mode="Overvoltage Deviation",
        effect="Supply voltage exceeds 5.5V"
    )
    dm1 = DiagnosticMeasure(id="dm_001", description="Watchdog Timer", dc=90.0)
    mit1 = Mitigation(
        id="mit_001",
        name="Secondary Clamp Diode",
        description="Clamps overvoltage",
        mitigation_type=MitigationType.PROTECTIVE_CIRCUIT
    )

    return Project(
        id="proj_block_test",
        name="Block Selection Test Project",
        description="Testing block selection and context menu",
        safety_standard=SafetyStandard.IEC_61508,
        units=[unit1],
        deviations=[dev1],
        diagnostic_measures=[dm1],
        mitigations=[mit1]
    )


# ==============================================================================
# 1. LOCKED VIEW MODE TESTS
# ==============================================================================

def test_locked_view_mode_right_click_and_shortcuts_disabled(qapp):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    assert isinstance(tab, FunctionalGroupTab)

    # Initial state is Locked View Mode
    assert not tab.is_in_edit_mode
    assert not tab.table.is_in_edit_mode()

    # 1. Right click does not select and does not open context menu
    rect = tab.table.visualRect(tab.model.index(0, 0))
    center = rect.center()
    ev_right = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(center.x(), center.y()),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    tab.table.mousePressEvent(ev_right)
    assert len(tab.table.selected_component_ids) == 0

    # 2. Ctrl+click and Shift+click do not create component block multi-selections
    ev_ctrl = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(center.x(), center.y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier
    )
    tab.table.mousePressEvent(ev_ctrl)
    assert len(tab.table.selected_component_ids) == 0

    # 3. Ctrl+A does not select component blocks
    key_ctrl_a = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    tab.table.keyPressEvent(key_ctrl_a)
    assert len(tab.table.selected_component_ids) == 0

    # 4. Delete & Backspace do nothing
    initial_comp_count = len(tab.unit.components)
    key_del = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    tab.table.keyPressEvent(key_del)
    assert len(tab.unit.components) == initial_comp_count


def test_locked_view_mode_direct_handlers_prevent_mutation(qapp):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)

    assert not tab.is_in_edit_mode

    # Direct calls to modifying handlers must return False immediately
    assert tab.edit_component("c_c201") is False
    assert tab.duplicate_component("c_c201") is False
    assert tab.delete_selected_components() is False
    assert tab.bulk_assign_deviation("dev_001") is False
    assert tab.bulk_assign_diagnostic_measure("dm_001") is False
    assert tab.bulk_assign_mitigation("mit_001") is False
    assert tab.bulk_set_classification("safe_failure") is False

    # Component count and properties remain unaltered
    assert len(tab.unit.components) == 3
    assert tab.unit.components[0].failure_mode_assignments[0].deviation_id is None


# ==============================================================================
# 2. COMPONENT-BLOCK SELECTION IN EDIT MODE
# ==============================================================================

def test_single_component_block_selection_in_edit_mode(qapp):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)

    tab.enable_editing()
    assert tab.is_in_edit_mode is True

    # C201 occupies row 0 and row 1. Click on row 1 (Open Circuit)
    rect1 = tab.table.visualRect(tab.model.index(1, 0))
    ev_click = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(rect1.center().x(), rect1.center().y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    tab.table.mousePressEvent(ev_click)

    # Whole component block is selected
    assert tab.table.selected_component_ids == {"c_c201"}
    assert tab.table.anchor_component_id == "c_c201"

    # Both row 0 and row 1 must be visually selected in QItemSelectionModel
    sm = tab.table.selectionModel()
    assert sm.isRowSelected(0, QModelIndex())
    assert sm.isRowSelected(1, QModelIndex())
    # Separator at row 2 is NOT selected
    assert not sm.isRowSelected(2, QModelIndex())


def test_ctrl_click_multi_selection(qapp):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    tab.enable_editing()

    # 1. Plain click on C201 (row 0)
    rect0 = tab.table.visualRect(tab.model.index(0, 0))
    tab.table.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(rect0.center().x(), rect0.center().y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    ))
    assert tab.table.selected_component_ids == {"c_c201"}

    # 2. Ctrl+click on R201 (row 3) -> both selected
    rect3 = tab.table.visualRect(tab.model.index(3, 0))
    tab.table.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(rect3.center().x(), rect3.center().y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier
    ))
    assert tab.table.selected_component_ids == {"c_c201", "c_r201"}

    # 3. Ctrl+click on C201 again -> deselects C201
    tab.table.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(rect0.center().x(), rect0.center().y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier
    ))
    assert tab.table.selected_component_ids == {"c_r201"}


def test_shift_click_range_selection(qapp):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    tab.enable_editing()

    # 1. Click on C201 (row 0)
    rect0 = tab.table.visualRect(tab.model.index(0, 0))
    tab.table.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(rect0.center().x(), rect0.center().y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    ))
    assert tab.table.selected_component_ids == {"c_c201"}

    # 2. Shift+click on U201 (row 6) -> selects range C201, R201, U201
    rect6 = tab.table.visualRect(tab.model.index(6, 0))
    tab.table.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(rect6.center().x(), rect6.center().y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier
    ))
    assert tab.table.selected_component_ids == {"c_c201", "c_r201", "c_u201"}


def test_ctrl_a_selects_all_visible_components(qapp):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    tab.enable_editing()

    key_ctrl_a = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    tab.table.keyPressEvent(key_ctrl_a)

    assert tab.table.selected_component_ids == {"c_c201", "c_r201", "c_u201"}

    # Test Escape clears selection
    key_esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    tab.table.keyPressEvent(key_esc)
    assert len(tab.table.selected_component_ids) == 0


def test_separator_rows_ignored_in_selection(qapp):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    tab.enable_editing()

    # Row 2 is separator
    assert tab.model.rows[2].is_separator is True
    rect2 = tab.table.visualRect(tab.model.index(2, 0))
    tab.table.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(rect2.center().x(), rect2.center().y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    ))
    assert len(tab.table.selected_component_ids) == 0


# ==============================================================================
# 3. RIGHT-CLICK CONTEXT MENU BEHAVIOR
# ==============================================================================

def test_right_click_unselected_component_selects_it(qapp, monkeypatch):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    tab.enable_editing()

    monkeypatch.setattr(QMenu, "exec", lambda self, *args: None)

    # Pre-select C201
    tab.table.selected_component_ids = {"c_c201"}
    tab.table.update_visual_selection()

    # Right click on R201 (row 3)
    rect3 = tab.table.visualRect(tab.model.index(3, 0))
    ev_right = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(rect3.center().x(), rect3.center().y()),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    # Right-click should deselect C201 and select R201
    tab.table.mousePressEvent(ev_right)
    assert tab.table.selected_component_ids == {"c_r201"}


def test_right_click_on_multi_selection_preserves_selection(qapp, monkeypatch):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    tab.enable_editing()

    monkeypatch.setattr(QMenu, "exec", lambda self, *args: None)

    # Pre-select C201 and R201
    tab.table.selected_component_ids = {"c_c201", "c_r201"}
    tab.table.update_visual_selection()

    # Right click on C201 (row 0), which is already part of multi-selection
    rect0 = tab.table.visualRect(tab.model.index(0, 0))
    ev_right = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(rect0.center().x(), rect0.center().y()),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    tab.table.mousePressEvent(ev_right)
    assert tab.table.selected_component_ids == {"c_c201", "c_r201"}


# ==============================================================================
# 4. BULK ASSIGNMENTS & SUMMARY CONFIRMATION
# ==============================================================================

def test_bulk_assign_deviation_with_summary_and_atomic_apply(qapp, monkeypatch):
    project = create_test_project_with_components()
    window = MainWindow()
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.widget(1)
    tab.enable_editing()

    # Select C201 and R201
    tab.table.selected_component_ids = {"c_c201", "c_r201"}
    tab.table.update_visual_selection()

    # Auto-accept summary dialog
    monkeypatch.setattr(BulkActionSummaryDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    success = tab.bulk_assign_deviation(selected_dev_id="dev_001")
    assert success is True

    # Check that all failure modes in C201 and R201 got dev_001
    c201 = next(c for c in tab.unit.components if c.id == "c_c201")
    r201 = next(c for c in tab.unit.components if c.id == "c_r201")
    u201 = next(c for c in tab.unit.components if c.id == "c_u201")

    for a in c201.failure_mode_assignments:
        assert a.deviation_id == "dev_001"
    for a in r201.failure_mode_assignments:
        assert a.deviation_id == "dev_001"
    for a in u201.failure_mode_assignments:
        assert a.deviation_id is None  # Unselected component untouched

    # Verify undo state was pushed
    assert len(window.undo_stack) >= 1


def test_bulk_assign_diagnostic_measure_with_summary(qapp, monkeypatch):
    project = create_test_project_with_components()
    window = MainWindow()
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.widget(1)
    tab.enable_editing()

    tab.table.selected_component_ids = {"c_c201", "c_u201"}
    monkeypatch.setattr(BulkActionSummaryDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    success = tab.bulk_assign_diagnostic_measure(selected_dm_id="dm_001")
    assert success is True

    c201 = next(c for c in tab.unit.components if c.id == "c_c201")
    u201 = next(c for c in tab.unit.components if c.id == "c_u201")

    for a in c201.failure_mode_assignments:
        assert a.diagnostic_measure_id == "dm_001"
        assert a.detection_percentage == 90.0
    for a in u201.failure_mode_assignments:
        assert a.diagnostic_measure_id == "dm_001"
        assert a.detection_percentage == 90.0


def test_bulk_assign_mitigation_with_summary(qapp, monkeypatch):
    project = create_test_project_with_components()
    window = MainWindow()
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.widget(1)
    tab.enable_editing()

    tab.table.selected_component_ids = {"c_r201"}
    monkeypatch.setattr(BulkActionSummaryDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    success = tab.bulk_assign_mitigation(selected_mit_id="mit_001")
    assert success is True

    r201 = next(c for c in tab.unit.components if c.id == "c_r201")
    for a in r201.failure_mode_assignments:
        assert a.mitigation_id == "mit_001"


def test_bulk_set_classification_with_summary(qapp, monkeypatch):
    project = create_test_project_with_components()
    window = MainWindow()
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.widget(1)
    tab.enable_editing()

    tab.table.selected_component_ids = {"c_c201", "c_r201"}
    monkeypatch.setattr(BulkActionSummaryDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    success = tab.bulk_set_classification(selected_classif="safe_failure")
    assert success is True

    c201 = next(c for c in tab.unit.components if c.id == "c_c201")
    for a in c201.failure_mode_assignments:
        assert a.classification == "safe_failure"
        assert a.dangerous_failure_percentage == 0.0


# ==============================================================================
# 5. SINGLE-COMPONENT ACTIONS (DUPLICATE, DETAILS, EDIT)
# ==============================================================================

def test_duplicate_component_creates_new_id_and_unique_position(qapp, monkeypatch):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    tab.enable_editing()

    tab.table.selected_component_ids = {"c_c201"}

    # Mock DuplicateComponentDialog to return "C201_COPY"
    monkeypatch.setattr(DuplicateComponentDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(DuplicateComponentDialog, "get_new_position", lambda self: "C201_COPY")

    success = tab.duplicate_component("c_c201")
    assert success is True

    assert len(tab.unit.components) == 4
    dup = next((c for c in tab.unit.components if c.position == "C201_COPY"), None)
    assert dup is not None
    assert dup.id != "c_c201"
    assert dup.name == "Capacitor C201"
    assert dup.failure_rate == 10.0
    assert len(dup.failure_modes) == 2
    assert len(dup.failure_mode_assignments) == 2


def test_view_component_details_is_read_only(qapp, monkeypatch):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)

    monkeypatch.setattr(ComponentDetailsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    success = tab.view_component_details("c_c201")
    assert success is True
    # Components data unmodified
    assert len(tab.unit.components) == 3


# ==============================================================================
# 6. COMPONENT DELETION & BOM RELEASE
# ==============================================================================

def test_single_and_multi_component_deletion_and_bom_release(qapp, monkeypatch):
    project = create_test_project_with_components()
    window = MainWindow()
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.widget(1)
    tab.enable_editing()

    tab.table.selected_component_ids = {"c_c201", "c_r201"}
    monkeypatch.setattr(DeleteComponentsConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    success = tab.delete_selected_components()
    assert success is True

    # 2 components deleted, 1 remaining (U201)
    assert len(tab.unit.components) == 1
    assert tab.unit.components[0].id == "c_u201"

    # BOM components still exist in BOM list, but C201 and R201 are now unmapped
    assert len(tab.unit.bom_components) == 3
    mapped_positions = [c.position for c in tab.unit.components]
    assert "C201" not in mapped_positions
    assert "R201" not in mapped_positions
    assert "U201" in mapped_positions


def test_undo_deletion_restores_components_and_bom_mapping(qapp, monkeypatch):
    project = create_test_project_with_components()
    window = MainWindow()
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.widget(1)
    tab.enable_editing()

    tab.table.selected_component_ids = {"c_c201"}
    monkeypatch.setattr(DeleteComponentsConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    tab.delete_selected_components()
    assert len(tab.unit.components) == 2

    # Perform Undo via window
    assert len(window.undo_stack) >= 1
    window._on_undo()

    # Restored to 3 components
    current_tab = window.unit_editor_view.unit_tabs.widget(1)
    assert len(current_tab.unit.components) == 3
    positions = [c.position for c in current_tab.unit.components]
    assert "C201" in positions


# ==============================================================================
# 7. SESSION RESTORE & CANCEL CHANGES
# ==============================================================================

def test_cancel_changes_restores_session_losslessly(qapp, monkeypatch):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)

    # 1. Enable editing
    tab.enable_editing()

    # 2. Mutate: Duplicate a component and delete another
    tab.table.selected_component_ids = {"c_c201"}
    monkeypatch.setattr(DuplicateComponentDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(DuplicateComponentDialog, "get_new_position", lambda self: "C201_TEMP")
    tab.duplicate_component("c_c201")
    assert len(tab.unit.components) == 4

    tab.table.selected_component_ids = {"c_u201"}
    monkeypatch.setattr(DeleteComponentsConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    tab.delete_selected_components()
    assert len(tab.unit.components) == 3

    # 3. Cancel Changes
    tab.cancel_changes()

    # Restored to exact 3 original components in original state
    assert not tab.is_in_edit_mode
    assert len(tab.unit.components) == 3
    comp_ids = [c.id for c in tab.unit.components]
    assert comp_ids == ["c_c201", "c_r201", "c_u201"]
    assert len(tab.table.selected_component_ids) == 0


def test_confirm_changes_and_cancel_changes_clear_selection(qapp):
    project = create_test_project_with_components()
    editor = UnitEditorView()
    editor.load_project(project)
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)

    tab.enable_editing()
    tab.table.selected_component_ids = {"c_c201", "c_r201"}
    tab.table.update_visual_selection()

    tab.confirm_changes()
    assert not tab.is_in_edit_mode
    assert len(tab.table.selected_component_ids) == 0
