"""View-only diagnostic library search and header behavior."""
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QDialog, QHeaderView
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtWidgets import QStyleOptionViewItem

from fmeda_tool.models import DiagnosticMeasure, Project, Component, Unit, FailureModeAssignment
from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel, COLUMN_HEADERS
from fmeda_tool.ui.delegates.fmeda_delegates import FmedaComboBoxDelegate
from fmeda_tool.ui.widgets.diagnostic_measure_selector import DiagnosticMeasureSelector
from fmeda_tool.ui.unit_editor_view import DiagnosticMeasureManagerDialog, DiagnosticMeasureMiniDialog


def catalog():
    return Project(id="p", name="Library", description="Test", diagnostic_measures=[
        DiagnosticMeasure(id="dm_alpha", name="Rail monitor", description="Supply voltage",
                          verification_method="Fault injection", execution_timing="Every cycle",
                          notes="Oscilloscope evidence"),
        DiagnosticMeasure(id="dm_beta", name="Watchdog", description="Processor timeout"),
    ])


@pytest.mark.parametrize("term", ["ALPH", "RAIL", "volt", "INJECT", "cycl", "OSCILLO"])
def test_live_partial_case_insensitive_search(qtbot, term):
    project = catalog()
    before = project.model_dump(mode="json")
    dialog = DiagnosticMeasureManagerDialog(project)
    qtbot.addWidget(dialog)
    qtbot.keyClicks(dialog.search_input, term)
    assert not dialog.table.isRowHidden(0)
    assert dialog.table.isRowHidden(1)
    assert project.model_dump(mode="json") == before
    dialog.clear_search_btn.click()
    assert all(not dialog.table.isRowHidden(row) for row in range(2))
    dialog.search_input.setText("no match")
    assert all(dialog.table.isRowHidden(row) for row in range(2))
    dialog.search_input.clear()
    assert all(not dialog.table.isRowHidden(row) for row in range(2))


def test_header_layout_survives_search_and_refresh(qtbot):
    dialog = DiagnosticMeasureManagerDialog(catalog())
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.table.horizontalHeader().length() == dialog.table.viewport().width())
    header = dialog.table.horizontalHeader()
    assert header.sectionsMovable()
    assert dialog.width() >= 1320
    assert sum(header.sectionSize(col) for col in range(6)) <= dialog.table.viewport().width()
    for col in range(6):
        assert not header.isSectionHidden(col)
        assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.Interactive
        assert header.sectionSize(col) >= header.sectionSizeHint(col)
    header.resizeSection(3, 410)
    header.moveSection(header.visualIndex(5), 0)
    dialog.search_input.setText("watch")
    dialog._refresh_table()
    dialog.clear_search_btn.click()
    assert header.sectionSize(3) == 410
    assert header.visualIndex(5) == 0


def test_description_absorbs_window_space_and_manual_resize(qtbot):
    dialog = DiagnosticMeasureManagerDialog(catalog())
    qtbot.addWidget(dialog)
    dialog.show()
    header = dialog.table.horizontalHeader()
    qtbot.waitUntil(lambda: header.length() == dialog.table.viewport().width())
    widths = [header.sectionSize(c) for c in range(6)]
    dialog.resize(dialog.width() + 400, dialog.height())
    qtbot.waitUntil(lambda: header.sectionSize(3) == widths[3] + 400)
    assert header.length() == dialog.table.viewport().width()
    assert [header.sectionSize(c) for c in (0, 1, 2, 4, 5)] == [widths[c] for c in (0, 1, 2, 4, 5)]
    header.resizeSection(3, header.sectionSize(3) - 100)
    assert header.sectionSize(3) == widths[3] + 300
    assert header.length() == dialog.table.viewport().width()
    dialog.resize(1440, dialog.height())
    qtbot.waitUntil(lambda: header.length() == dialog.table.viewport().width())


def assignment_project():
    project = catalog()
    assignment = FailureModeAssignment(failure_mode_name="Open", failure_rate_percentage=100,
                                      dc_test_ref="Historical evidence", detection_percentage=37)
    component = Component(id="c", name="Resistor", type="Resistor", position="R1",
                          failure_rate=10, failure_modes={"Open": 100},
                          failure_mode_assignments=[assignment])
    project.units = [Unit(id="u", name="Group", description="Test", components=[component])]
    return project


@pytest.mark.parametrize("term", ["ALPH", "RAIL", "volt", "INJECT", "cycl", "OSCILLO"])
def test_searchable_assignment_filters_and_commits(qtbot, term):
    project = assignment_project()
    model = FmedaTableModel(project.units[0], project)
    model.set_edit_mode(True)
    assignment = model.rows[0].assignment
    delegate = FmedaComboBoxDelegate()
    index = model.index(0, 14)
    editor = delegate.createEditor(None, QStyleOptionViewItem(), index)
    qtbot.addWidget(editor)
    assert isinstance(editor, DiagnosticMeasureSelector)
    delegate.setEditorData(editor, index)
    before = project.model_dump(mode="json")
    with patch.object(model, "_compute_entry_metrics") as compute, \
         qtbot.assertNotEmitted(model.data_modified):
        editor.lineEdit().selectAll()
        qtbot.keyClicks(editor.lineEdit(), term)
        assert editor.search_proxy.rowCount() == 1
        assert editor.search_proxy.index(0, 0).data(Qt.ItemDataRole.UserRole) == "dm_alpha"
        delegate.setModelData(editor, model, index)
        assert not compute.called
    assert project.model_dump(mode="json") == before
    delegate.commitData.connect(lambda selected: delegate.setModelData(selected, model, index))
    with qtbot.waitSignal(delegate.closeEditor):
        editor.completer().activated[QModelIndex].emit(editor.completer().completionModel().index(0, 0))
    assert assignment.diagnostic_measure_id == "dm_alpha"
    assert assignment.detection_percentage == 37
    assert assignment.dc_test_ref == "Historical evidence"


def test_legacy_reference_roundtrip_and_column_removal(qtbot, tmp_path):
    from fmeda_tool.services.project_service import ProjectService
    project = assignment_project()
    path = tmp_path / "legacy.json"
    path.write_text(project.model_dump_json(by_alias=True), encoding="utf-8")
    reopened, _, _ = ProjectService.load_and_migrate_project(str(path))
    model = FmedaTableModel(reopened.units[0], reopened)
    metrics = dict(model.rows[0].row_metrics)
    assert model.columnCount() == 36
    assert "DC Test Ref" not in COLUMN_HEADERS
    assert model.rows[0].assignment.dc_test_ref == "Historical evidence"
    assert "Historical evidence" in reopened.model_dump_json(by_alias=True)
    model.set_edit_mode(True)
    model.setData(model.index(0, 14), "dm_alpha")
    assert model.rows[0].row_metrics == metrics


def test_filtered_edit_and_remove_keep_catalog_identity(qtbot, monkeypatch):
    project = catalog()
    dialog = DiagnosticMeasureManagerDialog(project)
    qtbot.addWidget(dialog)
    dialog.search_input.setText("watch")
    dialog.table.setCurrentCell(1, 0)

    def edit(editor):
        editor.name_input.setText("Updated watchdog")
        editor._on_accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(DiagnosticMeasureMiniDialog, "exec", edit)
    dialog._on_edit()
    assert project.diagnostic_measures[1].name == "Updated watchdog"
    assert project.diagnostic_measures[0].name == "Rail monitor"
    dialog._on_remove()
    assert [dm.id for dm in project.diagnostic_measures] == ["dm_alpha"]
    dialog.clear_search_btn.click()
    assert not dialog.table.isRowHidden(0)


def test_search_does_not_call_project_services(qtbot):
    dialog = DiagnosticMeasureManagerDialog(catalog())
    qtbot.addWidget(dialog)
    with patch("fmeda_tool.ui.unit_editor_view.ValidationService") as validation, \
         patch("fmeda_tool.services.calculation_service.CalculationService") as calculation:
        dialog.search_input.setText("rail")
        dialog.clear_search_btn.click()
        assert not validation.mock_calls
        assert not calculation.mock_calls
