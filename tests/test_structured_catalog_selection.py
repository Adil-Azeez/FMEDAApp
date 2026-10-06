"""Catalog compatibility, selection, validation and UI regression coverage."""
import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QMessageBox, QStyleOptionViewItem

from fmeda_tool.models import DiagnosticMeasure, Project, Unit, Component, FailureModeAssignment, Deviation, Mitigation
from fmeda_tool.services.project_service import ProjectService
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.ui.unit_editor_view import DiagnosticMeasureMiniDialog, DiagnosticMeasureManagerDialog, UnitEditorView
from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel
from fmeda_tool.ui.delegates.fmeda_delegates import FmedaComboBoxDelegate
from fmeda_tool.ui.dialogs.component_instance_dialog import ComponentInstanceDialog
from fmeda_tool.ui.dialogs.bulk_assignment_dialogs import BulkActionSummaryDialog


def sample():
    devs = [Deviation(id='d1', name='Voltage high', description='Supply exceeds limit', effect='Processor damage',
                      keywords='rail surge', deviation_type='dangerous_detected', severity='high', failure_mode='Short', mitigation_ids=['m1']),
            Deviation(id='d2', name='Silent', description='No output', deviation_type='safe', severity='low', failure_mode='Open')]
    mits = [Mitigation(id='m1', name='Clamp', description='Clamp voltage', mitigation_type='protective_circuit'),
            Mitigation(id='m2', name='Reverse link', description='Independent monitor', mitigation_type='diagnostic', deviation_ids=['d1']),
            Mitigation(id='m3', name='Unrelated', description='Other', mitigation_type='other')]
    a = FailureModeAssignment(failure_mode_name='Short', failure_rate_percentage=100, deviation_id='d1', detection_percentage=12)
    c = Component(id='c', name='Resistor', type='Resistor', position='R1', failure_rate=10,
                  failure_modes={'Short':100}, failure_mode_assignments=[a])
    return Project(id='p', name='Catalog test', description='Test', units=[Unit(id='u', name='Group', description='Test group', components=[c])],
                   deviations=devs, mitigations=mits, diagnostic_measures=[
                       DiagnosticMeasure(id='dm', name='Monitor', description='Monitor voltage', dc=90, verification_method='Fault injection'),
                       DiagnosticMeasure(id='empty', name='Review', description='Inspect')])


def row(project):
    return project.units[0].components[0].failure_mode_assignments[0]


@pytest.mark.parametrize('field', ['id', 'name', 'description'])
def test_mandatory_model_and_dialog(qapp, field):
    data = dict(id='id', name='Name', description='Description')
    data[field] = ' '
    with pytest.raises(ValidationError):
        DiagnosticMeasure(**data)
    dialog = DiagnosticMeasureMiniDialog(project=sample())
    dialog.id_input.setText(data['id'])
    dialog.name_input.setText(data['name'])
    dialog.desc_input.setText(data['description'])
    with patch.object(QMessageBox, 'warning') as warning:
        dialog._on_accept()
    assert warning.called and dialog.result() != QDialog.DialogCode.Accepted


def test_catalog_add_edit_unique_rename_delete(qapp, monkeypatch):
    p = sample()
    manager = DiagnosticMeasureManagerDialog(p)
    def add(dialog):
        dialog.id_input.setText('new')
        dialog.name_input.setText('New measure')
        dialog.desc_input.setText('Description')
        dialog.failure_reaction_input.setText('Trip')
        dialog._on_accept()
        return dialog.result()
    monkeypatch.setattr(DiagnosticMeasureMiniDialog, 'exec', add)
    manager._on_add()
    assert p.diagnostic_measures[-1].dc is None
    assert p.diagnostic_measures[-1].failure_reaction == 'Trip'
    assert manager.table.columnCount() == 6
    with patch.object(QMessageBox, 'warning') as warning:
        manager._on_add()
    assert warning.called and len(p.diagnostic_measures) == 3
    row(p).diagnostic_measure_id = 'new'
    row(p).detection_percentage = 55
    manager.table.setCurrentCell(2, 0)
    def edit(dialog):
        dialog.id_input.setText('renamed')
        dialog.name_input.setText('Updated')
        dialog._on_accept()
        return dialog.result()
    monkeypatch.setattr(DiagnosticMeasureMiniDialog, 'exec', edit)
    manager._on_edit()
    assert row(p).diagnostic_measure_id == 'renamed'
    assert row(p).detection_percentage == 55
    assert p.diagnostic_measures[-1].failure_reaction == 'Trip'
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
        manager._on_remove()
    assert row(p).diagnostic_measure_id is None and len(p.diagnostic_measures) == 2


def test_legacy_load_edit_and_roundtrip(qapp, tmp_path):
    p = sample()
    data = p.model_dump(mode='json')
    data['diagnostic_measures'] = [dict(id='old', dc=75, description='Legacy description', notes='Keep', riskId='risk')]
    data['units'][0]['components'][0]['failure_mode_assignments'][0]['mitigation_id'] = 'm3'
    path = tmp_path / 'legacy.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    loaded, _, _ = ProjectService.load_and_migrate_project(str(path))
    dm = loaded.diagnostic_measures[0]
    assert dm.name == dm.description and dm.dc == 75
    dialog = DiagnosticMeasureMiniDialog(dm, project=loaded)
    dialog._on_accept()
    assert dialog.dm.risk_id == 'risk' and dialog.dm.notes == 'Keep'
    loaded.diagnostic_measures[0] = dialog.dm
    ProjectService.save_project_atomically(loaded, str(path))
    reopened, _, _ = ProjectService.load_and_migrate_project(str(path))
    assert reopened.diagnostic_measures[0] == dialog.dm
    assert row(reopened).mitigation_id == 'm3'
    assert any('Invalid deviation/mitigation' in a['message'] for a in ValidationService.validate_project(reopened))


def test_row_prefill_override_and_reference(qapp):
    p = sample()
    model = FmedaTableModel(p.units[0], p)
    model.set_edit_mode(True)
    assert model.setData(model.index(0,14), 'dm')
    assert row(p).detection_percentage == 90
    assert 'Verification Method: Fault injection' in model.index(0,14).data(Qt.ItemDataRole.ToolTipRole)
    assert row(p).dc_test_ref is None
    assert model.setData(model.index(0,15), 42)
    assert p.diagnostic_measures[0].dc == 90 and row(p).detection_percentage == 42
    assert not model.setData(model.index(0,14), 'dm')
    assert row(p).detection_percentage == 42
    assert model.setData(model.index(0,14), 'empty')
    assert row(p).detection_percentage == 42
    assert 'Verification Method: \n' in model.index(0,14).data(Qt.ItemDataRole.ToolTipRole)
    assert not model.setData(model.index(0,14), 'unknown')


@pytest.mark.parametrize('query', ['vOLT', 'EXCEEDS', 'rocessor', 'SURG'])
def test_search_while_typing_and_select(qapp, qtbot, query):
    p = sample()
    row(p).deviation_id = 'd2'
    model = FmedaTableModel(p.units[0], p)
    model.set_edit_mode(True)
    delegate = FmedaComboBoxDelegate()
    index = model.index(0,9)
    editor = delegate.createEditor(None, QStyleOptionViewItem(), index)
    qtbot.addWidget(editor)
    delegate.setEditorData(editor, index)
    editor.lineEdit().selectAll()
    qtbot.keyClicks(editor.lineEdit(), query)
    assert editor.search_proxy.rowCount() == 1
    assert editor.search_proxy.index(0,0).data() == 'Voltage high'
    delegate.setModelData(editor, model, index)
    assert row(p).deviation_id == 'd2'  # Search alone never changes assignment.
    editor.completer().activated[ type(index) ].emit(editor.completer().completionModel().index(0,0))
    delegate.setModelData(editor, model, index)
    assert row(p).deviation_id == 'd1'
    assert [o['data'] for o in model.index(0,16).data(Qt.ItemDataRole.UserRole+1)] == [None,'m1','m2']


def test_mitigation_validation_change_empty_and_view_mode(qapp):
    p = sample()
    model = FmedaTableModel(p.units[0],p)
    assert not model.setData(model.index(0,16),'m1')
    model.set_edit_mode(True)
    assert not model.setData(model.index(0,16),'m3')
    assert model.setData(model.index(0,16),'m1')
    assert model.setData(model.index(0,9),'d2')
    assert row(p).mitigation_id is None
    assert model.index(0,16).data(Qt.ItemDataRole.UserRole+1) == [{'label':'-- None --','data':None}]
    assert not model.setData(model.index(0,16),'m1')
    row(p).mitigation_id='m1'
    model.refresh_all_metrics()
    assert 'Invalid' in model.index(0,16).data()
    assert model.rows[0].validation_status == 'error'
    assert model.setData(model.index(0,16),None)


def test_component_dialog_filters_prefills_and_preserves_catalog(qapp):
    p=sample()
    dialog=ComponentInstanceDialog(p.units[0].components[0],p)
    mitigation=dialog._engineering_widget(0,'mitigation_id')
    assert [mitigation.itemData(i) for i in range(mitigation.count())] == [None,'m1','m2']
    mitigation.setCurrentIndex(1)
    deviation=dialog._engineering_widget(0,'deviation_id')
    deviation.setCurrentIndex(deviation.findData('d2'))
    assert mitigation.count()==1 and mitigation.currentData() is None
    dm=dialog._engineering_widget(0,'diagnostic_measure_id')
    dm.setCurrentIndex(dm.findData('dm'))
    assert dialog._engineering_widget(0,'detection_percentage').value()==90
    assert dialog._engineering_widget(0,'dc_test_ref').placeholderText()=='Fault injection'
    dialog._engineering_widget(0,'detection_percentage').setValue(45)
    dialog._on_save()
    assert row(p).diagnostic_measure_id=='dm' and row(p).detection_percentage==45
    assert row(p).dc_test_ref is None and p.diagnostic_measures[0].dc==90


def test_bulk_rejects_invalid_and_empty_default_keeps_dc(qapp):
    p=sample()
    editor=UnitEditorView()
    editor.load_project(p)
    editor.unit_tabs.setCurrentIndex(1)
    tab=editor.unit_tabs.widget(1)
    tab.enable_editing()
    tab.table.selected_component_ids={'c'}
    with patch.object(QMessageBox,'warning') as warning:
        assert not tab.bulk_assign_mitigation('m3')
    assert warning.called
    with patch.object(BulkActionSummaryDialog,'exec',return_value=QDialog.DialogCode.Accepted):
        assert tab.bulk_assign_mitigation('m1')
        assert tab.bulk_assign_diagnostic_measure('empty')
        assert row(p).detection_percentage==12
        assert tab.bulk_assign_deviation('d2')
    assert row(p).mitigation_id is None
    tab.cancel_changes()
    assert p.units[0].components[0].failure_mode_assignments[0].deviation_id=='d1'
    editor.close()



def test_zero_default_and_optional_fields_roundtrip(qapp, tmp_path):
    p = sample()
    dm = p.diagnostic_measures[0]
    dm.dc = 0
    dm.failure_reaction = 'Safe state'
    dm.execution_timing = 'Startup'
    dm.implementation_type = 'Software'
    dm.responsible = 'Engineer'
    dm.notes = 'Evidence'
    row(p).detection_percentage = None
    dialog = ComponentInstanceDialog(p.units[0].components[0], p)
    selector = dialog._engineering_widget(0, 'diagnostic_measure_id')
    selector.setCurrentIndex(selector.findData('dm'))
    dialog._on_save()
    assert row(p).detection_percentage == 0
    path = tmp_path / 'structured.json'
    ProjectService.save_project_atomically(p, str(path))
    reopened, _, _ = ProjectService.load_and_migrate_project(str(path))
    assert reopened.diagnostic_measures == p.diagnostic_measures
    assert row(reopened).dc_test_ref is None
    assert 'verification_method' not in row(reopened).model_dump()


def test_search_no_results_then_mouse_selection(qapp, qtbot):
    p = sample()
    model = FmedaTableModel(p.units[0], p)
    model.set_edit_mode(True)
    delegate = FmedaComboBoxDelegate()
    index = model.index(0, 9)
    selector = delegate.createEditor(None, QStyleOptionViewItem(), index)
    qtbot.addWidget(selector)
    selector.resize(350, 30)
    selector.show()
    selector.lineEdit().selectAll()
    qtbot.keyClicks(selector.lineEdit(), 'does-not-exist')
    assert selector.search_proxy.rowCount() == 0
    selector.lineEdit().selectAll()
    qtbot.keyClicks(selector.lineEdit(), 'silen')
    assert selector.search_proxy.rowCount() == 1
    popup = selector.completer().popup()
    match = popup.model().index(0, 0)
    qtbot.mouseClick(popup.viewport(), Qt.MouseButton.LeftButton, pos=popup.visualRect(match).center())
    delegate.setModelData(selector, model, index)
    assert row(p).deviation_id == 'd2'
