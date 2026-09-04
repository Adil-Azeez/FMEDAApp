"""
Unit and integration tests for Deviation and Mitigation library dialogs,
constructors, result contracts, getters, cancellation, editing, dropdown refreshes,
and unit context handling.
"""

import pytest
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtCore import Qt

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, Deviation, Mitigation,
    DeviationType, DeviationSeverity, MitigationType, MitigationStatus, SafetyStandard
)
from fmeda_tool.ui.dialogs.deviation_dialog import DeviationDialog
from fmeda_tool.ui.dialogs.mitigation_dialog import MitigationDialog
from fmeda_tool.ui.unit_editor_view import (
    DeviationManagerDialog, MitigationManagerDialog, UnitEditorView, FunctionalGroupTab
)


@pytest.fixture(scope="session")
def qapp():
    """Ensure QApplication instance exists for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def create_test_project() -> Project:
    """Create a sample project for testing dialogs."""
    dev1 = Deviation(
        id="dev_001",
        name="Short Circuit Deviation",
        description="Short circuit across component terminals",
        deviation_type=DeviationType.DANGEROUS_DETECTED,
        severity=DeviationSeverity.HIGH,
        failure_mode="Short Circuit",
        effect="Output stuck at rail"
    )
    mit1 = Mitigation(
        id="mit_001",
        name="Current Limiter",
        description="Hardware current limiting resistor",
        mitigation_type=MitigationType.PROTECTIVE_CIRCUIT,
        status=MitigationStatus.APPROVED,
        effectiveness=0.95
    )
    
    comp1 = Component(
        id="comp_001",
        position="R101",
        name="Resistor 10k",
        type="Resistor",
        failure_rate=10.0,
        failure_modes={"Short": 50.0, "Open": 50.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Short",
                failure_rate_percentage=50.0,
                classification="dangerous_failure",
                deviation_id="dev_001",
                mitigation_id="mit_001"
            )
        ]
    )
    unit1 = Unit(
        id="unit_001",
        name="Sensor Processing Unit",
        description="Processes raw sensor signals",
        components=[comp1]
    )
    
    return Project(
        id="proj_dialog_test",
        name="Dialog Test Project",
        description="Test project description for dialogs",
        safety_standard=SafetyStandard.IEC_61508,
        deviations=[dev1],
        mitigations=[mit1],
        units=[unit1]
    )


def test_deviation_dialog_constructor_and_getters(qapp):
    """Test DeviationDialog constructor with and without unit_name, and verify public getters."""
    # 1. Constructor with explicit unit_name
    dialog = DeviationDialog(unit_name="Power Unit")
    assert dialog.unit_name == "Power Unit"
    assert dialog.is_editing is False
    assert "Power Unit" in dialog.windowTitle()
    
    # Fill form
    dialog.name_input.setText("Overvoltage Deviation")
    dialog.impact_input.setText("Damage to downstream IC")
    dialog.description_input.setPlainText("Input exceeds maximum operating rating")
    
    # Save
    dialog._on_save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    
    # Verify getters
    saved_dev = dialog.get_deviation()
    assert isinstance(saved_dev, Deviation)
    assert saved_dev.name == "Overvoltage Deviation"
    assert saved_dev.effect == "Damage to downstream IC"
    assert saved_dev.description == "Input exceeds maximum operating rating"
    
    dev_data = dialog.get_deviation_data()
    assert isinstance(dev_data, dict)
    assert dev_data["name"] == "Overvoltage Deviation"
    assert dev_data["effect"] == "Damage to downstream IC"
    assert dev_data["description"] == "Input exceeds maximum operating rating"
    
    # 2. Constructor default unit_name
    dialog_def = DeviationDialog()
    assert dialog_def.unit_name == "Project / Global"


def test_mitigation_dialog_constructor_and_getters(qapp):
    """Test MitigationDialog constructor, validation, and public getters."""
    # 1. Constructor with unit_name
    dialog = MitigationDialog(unit_name="ADC Subsystem")
    assert dialog.unit_name == "ADC Subsystem"
    assert dialog.is_editing is False
    
    # Fill form
    dialog.name_input.setText("Zener Clamp")
    dialog.description_input.setPlainText("Zener diode clamps overvoltage to 5.1V")
    dialog.effectiveness_input.setValue(0.98)
    
    # Save
    dialog._on_save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    
    # Verify getters
    saved_mit = dialog.get_mitigation()
    assert isinstance(saved_mit, Mitigation)
    assert saved_mit.name == "Zener Clamp"
    assert saved_mit.description == "Zener diode clamps overvoltage to 5.1V"
    assert saved_mit.effectiveness == 0.98
    
    mit_data = dialog.get_mitigation_data()
    assert isinstance(mit_data, dict)
    assert mit_data["name"] == "Zener Clamp"
    assert mit_data["description"] == "Zener diode clamps overvoltage to 5.1V"
    assert mit_data["effectiveness"] == 0.98
    assert "mitigation_type" in mit_data


def test_open_deviation_manager_and_add_deviation(qapp, monkeypatch):
    """Test opening DeviationManagerDialog and adding a new deviation."""
    project = create_test_project()
    initial_count = len(project.deviations)
    
    manager = DeviationManagerDialog(project, unit_name="Sensor Processing Unit")
    assert manager.unit_name == "Sensor Processing Unit"
    assert manager.table.rowCount() == initial_count
    
    # Mock DeviationDialog to simulate user accepting a new deviation
    def mock_exec(self):
        self.name_input.setText("Thermal Runaway")
        self.impact_input.setText("Component destruction")
        self.description_input.setPlainText("Temperature exceeds Tj_max")
        self._on_save()
        return QDialog.DialogCode.Accepted
        
    monkeypatch.setattr(DeviationDialog, "exec", mock_exec)
    
    manager._on_add()
    
    assert len(project.deviations) == initial_count + 1
    assert project.deviations[-1].name == "Thermal Runaway"
    assert manager.table.rowCount() == initial_count + 1


def test_cancel_add_deviation(qapp, monkeypatch):
    """Test cancelling Add Deviation does not alter project deviations."""
    project = create_test_project()
    initial_count = len(project.deviations)
    
    manager = DeviationManagerDialog(project, unit_name="Sensor Processing Unit")
    
    # Mock DeviationDialog reject
    monkeypatch.setattr(DeviationDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    
    manager._on_add()
    
    assert len(project.deviations) == initial_count
    assert manager.table.rowCount() == initial_count


def test_edit_existing_deviation(qapp, monkeypatch):
    """Test editing an existing deviation via DeviationManagerDialog."""
    project = create_test_project()
    dev_to_edit = project.deviations[0]
    
    manager = DeviationManagerDialog(project, unit_name="Sensor Processing Unit")
    manager.table.setCurrentCell(0, 0)
    
    # Mock DeviationDialog editing
    def mock_edit_exec(self):
        assert self.is_editing is True
        assert self.name_input.text() == "Short Circuit Deviation"
        self.name_input.setText("Updated Short Circuit Deviation")
        self.description_input.setPlainText("Updated description text")
        self._on_save()
        return QDialog.DialogCode.Accepted
        
    monkeypatch.setattr(DeviationDialog, "exec", mock_edit_exec)
    
    manager._on_edit()
    
    assert dev_to_edit.name == "Updated Short Circuit Deviation"
    assert dev_to_edit.description == "Updated description text"
    assert manager.table.item(0, 0).text() == "Updated Short Circuit Deviation"


def test_open_mitigation_manager_and_add_mitigation(qapp, monkeypatch):
    """Test opening MitigationManagerDialog and adding a new mitigation."""
    project = create_test_project()
    initial_count = len(project.mitigations)
    
    manager = MitigationManagerDialog(project, unit_name="Sensor Processing Unit")
    assert manager.unit_name == "Sensor Processing Unit"
    assert manager.table.rowCount() == initial_count
    
    # Mock MitigationDialog accept
    def mock_mit_exec(self):
        self.name_input.setText("Hardware Watchdog")
        self.description_input.setPlainText("External watchdog timer resets MCU on hang")
        self.effectiveness_input.setValue(0.99)
        self._on_save()
        return QDialog.DialogCode.Accepted
        
    monkeypatch.setattr(MitigationDialog, "exec", mock_mit_exec)
    
    manager._on_add()
    
    assert len(project.mitigations) == initial_count + 1
    assert project.mitigations[-1].name == "Hardware Watchdog"
    assert manager.table.rowCount() == initial_count + 1


def test_cancel_add_mitigation(qapp, monkeypatch):
    """Test cancelling Add Mitigation does not modify project mitigations."""
    project = create_test_project()
    initial_count = len(project.mitigations)
    
    manager = MitigationManagerDialog(project, unit_name="Sensor Processing Unit")
    
    monkeypatch.setattr(MitigationDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    
    manager._on_add()
    
    assert len(project.mitigations) == initial_count
    assert manager.table.rowCount() == initial_count


def test_edit_existing_mitigation(qapp, monkeypatch):
    """Test editing an existing mitigation via MitigationManagerDialog."""
    project = create_test_project()
    mit_to_edit = project.mitigations[0]
    
    manager = MitigationManagerDialog(project, unit_name="Sensor Processing Unit")
    manager.table.setCurrentCell(0, 0)
    
    def mock_edit_mit_exec(self):
        assert self.is_editing is True
        assert self.name_input.text() == "Current Limiter"
        self.name_input.setText("Active Current Limiter Circuit")
        self.effectiveness_input.setValue(0.99)
        self._on_save()
        return QDialog.DialogCode.Accepted
        
    monkeypatch.setattr(MitigationDialog, "exec", mock_edit_mit_exec)
    
    manager._on_edit()
    
    assert mit_to_edit.name == "Active Current Limiter Circuit"
    assert mit_to_edit.effectiveness == 0.99
    assert manager.table.item(0, 0).text() == "Active Current Limiter Circuit"


def test_fmeda_table_dropdowns_refresh_on_deviation_and_mitigation_add(qapp, monkeypatch):
    """Test that FMEDA table dropdown selectors immediately reflect added deviations and mitigations."""
    project = create_test_project()
    editor = UnitEditorView()
    editor.load_project(project)
    
    # Switch to functional group tab 1
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.widget(1)
    assert isinstance(tab, FunctionalGroupTab)
    assert tab.is_populated is True
    
    # Check initial dropdown items in deviation column (col 13) and mitigation column (col 21)
    dev_opts = tab.model.data(tab.model.index(0, 13), Qt.ItemDataRole.UserRole + 1)
    mit_opts = tab.model.data(tab.model.index(0, 21), Qt.ItemDataRole.UserRole + 1)
    
    assert len(dev_opts) == 2  # "-- None --" + "Short Circuit Deviation"
    assert len(mit_opts) == 2  # "-- None --" + "Current Limiter"
    
    # Add new deviation via dialog
    def mock_dev_add(self):
        self.name_input.setText("New Temp Deviation")
        self.description_input.setPlainText("Temp desc")
        self._on_save()
        return QDialog.DialogCode.Accepted
        
    monkeypatch.setattr(DeviationDialog, "exec", mock_dev_add)
    tab._on_manage_deviations_clicked()
    
    # Dropdown options should now have 3 items
    dev_opts_updated = tab.model.data(tab.model.index(0, 13), Qt.ItemDataRole.UserRole + 1)
    assert len(dev_opts_updated) == 3
    assert dev_opts_updated[2]["label"] == "New Temp Deviation"
    
    # Add new mitigation via dialog
    def mock_mit_add(self):
        self.name_input.setText("New Optocoupler Isolation")
        self.description_input.setPlainText("Opto desc")
        self._on_save()
        return QDialog.DialogCode.Accepted
        
    monkeypatch.setattr(MitigationDialog, "exec", mock_mit_add)
    tab._on_manage_mitigations_clicked()
    
    # Dropdown options should now have 3 items
    mit_opts_updated = tab.model.data(tab.model.index(0, 21), Qt.ItemDataRole.UserRole + 1)
    assert len(mit_opts_updated) == 3
    assert mit_opts_updated[2]["label"] == "New Optocoupler Isolation"
