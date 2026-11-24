"""Project-only cases, proof-test presentation, and catalog compatibility."""
from contextlib import ExitStack
from unittest.mock import patch

import openpyxl
import pytest
from pydantic import ValidationError
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QMessageBox

from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment, DiagnosticMeasure, ComponentDB, BOMComponent
from fmeda_tool.models.diagnostic_measure import DEFAULT_SOURCE_LINK
from fmeda_tool.services.assessment_service import split_case, allocation_errors
from fmeda_tool.services.calculation_service import CalculationService as Calc
from fmeda_tool.services.component_remapping_service import ComponentRemappingService
from fmeda_tool.services.project_service import ProjectService
from fmeda_tool.services.export_service import ExportService
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.services.change_history_service import ChangeHistoryService
from fmeda_tool.ui.dialogs.component_instance_dialog import ComponentInstanceDialog
from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel
from fmeda_tool.ui.unit_editor_view import DiagnosticMeasureMiniDialog
from fmeda_tool.ui.main_window import MainWindow


def fixture():
    dm = DiagnosticMeasure(diagnostic_measure_test='Test_ID_1', description='Circuit analysis')
    cases = [FailureModeAssignment(failure_mode_name=name, failure_rate_percentage=pct,
             parent_failure_mode_id='parent-' + name, classification='dangerous_failure',
             detection_percentage=20, proof_test_a=50, proof_test_b=25, proof_test_c=100,
             diagnostic_measure_id=dm.id, diagnostic_function='Yes', notes='Keep evidence')
             for name, pct in [('Open', 30), ('Short', 70)]]
    c = Component(id='c', name='Resistor', type='Resistor', position='R1', failure_rate=100,
                  failure_modes={'Open': 30, 'Short': 70}, failure_mode_ids={'Open': 'parent-Open', 'Short': 'parent-Short'},
                  failure_mode_assignments=cases)
    p = Project(id='p', name='Assessment cases', description='Test', diagnostic_measures=[dm],
                units=[Unit(id='u', name='Group', description='Test', components=[c])])
    return p, c


def split(c):
    first, second = split_case(c, c.failure_mode_assignments[0])
    c.failure_mode_assignments[:1] = [first, second]
    return first, second


def test_case_allocation_conserves_parent_and_independent_engineering():
    p, c = fixture()
    before = Calc.calculate_component(c)
    a, b = split(c)
    assert a.assignment_id != b.assignment_id
    assert a.allocation_percentage == b.allocation_percentage == 15
    assert Calc.calculate_component(c) == before
    assert Calc.calculate_diagnostic_lambda(c) == 100
    a.set_classification('diagnostic_function_failure')
    a.diagnostic_function = 'No'
    result = Calc.calculate_component(c)
    assert result['gesamtgerat']['lambda'] == 100
    assert result['lambda_diag_failure'] == 15
    assert result['dangerous_undetected_rate'] == pytest.approx(68)
    assert Calc.calculate_diagnostic_lambda(c) == 85
    assert b.classification == 'dangerous_failure' and b.notes == 'Keep evidence'
    assert c.failure_modes == {'Open': 30, 'Short': 70}


def test_proof_results_per_case_and_weighted_group(qapp):
    p, c = fixture()
    a, b = split(c)
    a.proof_test_a, b.proof_test_a = 0, 100
    a.proof_test_b, b.proof_test_b = 40, 60
    row = Calc.calculate_assignment(c, b)
    assert row['lambda_du'] == 12
    assert [row[f'proof_test_{x}_contribution'] for x in 'abc'] == pytest.approx([12, 7.2, 12])
    result = Calc.calculate_group_result(p.units[0], p)
    assert [result[f'proof_test_{x}_contribution'] for x in 'abc'] == pytest.approx([40, 26, 80])
    assert [result[f'proof_test_{x}_coverage'] for x in 'abc'] == pytest.approx([50, 32.5, 100])
    assert not any(key.startswith('pfd_avg_') for key in result)
    model = FmedaTableModel(p.units[0], p)
    model.set_edit_mode(True)
    assert model.index(1, 35).data() == '12.0000'
    assert model.setData(model.index(1, 19), 0)
    assert model.index(1, 35).data() == '0.0000'
    assert model.index(0, 38).data() == '35.00%'
    for case in c.failure_mode_assignments:
        case.set_classification('safe_failure')
    model.refresh_all_metrics()
    assert model.index(0, 38).data() == 'N/A'
    assert model.index(0, 35).data() == '0.0000'


def test_proof_visibility_only_changes_view(qtbot):
    p, c = fixture()
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_project = p
    window.unit_editor_view.load_project(p)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.currentWidget()
    before, undo, dirty = p.model_dump(), list(window.undo_stack), window.has_unsaved_changes
    with ExitStack() as stack:
        for service in (Calc, ValidationService):
            for name, value in vars(service).items():
                if isinstance(value, staticmethod):
                    stack.enter_context(patch.object(service, name, side_effect=AssertionError(name)))
        for visible in (True, False, True):
            tab.cb_proof.setChecked(visible)
            for col in (*range(19, 22), *range(35, 41)):
                assert tab.table.isColumnHidden(col) != visible
    assert p.model_dump() == before
    assert window.undo_stack == undo and window.has_unsaved_changes == dirty


def test_split_dialog_validates_without_library_writes_and_cancel(qtbot):
    p, c = fixture()
    before = c.model_dump()
    dialog = ComponentInstanceDialog(c, p, allow_distribution=True)
    qtbot.addWidget(dialog)
    assert dialog.add_mode_button.text() == 'Add Failure Mode'
    dialog.table.setCurrentCell(0, 0)
    dialog._split_selected()
    assert c.model_dump() == before
    assert dialog.table.rowCount() == 3
    assert 'Parent 30' in dialog.allocation_summary.text()
    assert 'Remaining 0' in dialog.allocation_summary.text()
    dialog.table.item(2, 1).setText('20')
    with patch.object(QMessageBox, 'warning') as warning:
        dialog._on_save()
    assert warning.called and c.model_dump() == before
    dialog.table.item(2, 1).setText('15')
    with patch('fmeda_tool.services.component_library_service.ComponentLibraryService.create_custom_component',
               side_effect=AssertionError('Split must not write library')):
        dialog._on_save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert len(c.failure_mode_assignments) == 3 and not allocation_errors(c)
    another = ComponentInstanceDialog(c, p)
    qtbot.addWidget(another)
    before = c.model_dump()
    another.table.setCurrentCell(0, 0)
    another._split_selected()
    another.reject()
    assert c.model_dump() == before


def test_save_reopen_invalid_save_and_audit(tmp_path):
    p, c = fixture()
    path = tmp_path / 'project.json'
    ProjectService.save_project_atomically(p, str(path))
    a, b = split(c)
    ProjectService.save_project_atomically(p, str(path))
    reopened, _, _ = ProjectService.load_and_migrate_project(str(path))
    assert reopened.units[0].components[0].failure_mode_assignments == c.failure_mode_assignments
    assert Calc.calculate_group_result(reopened.units[0], reopened) == Calc.calculate_group_result(p.units[0], p)
    baseline = ChangeHistoryService.meaningful_state(p)
    b.notes = 'Second case only'
    changes = ChangeHistoryService.changes(baseline, ChangeHistoryService.meaningful_state(p))
    assert len(changes) == 1 and changes[0]['new_value'] == 'Second case only'
    original_file = path.read_bytes()
    a.allocation_percentage = 20
    with pytest.raises(ValueError, match='Remaining -5'):
        ProjectService.save_project_atomically(p, str(path))
    assert path.read_bytes() == original_file
    assert any('Allocated' in issue['message'] for issue in ValidationService.validate_project(p))


def test_compatible_remap_retains_all_cases():
    p, c = fixture()
    a, b = split(c)
    template = ComponentDB(id='new', display_name='New model', fits=120,
        failure_modes={'Renamed': 30, 'Short': 70}, failure_mode_ids={'Renamed': 'parent-Open', 'Short': 'parent-Short'})
    plan = ComponentRemappingService.plan(c, template, BOMComponent(id='bom', designator='R1'), project=p)
    cases = plan.component.failure_mode_assignments
    assert len(cases) == 3
    assert [case.assignment_id for case in cases[:2]] == [a.assignment_id, b.assignment_id]
    assert [case.allocation_percentage for case in cases[:2]] == [15, 15]
    assert all(case.failure_mode_name == 'Renamed' for case in cases[:2])
    assert plan.preserved['diagnostic measures'] == 3
    assert not plan.component.remapping_review_assignments


def test_excel_case_traceability_catalog_and_proof_values(tmp_path):
    p, c = fixture()
    a, b = split(c)
    b.notes = 'Second case'
    path = tmp_path / 'cases.xlsx'
    assert ExportService.export_to_excel(p, str(path))
    wb = openpyxl.load_workbook(path)
    try:
        sheet = wb['Group']
        headers = [cell.value for cell in sheet[1]]
        rows = [dict(zip(headers, values)) for values in sheet.iter_rows(min_row=2, values_only=True)]
        assert len(rows) == 3
        assert [row['Case Allocation %'] for row in rows] == [.15, .15, .7]
        assert [row['Parent Failure-Mode %'] for row in rows] == [.3, .3, .7]
        assert rows[0]['Assessment Case ID'] != rows[1]['Assessment Case ID']
        assert rows[0]['Parent Failure-Mode ID'] == rows[1]['Parent Failure-Mode ID'] == 'parent-Open'
        assert rows[1]['Comments / Justification'] == 'Second case'
        assert sum(row['lambda (FIT)'] for row in rows) == 100
        assert rows[0]['Diagnostic Measure Test'] == 'Test_ID_1'
        assert rows[0]['Diagnostic Measure Description'] == 'Circuit analysis'
        assert rows[0]['Diagnostic Measure ID'] is None
        assert rows[0]['Source Link'] == DEFAULT_SOURCE_LINK
        assert rows[0]['lambda_duPTCA (FIT)'] == 6
        assert rows[0]['PTCA %'] == .5
        assert sheet.cell(2, headers.index('Source Link') + 1).hyperlink.target == DEFAULT_SOURCE_LINK
        assert not any('PFDavgA' in str(h) for h in headers)
    finally:
        wb.close()


def test_optional_visible_id_required_test_description_and_legacy(qtbot):
    p, c = fixture()
    with pytest.raises(ValidationError):
        DiagnosticMeasure(description='A new record requires a test')
    for field in ('diagnostic_measure_test', 'description'):
        with pytest.raises(ValidationError):
            DiagnosticMeasure(**{'diagnostic_measure_test': 'Test', 'description': 'Details', field: ''})
    dialog = DiagnosticMeasureMiniDialog(project=p)
    qtbot.addWidget(dialog)
    assert not hasattr(dialog, 'name_input')
    assert dialog.id_input.text() == '' and dialog.source_link_input.text() == DEFAULT_SOURCE_LINK
    dialog.test_input.setText('Test_ID_2')
    dialog.desc_input.setText('Hardware test')
    dialog._on_accept()
    assert dialog.dm.display_id is None and dialog.dm.id
    assert dialog.dm.display_label == 'Test_ID_2 | Hardware test'
    assert 'name' not in dialog.dm.model_dump()
    legacy = DiagnosticMeasure.model_validate(dict(id='dm-old', name='Legacy monitor', description='Legacy details', dc=75))
    assert legacy.id == legacy.display_id == 'dm-old'
    assert legacy.diagnostic_measure_test == 'Legacy monitor'
    assert legacy.description == 'Legacy details' and legacy.dc == 75


def test_split_undo_restores_unsplit_project(qtbot, monkeypatch):
    p, c = fixture()
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_project = p
    window.unit_editor_view.load_project(p)
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.currentWidget()
    tab.enable_editing()
    before = c.model_dump()
    def accept(dialog):
        dialog._on_save()
        return dialog.result()
    monkeypatch.setattr(ComponentInstanceDialog, 'exec', accept)
    assert tab.edit_component(c.id, split_mode=('Open', None))
    assert len(c.failure_mode_assignments) == 3
    assert len(window.undo_stack) == 1
    window._on_undo()
    assert window.current_project.units[0].components[0].model_dump() == before
