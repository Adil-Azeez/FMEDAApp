from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QMessageBox

from fmeda_tool.models import Component, FailureModeAssignment, Project, Unit
from fmeda_tool.db.database import get_db_connection
from fmeda_tool.services.component_library_service import ComponentLibraryService as Library
from fmeda_tool.services.calculation_service import CalculationService as Calc
from fmeda_tool.services.project_service import ProjectService
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.ui.dialogs.component_instance_dialog import ComponentInstanceDialog
from fmeda_tool.ui.dialogs.bulk_assignment_dialogs import DeleteComponentsConfirmDialog
from fmeda_tool.ui.unit_editor_view import UnitEditorView, ChangeEnvironmentalProfileDialog, ComponentMappingDialog
from fmeda_tool.ui.main_window import MainWindow
from fmeda_tool.ui.verification_view import VerificationView


def project():
    component = Component(id="one", position="R1", name="Resistor", type="Resistor", failure_rate=0.4,
        selected_profile="Profile 3", failure_modes={"Open": 30, "Short": 70},
        snapshot={"description": "Original description", "component_type": "Resistor"},
        failure_mode_assignments=[FailureModeAssignment(
            failure_mode_name=name, failure_rate_percentage=pct, diagnostic_function="Yes",
            dangerous_failure_percentage=danger, detection_percentage=12.345678,
            classification="safe_failure" if danger == 0 else "dangerous_failure",
            secondary_failure_component_id="legacy-secondary", proof_test_a=23.456789,
            notes="Engineering notes", review_status="approved")
            for name, pct, danger in (("Open", 30, 0), ("Short", 70, 100))])
    return Project(id="protected", name="Protected", description="Test", selected_profile="Profile 3",
        units=[Unit(id="u", name="Group", description="Test", components=[component]),
               Unit(id="other", name="Other", description="Test")])


def unlock(dialog, proceed=True):
    def warning_exec(box):
        assert "modified reliability model" in box.text()
        assert "original library component will not be changed" in box.text()
        button = next(b for b in box.buttons() if b.text() == ("Continue" if proceed else "Cancel"))
        button.click()
    with patch.object(QMessageBox, "exec", warning_exec):
        dialog._unlock_distribution()


def editor(p):
    view = UnitEditorView()
    view.load_project(p)
    view.unit_tabs.setCurrentIndex(1)
    return view, view.unit_tabs.widget(1)


def test_protected_unlock_cancel_and_engineering_preserved(qapp, fresh_isolated_db):
    p = project()
    comp = p.units[0].components[0]
    original = comp.model_dump()
    dialog = ComponentInstanceDialog(comp, p, allow_distribution=True)
    assert "Secondary Failure" not in [dialog.table.horizontalHeaderItem(c).text() for c in range(dialog.table.columnCount())]
    for col in (0, 1):
        assert not dialog.table.item(0, col).flags() & Qt.ItemFlag.ItemIsEditable
    unlock(dialog, False)
    assert not dialog.distribution_unlocked
    assert comp.model_dump() == original
    unlock(dialog)
    assert dialog.distribution_unlocked
    for col in (0, 1):
        assert dialog.table.item(0, col).flags() & Qt.ItemFlag.ItemIsEditable
    dialog.table.cellWidget(0, 4).setValue(15.5)
    with patch.object(Library, "create_custom_component") as create:
        dialog._on_save()
    create.assert_not_called()
    expected = deepcopy(original)
    expected["failure_mode_assignments"][0]["detection_percentage"] = 15.5
    assert comp.model_dump() == expected
    assert dialog.result() == QDialog.DialogCode.Accepted


@pytest.mark.parametrize("source_type", ["exida", "legacy", "custom"])
def test_independent_custom_model_preserves_source_and_other_instances(qapp, fresh_isolated_db, tmp_path, source_type):
    p = project()
    comp = p.units[0].components[0]
    table = "components" if source_type == "exida" else "legacy_components"
    if source_type == "custom":
        ok, _, source = Library.create_custom_component("Original", 0.4, comp.failure_modes, description="Original")
        assert ok
        source_id = source["library_component_id"]
        table = "custom_components"
    else:
        with get_db_connection() as conn:
            source_id = conn.execute(f"SELECT id FROM {table} LIMIT 1").fetchone()[0]
    comp.source_type, comp.library_component_id = source_type, source_id
    other = comp.model_copy(deep=True)
    other.id, other.position = "two", "R2"
    p.units[0].components.append(other)
    other_before = other.model_dump()
    with get_db_connection() as conn:
        source_before = tuple(conn.execute(f"SELECT * FROM {table} WHERE id=?", (source_id,)).fetchone())
    dialog = ComponentInstanceDialog(comp, p, allow_distribution=True)
    unlock(dialog)
    dialog.table.item(0, 0).setText("Renamed")
    dialog.table.item(0, 1).setText("20")
    dialog._add_row("New mode", 15)
    dialog.table.setCurrentCell(1, 0)
    dialog._remove_mode()
    assert dialog.total_label.text() == "Total: 35.0%"
    dialog.description_input.setPlainText("  Modified description\nFor this instance  ")
    dialog._on_save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert comp.failure_modes == {"Renamed": 20, "New mode": 15}
    assert comp.source_type == "custom" and comp.library_component_id != source_id
    assert comp.selected_profile == "Profile 3"
    snapshot = Library.get_custom_component_snapshot(comp.library_component_id)
    assert snapshot["failure_rate"] == 0.4
    assert snapshot["description"] == "Modified description\nFor this instance"
    assert snapshot["display_name"] is None
    assert snapshot["copied_from_component_id"] == source_id
    assert snapshot["copied_from_source_type"] == source_type
    assert comp.failure_mode_assignments[0].secondary_failure_component_id == "legacy-secondary"
    assert comp.failure_mode_assignments[0].proof_test_a == 23.456789
    assert other.model_dump() == other_before
    with get_db_connection() as conn:
        assert tuple(conn.execute(f"SELECT * FROM {table} WHERE id=?", (source_id,)).fetchone()) == source_before
    path = tmp_path / "modified.json"
    ProjectService.save_project_atomically(p, str(path))
    loaded, _, _ = ProjectService.load_and_migrate_project(str(path))
    assert loaded.units[0].components[0].model_dump() == comp.model_dump()


@pytest.mark.parametrize("invalid", ["description", "display_name", "duplicate", "rate", "one_mode"])
def test_distribution_validation_is_atomic(qapp, fresh_isolated_db, invalid):
    p = project()
    comp = p.units[0].components[0]
    before = comp.model_dump()
    Library.create_custom_component("Existing", 1, {"A": 50, "B": 50}, display_name="ExistingLabel", description="Existing")
    dialog = ComponentInstanceDialog(comp, p, allow_distribution=True)
    unlock(dialog)
    dialog.table.item(0, 1).setText("20")
    if invalid == "description":
        dialog.description_input.setPlainText(" \n ")
    elif invalid == "display_name":
        dialog.display_name_input.setText("ExistingLabel")
    elif invalid == "duplicate":
        dialog.table.item(0, 0).setText("Short")
    elif invalid == "rate":
        dialog.table.item(0, 1).setText("-1")
    else:
        dialog.table.setCurrentCell(1, 0)
        dialog._remove_mode()
    with patch.object(QMessageBox, "warning") as warning:
        dialog._on_save()
    warning.assert_called_once()
    assert comp.model_dump() == before
    assert len(Library.search_custom_components()) == 1


def test_context_edit_recalculates_validates_once_and_undo(qapp, fresh_isolated_db):
    p = project()
    window = MainWindow()
    window.current_project = p
    window.unit_editor_view.load_project(p)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.widget(1)
    assert not tab.edit_component("one")
    tab.enable_editing()
    before = p.units[0].components[0].model_dump()
    def edit(dialog):
        unlock(dialog)
        dialog.table.item(0, 0).setText("Modified Open")
        dialog._on_save()
        return dialog.result()
    with patch.object(ComponentInstanceDialog, "exec", edit), \
         patch.object(Calc, "calculate_unit", wraps=Calc.calculate_unit) as calculate, \
         patch.object(ValidationService, "validate_row", wraps=ValidationService.validate_row) as validate:
        assert tab.edit_component("one")
    assert sum(call.args[0] is tab.unit for call in calculate.call_args_list) == 1
    assert validate.call_count == 2  # One validation per failure-mode row in the rebuilt block.
    assert window.has_unsaved_changes and len(window.undo_stack) == 1
    assert tab.model.rows[0].fm_name == "Modified Open"
    window._on_undo()
    assert window.current_project.units[0].components[0].model_dump() == before


def test_summary_reads_existing_results_without_calculation(qapp):
    p = project()
    view, tab = editor(p)
    expected = "λtotal: 0.4000 FIT    |    λsafe: 0.1200 FIT    |    λdangerous: 0.2800 FIT    |    λDiagGesamt: 0.4000 FIT"
    assert tab.diagnostic_summary.text() == expected
    before = p.model_dump()
    with patch.object(Calc, "calculate_unit", side_effect=AssertionError("Display recalculated")), \
         patch.object(Calc, "calculate_unit_metrics", side_effect=AssertionError("Display recalculated")), \
         patch.object(Calc, "calculate_project", side_effect=AssertionError("Display recalculated")):
        tab._refresh_diagnostic_summary()
        assert tab.diagnostic_summary.text() == expected
    assert p.model_dump() == before
    tab.enable_editing()
    tab.model.setData(tab.model.index(0, 10), "No")
    assert "λDiagGesamt: 0.2800 FIT" in tab.diagnostic_summary.text()
    tab.model.setData(tab.model.index(0, 12), 50)
    assert "λsafe: 0.0600 FIT" in tab.diagnostic_summary.text()
    assert "λdangerous: 0.3400 FIT" in tab.diagnostic_summary.text()
    tab.confirm_changes()
    assert "λsafe: 0.0600 FIT" in tab.diagnostic_summary.text()
    view.unit_tabs.setCurrentIndex(2)
    other = view.unit_tabs.widget(2)
    assert other.diagnostic_summary.text().count("0.0000 FIT") == 4
    with patch.object(Calc, "get_unit_result", return_value=None):
        other._refresh_diagnostic_summary()
    assert other.diagnostic_summary.text().count("N/A") == 4


def test_delete_and_mapping_reload_summary(qapp):
    p = project()
    view, tab = editor(p)
    tab.enable_editing()
    tab.table.selected_component_ids = {"one"}
    with patch.object(DeleteComponentsConfirmDialog, "exec", return_value=QDialog.DialogCode.Accepted):
        tab.delete_selected_components()
    assert tab.diagnostic_summary.text().count("0.0000 FIT") == 4
    def map_component(dialog):
        tab.unit.components = project().units[0].components
        return QDialog.DialogCode.Accepted
    with patch.object(ComponentMappingDialog, "exec", map_component), patch.object(QMessageBox, "information"):
        tab._on_component_bom_mapping()
    assert "λtotal: 0.4000 FIT" in tab.diagnostic_summary.text()


def test_page_three_labels_only(qapp):
    p = project()
    before = Calc.calculate_project(p)
    view = VerificationView()
    view.load_project(p)
    labels = [view.secondary_table.item(r, 0).text() for r in range(view.secondary_table.rowCount())]
    assert "PFDavg" in labels and "PFHd" in labels
    assert "Average PFD (PFDavg)" not in labels and "Maximum PFD (PFHd)" not in labels
    assert Calc.calculate_project(p) == before


def test_summary_after_profile_change_and_undo(qapp, fresh_isolated_db):
    p = project()
    comp = p.units[0].components[0]
    comp.library_component_id = "source"
    window = MainWindow()
    window.current_project = p
    window.unit_editor_view.load_project(p)
    def profile_exec(dialog):
        dialog.target_profile = "Profile 4"
        return QDialog.DialogCode.Accepted
    def confirm(box):
        next(b for b in box.buttons() if b.text() == "Confirm").click()
    with patch.object(ChangeEnvironmentalProfileDialog, "exec", profile_exec), \
         patch.object(QMessageBox, "exec", confirm), \
         patch.object(Library, "get_exida_component_snapshot", return_value={
             "failure_rate": 0.8, "failure_modes": {"Open": 30, "Short": 70}}):
        window.unit_editor_view.overview_tab._on_change_profile()
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.widget(1)
    assert "λtotal: 0.8000 FIT" in tab.diagnostic_summary.text()
    assert "λsafe: 0.2400 FIT" in tab.diagnostic_summary.text()
    window._on_undo()
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    restored = window.unit_editor_view.unit_tabs.widget(1)
    assert "λtotal: 0.4000 FIT" in restored.diagnostic_summary.text()


def test_legacy_lazy_assignments_are_included_in_summary(qapp):
    p = project()
    p.units[0].components[0].failure_mode_assignments = []
    Calc.calculate_project(p)
    view, tab = editor(p)
    assert "λtotal: 0.4000 FIT" in tab.diagnostic_summary.text()
    assert "λdangerous: 0.4000 FIT" in tab.diagnostic_summary.text()
    assert "λDiagGesamt: 0.0000 FIT" in tab.diagnostic_summary.text()


def test_missing_source_description_requires_entry_and_unique_name_saves(qapp, fresh_isolated_db):
    p = project()
    comp = p.units[0].components[0]
    comp.snapshot = None
    dialog = ComponentInstanceDialog(comp, p, allow_distribution=True)
    unlock(dialog)
    dialog.table.item(0, 1).setText("25")
    with patch.object(QMessageBox, "warning") as warning:
        dialog._on_save()
    assert "Description is required" in warning.call_args.args[2]
    dialog.description_input.setPlainText("New engineering model")
    dialog.display_name_input.setText("UniqueEngineeringModel")
    dialog._on_save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert Library.get_custom_component_snapshot(comp.library_component_id)["display_name"] == "UniqueEngineeringModel"
