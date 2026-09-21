import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton
from PyQt6.QtCore import Qt

from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment
from fmeda_tool.services.component_library_service import ComponentLibraryService
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.project_service import ProjectService
from fmeda_tool.ui.dialogs.custom_component_dialog import CustomComponentDialog
from fmeda_tool.ui.dialogs.component_picker_dialog import ComponentPickerDialog
from fmeda_tool.ui.dialogs.component_mapping_dialog import ComponentMappingDialog
from fmeda_tool.ui.components_db_view import ComponentsDBView
from fmeda_tool.ui.unit_editor_view import UnitEditorView, ProjectOverviewTab, ChangeEnvironmentalProfileDialog
from fmeda_tool.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_custom_component_dialog_validation_and_creation(fresh_isolated_db, qapp):
    """Test CustomComponentDialog field validation, non-100% total acceptance, and creation."""
    # 1. Test empty component type rejected
    dlg = CustomComponentDialog()
    dlg.type_input.setText("")
    dlg.fit_input.setValue(10.5)
    dlg.add_failure_mode("Mode 1", 50.0)
    dlg.add_failure_mode("Mode 2", 50.0)
    
    with patch.object(QMessageBox, "warning") as mock_warn:
        dlg._on_save()
        mock_warn.assert_called_once()
        assert "Component Type is required" in mock_warn.call_args[0][2]

    # 2. Test FIT value <= 0 rejected
    dlg.type_input.setText("Custom Sensor")
    dlg.fit_input.setValue(0.0)
    with patch.object(QMessageBox, "warning") as mock_warn:
        dlg._on_save()
        mock_warn.assert_called_once()
        assert "greater than 0" in mock_warn.call_args[0][2]

    # 3. Test fewer than 2 failure modes rejected
    dlg.fit_input.setValue(15.0)
    dlg.fm_table.setRowCount(0)
    dlg.add_failure_mode("Open Circuit", 40.0)
    with patch.object(QMessageBox, "warning") as mock_warn:
        dlg._on_save()
        mock_warn.assert_called_once()
        assert "At least 2 failure modes" in mock_warn.call_args[0][2]

    # 4. Test failure mode with empty name rejected
    dlg.add_failure_mode("   ", 30.0)
    with patch.object(QMessageBox, "warning") as mock_warn:
        dlg._on_save()
        mock_warn.assert_called_once()
        assert "cannot be empty" in mock_warn.call_args[0][2]

    # 5. Test failure mode percentages do not need to total 100% (e.g. 40% + 30% = 70%)
    dlg.fm_table.removeRow(1)
    dlg.add_failure_mode("Short Circuit", 30.0)
    assert dlg.fm_total_lbl.text() == "Total: 70.0%"
    
    # Optional display name
    dlg.display_name_input.setText("MY_CUSTOM_SENSOR")
    
    with patch.object(QMessageBox, "information") as mock_info:
        dlg._on_save()
        mock_info.assert_called_once()
        assert "successfully" in mock_info.call_args[0][2]

    # Verify custom component is saved in database
    results = ComponentLibraryService.search_custom_components(query="MY_CUSTOM_SENSOR")
    assert len(results) >= 1
    custom_comp = results[0]
    assert custom_comp["display_name"] == "MY_CUSTOM_SENSOR"
    assert custom_comp["component_type"] == "Custom Sensor"
    assert custom_comp["fits"] == 15.0
    assert len(custom_comp["failure_modes"]) == 2
    assert custom_comp["failure_modes"]["Open Circuit"] == 40.0
    assert custom_comp["failure_modes"]["Short Circuit"] == 30.0


def test_custom_component_cross_catalog_display_name_uniqueness(fresh_isolated_db, qapp):
    """Test that display names must be unique across Exida, Legacy, and Custom catalogs."""
    # Create first custom component with display name "CUSTOM_UNIQUE_1"
    ok, msg, c_id = ComponentLibraryService.create_custom_component(
        component_type="Optocoupler",
        fits=25.0,
        failure_modes={"Open": 50.0, "Short": 50.0},
        display_name="CUSTOM_UNIQUE_1"
    )
    assert ok is True

    # Try creating another custom component with same display name -> rejected with "Display Name already exists."
    ok2, msg2, _ = ComponentLibraryService.create_custom_component(
        component_type="Optocoupler",
        fits=25.0,
        failure_modes={"Open": 50.0, "Short": 50.0},
        display_name="CUSTOM_UNIQUE_1"
    )
    assert ok2 is False
    assert "Display Name already exists." in msg2

    # Try creating custom component with an existing Exida or Legacy display name -> rejected
    valid, v_msg = ComponentLibraryService.validate_display_name("CUSTOM_UNIQUE_1")
    assert valid is False
    assert "Display Name already exists." in v_msg


def test_custom_component_optional_display_name(fresh_isolated_db, qapp):
    """Test custom component with NULL / empty display name uses component type as active label."""
    ok, msg, c_id = ComponentLibraryService.create_custom_component(
        component_type="Pressure Sensor",
        fits=35.0,
        failure_modes={"Drift": 45.0, "Stuck Output": 35.0},
        display_name=None
    )
    assert ok is True
    
    snapshot = ComponentLibraryService.get_custom_component_snapshot(c_id)
    assert snapshot is not None
    assert snapshot["display_name"] is None
    assert snapshot["displayed_label"] == "Pressure Sensor"
    assert snapshot["source_type"] == "custom"


def test_custom_components_in_db_view_and_mapping_workspace(fresh_isolated_db, qapp):
    """Test custom components appearing in ComponentsDBView and ComponentMappingDialog."""
    # Create custom component
    ok, msg, c_id = ComponentLibraryService.create_custom_component(
        component_type="CAN Transceiver",
        fits=18.5,
        failure_modes={"Dominant Stuck": 60.0, "Recessive Stuck": 40.0},
        display_name="CAN_TRX_CUSTOM"
    )
    assert ok is True

    # Test ComponentsDBView
    db_view = ComponentsDBView()
    assert db_view.tabs.count() == 6
    assert db_view.tabs.tabText(2) == "Custom Components"
    assert db_view.custom_table.rowCount() >= 1
    
    # Test ComponentMappingDialog with Custom Components radio
    unit = Unit(id="u1", name="Interface FG", description="Interface functional group")
    dlg = ComponentMappingDialog(unit=unit, project_profile="Profile 1")
    dlg.custom_radio.setChecked(True)
    dlg._on_library_search()
    
    assert dlg.lib_table.rowCount() >= 1
    # Find our custom component in the table
    target_row = -1
    for r in range(dlg.lib_table.rowCount()):
        it = dlg.lib_table.item(r, 0)
        if it and "CAN_TRX_CUSTOM" in it.text():
            target_row = r
            break
    assert target_row >= 0
    dlg.lib_table.selectRow(target_row)
    assert dlg.selected_template is not None
    assert dlg.selected_template.fits == 18.5
    assert dlg.selected_template.source_type == "custom"


def test_project_profile_change_workflow_and_undo(fresh_isolated_db, qapp):
    """Test changing environmental profile updates Exida components and recalculates metrics, leaves legacy/custom unchanged, and Undo reverts cleanly."""
    window = MainWindow()
    project = Project(
        id="p_test_1",
        name="Profile Test Project",
        description="Profile test project description",
        selected_profile="Profile 1",
        environmental_profile="Profile 1"
    )
    unit = Unit(id="u2", name="Microcontroller FG", description="Microcontroller functional group")
    
    # 1. Add Exida component
    exida_snap = ComponentLibraryService.get_exida_component_snapshot("FR-000001", profile="Profile 1")
    if not exida_snap:
        exida_list = ComponentLibraryService.search_exida_components(profile="Profile 1")
        assert len(exida_list) > 0
        exida_snap = ComponentLibraryService.get_exida_component_snapshot(exida_list[0]["id"], profile="Profile 1")
    
    exida_comp = Component(
        id="c_exida_1",
        position="U1",
        name="MCU Controller",
        type=exida_snap.get("displayed_label") or exida_snap.get("display_name"),
        failure_rate=exida_snap.get("failure_rate"),
        failure_modes=dict(exida_snap.get("failure_modes", {})),
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name=fm,
                failure_rate_percentage=pct,
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            ) for fm, pct in exida_snap.get("failure_modes", {}).items()
        ],
        library_component_id=exida_snap.get("library_component_id"),
        failure_rate_id=exida_snap.get("failure_rate_id"),
        selected_profile="Profile 1",
        source_type="exida",
        snapshot=exida_snap
    )
    unit.components.append(exida_comp)
    
    # 2. Add Custom component (fixed FIT)
    custom_comp = Component(
        id="c_custom_1",
        position="U2",
        name="Custom ASIC",
        type="Custom ASIC",
        failure_rate=25.0,
        failure_modes={"Open": 60.0, "Short": 40.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Open",
                failure_rate_percentage=60.0,
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            ),
            FailureModeAssignment(
                failure_mode_name="Short",
                failure_rate_percentage=40.0,
                dangerous_failure_percentage=100.0,
                detection_percentage=0.0
            )
        ],
        selected_profile="Profile 1",
        source_type="custom"
    )
    unit.components.append(custom_comp)
    
    project.units.append(unit)
    CalculationService.calculate_project(project)
    
    initial_tot_fit = project.total_failure_rate
    initial_exida_fit = exida_comp.failure_rate
    
    # Load into window
    window.current_project = project
    window.unit_editor_view.load_project(project)
    
    overview_tab = window.unit_editor_view.overview_tab
    
    # Test Cancel Profile Change: Dialog opened then cancelled
    with patch.object(ChangeEnvironmentalProfileDialog, "exec", return_value=QDialog.DialogCode.Rejected):
        overview_tab._on_change_profile()
        assert project.selected_profile == "Profile 1"
        assert exida_comp.failure_rate == initial_exida_fit
        assert project.total_failure_rate == initial_tot_fit
        
    # Test Confirm Profile Change: Profile 1 -> Profile 2
    exida_snap_p2 = ComponentLibraryService.get_exida_component_snapshot(exida_snap["library_component_id"], profile="Profile 2")
    expected_p2_fit = exida_snap_p2.get("failure_rate")

    def mock_dlg_exec(dlg_self):
        dlg_self.target_profile = "Profile 2"
        return QDialog.DialogCode.Accepted

    def mock_msg_exec(msg_self):
        for btn in msg_self.buttons():
            if btn.text() == "Confirm":
                msg_self._test_clicked = btn
                break
        return 0

    with patch.object(ChangeEnvironmentalProfileDialog, "exec", mock_dlg_exec), \
         patch.object(QMessageBox, "exec", mock_msg_exec), \
         patch.object(QMessageBox, "clickedButton", lambda self: getattr(self, "_test_clicked", None)):
        overview_tab._on_change_profile()
                
    # Verify profile change effects
    cur_proj = window.current_project
    assert cur_proj.selected_profile == "Profile 2"
    assert cur_proj.environmental_profile == "Profile 2"
    
    cur_exida = cur_proj.units[0].components[0]
    assert cur_exida.selected_profile == "Profile 2"
    assert cur_exida.failure_rate == expected_p2_fit
    
    # Verify Custom component remained unchanged (25.0 FIT)
    cur_custom = cur_proj.units[0].components[1]
    assert cur_custom.failure_rate == 25.0
    
    # Verify Undo restores Profile 1 cleanly
    assert len(window.undo_stack) >= 1
    window._on_undo()
    
    restored_proj = window.current_project
    assert restored_proj.selected_profile == "Profile 1"
    assert restored_proj.environmental_profile == "Profile 1"
    assert restored_proj.units[0].components[0].failure_rate == initial_exida_fit
    assert restored_proj.units[0].components[1].failure_rate == 25.0
    assert abs(restored_proj.total_failure_rate - initial_tot_fit) < 1e-5


def test_custom_component_edit_crash_fix_and_update(fresh_isolated_db, qapp):
    """Test CustomComponentDialog accepts custom_comp arg, populates existing fields, and updates in-place without duplicating."""
    # 1. Create initial custom component
    ok, msg, initial_snap = ComponentLibraryService.create_custom_component(
        component_type="Microcontroller",
        fits=12.0,
        failure_modes={"Flash Error": 60.0, "RAM Error": 40.0},
        display_name="MCU_CUSTOM_TEST"
    )
    assert ok is True
    c_id = initial_snap["library_component_id"]

    # 2. Test opening CustomComponentDialog with custom_comp keyword argument (previously caused TypeError)
    results = ComponentLibraryService.search_custom_components(query="MCU_CUSTOM_TEST")
    assert len(results) == 1
    comp_dict = results[0]

    dlg = CustomComponentDialog(custom_comp=comp_dict)
    assert dlg.is_edit is True
    assert dlg.component_id == c_id
    assert dlg.type_input.text() == "Microcontroller"
    assert dlg.display_name_input.text() == "MCU_CUSTOM_TEST"
    assert dlg.fit_input.value() == 12.0
    assert dlg.fm_table.rowCount() == 2
    assert dlg.fm_total_lbl.text() == "Total: 100.0%"

    # 3. Test modifying fields in Edit mode: change FIT, add 3rd failure mode, change display name
    dlg.fit_input.setValue(14.5)
    dlg.add_failure_mode("Clock Fail", 20.0)
    assert dlg.fm_total_lbl.text() == "Total: 120.0%"
    dlg.display_name_input.setText("MCU_CUSTOM_TEST_V2")

    with patch.object(QMessageBox, "information") as mock_info:
        dlg._on_save()
        mock_info.assert_called_once()
        assert "updated successfully" in mock_info.call_args[0][2]

    # 4. Verify SQLite record is updated in place without duplicate creation
    all_custom = ComponentLibraryService.search_custom_components()
    matching = [c for c in all_custom if c["id"] == c_id]
    assert len(matching) == 1
    updated = matching[0]
    assert updated["display_name"] == "MCU_CUSTOM_TEST_V2"
    assert updated["fits"] == 14.5
    assert len(updated["failure_modes"]) == 3
    assert updated["failure_modes"]["Clock Fail"] == 20.0

    # Verify no stray duplicate with old name exists
    old_matching = [c for c in all_custom if c["display_name"] == "MCU_CUSTOM_TEST"]
    assert len(old_matching) == 0


def test_custom_component_deletion_workflow_and_confirmation(fresh_isolated_db, qapp):
    """Test deleting an unreferenced custom component prompts confirmation and deletes permanently from SQLite."""
    # 1. Create custom component to delete
    ok, msg, snap = ComponentLibraryService.create_custom_component(
        component_type="Test Sensor",
        fits=5.0,
        failure_modes={"Mode A": 50.0, "Mode B": 50.0},
        display_name="SENSOR_TO_DELETE"
    )
    assert ok is True
    c_id = snap["library_component_id"]

    db_view = ComponentsDBView()
    comp_item = None
    for r in ComponentLibraryService.search_custom_components():
        if r["id"] == c_id:
            comp_item = r
            break
    assert comp_item is not None

    # 2. Test Cancel Deletion: Click Cancel on confirmation modal
    def mock_msg_cancel(msg_self):
        for btn in msg_self.buttons():
            if btn.text() == "Cancel":
                msg_self._test_clicked = btn
                break
        return 0

    with patch.object(QMessageBox, "exec", mock_msg_cancel), \
         patch.object(QMessageBox, "clickedButton", lambda self: getattr(self, "_test_clicked", None)):
        db_view._on_delete_custom_clicked(comp_item)

    # Component must still exist
    assert ComponentLibraryService.get_custom_component_snapshot(c_id) is not None

    # 3. Test Confirm Deletion: Click Delete on confirmation modal
    def mock_msg_delete(msg_self):
        for btn in msg_self.buttons():
            if btn.text() == "Delete":
                msg_self._test_clicked = btn
                break
        return 0

    with patch.object(QMessageBox, "exec", mock_msg_delete), \
         patch.object(QMessageBox, "clickedButton", lambda self: getattr(self, "_test_clicked", None)):
        db_view._on_delete_custom_clicked(comp_item)

    # Component must be permanently removed from SQLite
    assert ComponentLibraryService.get_custom_component_snapshot(c_id) is None
    
    # Audit log must record deletion
    logs = ComponentLibraryService.get_change_logs(component_id=c_id)
    assert len(logs) >= 1
    assert logs[0]["action"] == "delete_custom_component"


def test_custom_component_deletion_blocked_when_referenced(fresh_isolated_db, qapp):
    """Test reference check blocks deleting a custom component that is currently in use."""
    # 1. Create custom component
    ok, msg, snap = ComponentLibraryService.create_custom_component(
        component_type="ADC Driver",
        fits=8.0,
        failure_modes={"Gain Error": 70.0, "Offset Error": 30.0},
        display_name="ADC_DRIVER_USED"
    )
    assert ok is True
    c_id = snap["library_component_id"]

    # 2. Create an active Project that uses this custom component
    project = Project(id="p_used", name="Active Safety Project", description="Test active project description")
    unit = Unit(id="u_main", name="Analog Processing FG", description="Analog processing functional group")
    comp_instance = Component(
        id="c_adc_1",
        position="U10",
        name="ADC_DRIVER_USED",
        type="ADC Driver",
        failure_rate=8.0,
        failure_modes={"Gain Error": 70.0, "Offset Error": 30.0},
        library_component_id=c_id,
        source_type="custom"
    )
    unit.components.append(comp_instance)
    project.units.append(unit)

    # 3. Test reference check helper directly
    is_ref, ref_msg, ref_list = ComponentLibraryService.is_custom_component_referenced(c_id, project=project)
    assert is_ref is True
    assert "Active Safety Project" in ref_msg
    assert "U10" in ref_msg
    assert len(ref_list) >= 1

    # 4. Test deleting from ComponentsDBView with active project attached
    db_view = ComponentsDBView(project=project)
    comp_dict = ComponentLibraryService.search_custom_components(query="ADC_DRIVER_USED")[0]

    with patch.object(QMessageBox, "warning") as mock_warn:
        db_view._on_delete_custom_clicked(comp_dict)
        mock_warn.assert_called_once()
        assert "Deletion Blocked" in mock_warn.call_args[0][1]
        assert "currently used and cannot be deleted" in mock_warn.call_args[0][2]

    # Component must still exist in SQLite
    assert ComponentLibraryService.get_custom_component_snapshot(c_id) is not None

    # 5. Test deleting from CustomComponentDialog with active project
    dlg = CustomComponentDialog(custom_comp=comp_dict, project=project)
    with patch.object(QMessageBox, "warning") as mock_warn2:
        dlg._on_delete_clicked()
        mock_warn2.assert_called_once()
        assert "currently used and cannot be deleted" in mock_warn2.call_args[0][2]

    assert ComponentLibraryService.get_custom_component_snapshot(c_id) is not None


def test_exida_and_legacy_cannot_be_deleted(fresh_isolated_db, qapp):
    """Test that Exida and Legacy components cannot be deleted and delete_custom_component rejects non-custom IDs."""
    db_view = ComponentsDBView()
    
    # Exida table actions must only be name assignment / editing (no delete button)
    assert db_view.exida_table.columnCount() == 9
    assert db_view.exida_table.horizontalHeaderItem(8).text() == "Actions"
    if db_view.exida_table.rowCount() > 0:
        action_btn = db_view.exida_table.cellWidget(0, 8)
        assert isinstance(action_btn, QPushButton)
        assert action_btn.text() in ("Edit Name", "+ Assign Name")
        
    # Legacy table actions must only be Retire / Reactivate (no delete button)
    assert db_view.legacy_table.columnCount() == 7
    if db_view.legacy_table.rowCount() > 0:
        action_btn_leg = db_view.legacy_table.cellWidget(0, 6)
        assert isinstance(action_btn_leg, QPushButton)
        assert action_btn_leg.text() in ("Retire", "Reactivate")

    # Calling delete_custom_component on Exida ID fails safely
    exida_list = ComponentLibraryService.search_exida_components()
    if exida_list:
        exida_id = exida_list[0]["id"]
        ok, msg = ComponentLibraryService.delete_custom_component(exida_id)
        assert ok is False
        assert "not found" in msg.lower()
        # Exida component still exists
        assert ComponentLibraryService.get_exida_component_snapshot(exida_id) is not None

    # Calling delete_custom_component on Legacy ID fails safely
    leg_list = ComponentLibraryService.search_legacy_components()
    if leg_list:
        leg_id = leg_list[0]["id"]
        ok2, msg2 = ComponentLibraryService.delete_custom_component(leg_id)
        assert ok2 is False
        assert "not found" in msg2.lower()
        # Legacy component still exists
        assert ComponentLibraryService.get_legacy_component_snapshot(leg_id) is not None


def test_component_picker_dialog_search_and_selection(fresh_isolated_db, qapp):
    """Test ComponentPickerDialog searching Exida and Legacy components and returning snapshot."""
    # 1. Test Exida search in picker
    picker = ComponentPickerDialog(selected_profile="Profile 2")
    assert picker.exida_radio.isChecked()
    assert not picker.prof_badge.isHidden()
    assert picker.table.columnCount() == 7
    assert picker.table.rowCount() > 0

    # Search for Resistor
    picker.search_input.setText("Resistor")
    assert picker.table.rowCount() > 0
    for r in range(picker.table.rowCount()):
        txt = picker.table.item(r, 0).text() + " " + picker.table.item(r, 1).text()
        assert "resistor" in txt.lower()

    # Select first row
    picker.table.selectRow(0)
    assert picker.selected_snapshot is not None
    assert picker.selected_snapshot["source_type"] == "exida"
    assert picker.select_btn.isEnabled()

    # 2. Test Legacy search in picker
    picker.legacy_radio.setChecked(True)
    assert picker.prof_badge.isHidden()
    assert picker.table.columnCount() == 5
    picker.search_input.setText("")
    assert picker.table.rowCount() > 0

    picker.table.selectRow(0)
    assert picker.selected_snapshot is not None
    assert picker.selected_snapshot["source_type"] == "legacy"


def test_copy_from_exida_component_workflow(fresh_isolated_db, qapp):
    """Test copying an Exida component into a new custom component, editing fields, display name uniqueness guard, and traceability."""
    # Find an Exida component
    exida_list = ComponentLibraryService.search_exida_components(profile="Profile 2")
    assert len(exida_list) > 0
    source_exida = exida_list[0]
    source_id = source_exida["id"]
    source_fr_id = source_exida["failure_rate_id"]
    source_label = source_exida["display_label"]
    source_fit_p2 = source_exida["failure_rate"]
    source_fms = dict(source_exida["failure_modes"])

    # 1. Open CustomComponentDialog in create mode
    dlg = CustomComponentDialog()
    assert not dlg.is_edit
    assert hasattr(dlg, "copy_btn")

    # 2. Simulate clicking Copy From Existing and selecting the Exida component with Profile 2
    exida_snap = ComponentLibraryService.get_exida_component_snapshot(source_id, profile="Profile 2")
    dlg._apply_copied_snapshot(exida_snap)

    # Verify form fields are prefilled with copied data
    assert dlg.type_input.text() == source_exida["component_type"]
    assert dlg.display_name_input.text() == source_label
    assert abs(dlg.fit_input.value() - source_fit_p2) < 1e-4
    assert dlg.fm_table.rowCount() == len(source_fms)
    assert not dlg.copied_info_lbl.isHidden()
    assert "Copied from Exida" in dlg.copied_info_lbl.text()
    assert dlg.copied_from_source_type == "exida"
    assert dlg.copied_from_component_id == source_id
    assert dlg.copied_from_failure_rate_id == source_fr_id
    assert dlg.copied_at is not None

    # 3. Test saving with unchanged source display name -> blocked by display-name uniqueness
    with patch.object(QMessageBox, "warning") as mock_warn:
        dlg._on_save()
        mock_warn.assert_called_once()
        assert "Display Name already exists. Enter a unique name or leave it empty." in mock_warn.call_args[0][2]

    # 4. User edits: change display name to unique label, modify FIT, and add a custom failure mode
    dlg.display_name_input.setText("COPIED_EXIDA_CUSTOM_MCU")
    dlg.fit_input.setValue(42.5)
    dlg.add_failure_mode("Extra Fail Mode", 15.0)

    with patch.object(QMessageBox, "information") as mock_info:
        dlg._on_save()
        mock_info.assert_called_once()
        assert "successfully" in mock_info.call_args[0][2]

    # 5. Verify newly created custom component in SQLite
    res = ComponentLibraryService.search_custom_components(query="COPIED_EXIDA_CUSTOM_MCU")
    assert len(res) == 1
    new_custom = res[0]
    assert new_custom["id"].startswith("custom_")
    assert new_custom["id"] != source_id
    assert new_custom["display_name"] == "COPIED_EXIDA_CUSTOM_MCU"
    assert new_custom["fits"] == 42.5
    assert len(new_custom["failure_modes"]) == len(source_fms) + 1
    assert new_custom["failure_modes"]["Extra Fail Mode"] == 15.0
    assert new_custom["copied_from_source_type"] == "exida"
    assert new_custom["copied_from_component_id"] == source_id
    assert new_custom["copied_from_failure_rate_id"] == source_fr_id
    assert new_custom["copied_at"] is not None

    # 6. Verify original Exida component remains completely unmodified
    orig_check = ComponentLibraryService.get_exida_component_snapshot(source_id, profile="Profile 2")
    assert orig_check["failure_rate"] == source_fit_p2
    assert len(orig_check["failure_modes"]) == len(source_fms)
    assert "Extra Fail Mode" not in orig_check["failure_modes"]


def test_copy_from_legacy_component_workflow(fresh_isolated_db, qapp):
    """Test copying a Legacy component into a new custom component, saving with empty display name, and traceability."""
    # Find a Legacy component with positive FIT
    legacy_list = [l for l in ComponentLibraryService.search_legacy_components() if float(l.get("fits") or 0.0) > 0.0]
    assert len(legacy_list) > 0
    source_leg = legacy_list[0]
    source_id = source_leg["id"]
    source_dname = source_leg["display_name"]
    source_fit = float(source_leg["fits"])
    source_fms = dict(source_leg["failure_modes"])

    dlg = CustomComponentDialog()
    leg_snap = ComponentLibraryService.get_legacy_component_snapshot(source_id)
    dlg._apply_copied_snapshot(leg_snap)

    assert dlg.type_input.text() == (source_leg.get("material") or source_leg["display_name"])
    assert dlg.display_name_input.text() == source_dname
    assert abs(dlg.fit_input.value() - source_fit) < 1e-4
    assert dlg.fm_table.rowCount() == len(source_fms)
    assert dlg.copied_from_source_type == "legacy"
    assert dlg.copied_from_component_id == source_id

    # Test leaving Display Name empty (valid)
    dlg.display_name_input.setText("")

    with patch.object(QMessageBox, "information") as mock_info:
        dlg._on_save()
        mock_info.assert_called_once()
        assert "successfully" in mock_info.call_args[0][2]

    # Verify custom component saved with display_name = None and active label = component type
    saved_snap = dlg.saved_snapshot
    assert saved_snap is not None
    assert saved_snap["display_name"] is None
    assert saved_snap["displayed_label"] == dlg.type_input.text()
    assert saved_snap["copied_from_source_type"] == "legacy"
    assert saved_snap["copied_from_component_id"] == source_id

    # Verify original legacy component is unchanged
    orig_leg = ComponentLibraryService.get_legacy_component_snapshot(source_id)
    assert orig_leg["display_name"] == source_dname
    assert orig_leg["failure_rate"] == source_fit


def test_copied_custom_component_available_in_db_view_and_mapping(fresh_isolated_db, qapp):
    """Test newly copied custom component is immediately visible and usable in ComponentsDBView and ComponentMappingDialog."""
    # Create copied custom component
    ok, msg, snap = ComponentLibraryService.create_custom_component(
        component_type="Optoisolator",
        fits=33.0,
        failure_modes={"CTR Degradation": 60.0, "LED Open": 40.0},
        display_name="OPTO_COPIED_TEST",
        copied_from_source_type="exida",
        copied_from_component_id="exida-123"
    )
    assert ok is True

    # 1. Check ComponentsDBView Custom tab
    db_view = ComponentsDBView()
    assert db_view.custom_table.rowCount() >= 1
    found_db = False
    for r in range(db_view.custom_table.rowCount()):
        it = db_view.custom_table.item(r, 0)
        if it and it.text() == "OPTO_COPIED_TEST":
            found_db = True
            break
    assert found_db is True

    # 2. Check ComponentMappingDialog Custom Components catalog
    unit = Unit(id="u_iso", name="Isolation FG", description="Isolation functional group")
    dlg = ComponentMappingDialog(unit=unit, project_profile="Profile 1")
    dlg.custom_radio.setChecked(True)
    dlg._on_library_search()

    found_map = False
    for r in range(dlg.lib_table.rowCount()):
        it = dlg.lib_table.item(r, 0)
        if it and "OPTO_COPIED_TEST" in it.text():
            found_map = True
            dlg.lib_table.selectRow(r)
            break
    assert found_map is True
    assert dlg.selected_template is not None
    assert dlg.selected_template.fits == 33.0


