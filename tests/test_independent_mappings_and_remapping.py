from copy import deepcopy
from unittest.mock import patch

import openpyxl
import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

from fmeda_tool.models import (Project, Unit, ComponentDB, BOMComponent, FailureModeAssignment,
                               Deviation, DiagnosticMeasure, Mitigation)
from fmeda_tool.services.mapping_service import MappingService as Mapping
from fmeda_tool.services.component_remapping_service import ComponentRemappingService as Remap
from fmeda_tool.services.calculation_service import CalculationService as Calc
from fmeda_tool.services.project_service import ProjectService
from fmeda_tool.services.export_service import ExportService
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.ui.dialogs.component_mapping_dialog import ComponentMappingDialog
from fmeda_tool.ui.dialogs.remapping_review_dialog import RemappingReviewDialog
from fmeda_tool.ui.main_window import MainWindow
from fmeda_tool.ui.verification_view import VerificationView


def fixture():
    bom = BOMComponent(id='bom9', designator='C9', part_number='123', value='10n')
    one = ComponentDB(id='CKPN', display_name='CKPN', source_type='exida', fits=100,
        failure_modes={'Open': 60, 'Short': 40}, failure_mode_ids={'Open': 'fm-open', 'Short': 'fm-short'})
    two = one.model_copy(deep=True, update={'id': 'CT', 'display_name': 'CT', 'fits': 20})
    unit = Unit(id='u', name='Group A', description='Test', bom_components=[bom])
    project = Project(id='p', name='Independent mappings', description='Test', units=[unit])
    return project, unit, bom, one, two


def add(unit, bom, *templates):
    candidate = Mapping.prepare_batch(unit, [(bom.id, t) for t in templates])
    Mapping.commit_batch(unit, candidate)


def test_mapping_pairs_append_remove_idempotent_and_atomic(tmp_path):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    old = unit.components[0]
    old.failure_mode_assignments[0].notes = 'Keep engineering work'
    old_dump = old.model_dump()
    first_id = unit.component_mappings[0].id
    add(unit, bom, two, one, two)
    assert len(unit.components) == len(unit.component_mappings) == 2
    assert unit.components[0] is old and old.model_dump() == old_dump
    assert len({m.id for m in unit.component_mappings}) == 2
    before = unit.model_dump()
    add(unit, bom, one, two)
    assert unit.model_dump() == before
    with pytest.raises(ValueError):
        Mapping.prepare_batch(unit, [(bom.id, one), ('missing-bom', two)])
    assert unit.model_dump() == before
    path = tmp_path / 'multi.json'
    ProjectService.save_project_atomically(project, str(path))
    reopened, _, _ = ProjectService.load_and_migrate_project(str(path))
    assert [m.model_dump() for m in reopened.units[0].component_mappings] == before['component_mappings']
    assert reopened.units[0].components[0].failure_mode_assignments[0].notes == 'Keep engineering work'
    second_id = unit.component_mappings[1].id
    Mapping.commit_batch(unit, Mapping.prepare_batch(unit, removals=[second_id]))
    assert [m.id for m in unit.component_mappings] == [first_id]
    assert unit.components == [old]


def test_legacy_identity_migration_is_stable_and_does_not_write(tmp_path):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    data = project.model_dump(mode='json')
    mapping = data['units'][0]['component_mappings'][0]
    for key in ('id', 'bom_position', 'library_source', 'component_instance_id', 'metadata'):
        mapping.pop(key)
    import json
    path = tmp_path / 'legacy.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    before = path.read_bytes()
    loaded, _, _ = ProjectService.load_and_migrate_project(str(path))
    again, _, _ = ProjectService.load_and_migrate_project(str(path))
    assert path.read_bytes() == before
    assert loaded.units[0].component_mappings == again.units[0].component_mappings
    assert loaded.units[0].component_mappings[0].component_instance_id == unit.components[0].id
    assert len(loaded.units[0].components) == 1


def test_remapping_preserves_every_engineering_field_and_matches_id_before_name():
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    old = unit.components[0]
    a = old.failure_mode_assignments[0]
    a.deviation_id = 'dev'; a.diagnostic_measure_id = 'dm'; a.mitigation_id = 'mit'
    a.classification = 'dangerous_failure'; a.dangerous_failure_percentage = 100
    a.detection_percentage = 87; a.diagnostic_function = 'Yes'; a.review_status = 'reviewed'
    a.proof_test_a = 30; a.proof_test_b = 40; a.proof_test_c = 50; a.notes = 'Engineering rationale'
    before = old.model_dump()
    # An earlier name match must not steal the stable ID belonging to Renamed Open.
    two.failure_modes = {'Open': 40, 'Renamed Open': 60}
    two.failure_mode_ids = {'Open': 'fm-short', 'Renamed Open': 'fm-open'}
    plan = Remap.plan(old, two, bom, project=project)
    actual = plan.component.failure_mode_assignments[1].model_dump()
    expected = a.model_dump(); expected['failure_mode_name'] = 'Renamed Open'
    assert actual == expected
    assert old.model_dump() == before
    assert plan.component.id == old.id
    assert plan.preserved['deviations'] == plan.preserved['diagnostic measures'] == 1
    assert plan.preserved['mitigations'] == 0
    assert any('mitigation' in warning for warning in plan.review)
    assert any('deviation' in warning for warning in plan.review)
    assert plan.component.failure_mode_assignments[1].mitigation_id == 'mit'


def test_assignment_id_name_and_explicit_matching_and_archive(tmp_path):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    old = unit.components[0]
    old.failure_mode_assignments[0].notes = 'Open work'
    old.failure_mode_assignments[1].notes = 'Short work'
    two.failure_mode_ids = {}
    two.failure_modes = {'Renamed': 60, ' SHORT ': 40}
    two.snapshot = {'assignment_ids': {'Renamed': old.failure_mode_assignments[0].assignment_id}}
    plan = Remap.plan(old, two, bom)
    assert [a.notes for a in plan.component.failure_mode_assignments] == ['Open work', 'Short work']
    two.snapshot = None
    plan = Remap.plan(old, two, bom)
    assert len(plan.component.remapping_review_assignments) == 1
    assert plan.component.remapping_review_assignments[0].notes == 'Open work'
    matched = Remap.plan(old, two, bom, explicit_matches={'Renamed': old.failure_mode_assignments[0].assignment_id})
    assert matched.component.failure_mode_assignments[0].notes == 'Open work'
    mid = unit.component_mappings[0].id
    Mapping.commit_batch(unit, Mapping.prepare_batch(unit, replacements={mid: plan.component}))
    path = tmp_path / 'remapped.json'
    ProjectService.save_project_atomically(project, str(path))
    loaded, _, _ = ProjectService.load_and_migrate_project(str(path))
    assert loaded.units[0].components[0].remapping_review_assignments[0].notes == 'Open work'
    assert any('Remapping Review Required' in a['message'] for a in ValidationService.validate_project(loaded))


def test_remap_duplicate_pair_rejected_without_mutation():
    project, unit, bom, one, two = fixture()
    add(unit, bom, one, two)
    before = unit.model_dump()
    proposed = Remap.plan(unit.components[0], two, bom).component
    with pytest.raises(ValueError, match='already mapped'):
        Mapping.prepare_batch(unit, replacements={unit.component_mappings[0].id: proposed})
    assert unit.model_dump() == before


def test_preview_cancel_and_explicit_choice(qtbot):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    two.failure_modes = {'New mode': 100}; two.failure_mode_ids = {}
    before = unit.model_dump()
    dialog = RemappingReviewDialog(unit.components[0], two, bom, 'Profile 1', project)
    qtbot.addWidget(dialog)
    assert 'Requires review:' in dialog.summary.toPlainText()
    dialog.choices['New mode'].setCurrentIndex(1)
    assert len(dialog.plan.component.remapping_review_assignments) == 1
    dialog.reject()
    assert unit.model_dump() == before


def test_mapping_workspace_lists_both_and_cancel_is_pure(qtbot):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one, two)
    before = unit.model_dump()
    dialog = ComponentMappingDialog(unit, project=project)
    qtbot.addWidget(dialog)
    text = dialog.bom_table.item(0, 8).text()
    assert 'CKPN' in text and 'CT' in text
    dialog.unit.bom_components[0].notes = 'Discarded edit'
    dialog.reject()
    assert unit.model_dump() == before


def test_excel_includes_every_instance_and_retained_review(tmp_path):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one, two)
    unit.components[0].remapping_review_assignments = [FailureModeAssignment(
        failure_mode_name='Historic mode', failure_rate_percentage=100, notes='Retained rationale')]
    path = tmp_path / 'mappings.xlsx'
    assert ExportService.export_to_excel(project, str(path))
    workbook = openpyxl.load_workbook(path)
    assert workbook['Component Mappings'].max_row == 3
    rows = list(workbook['Component Mappings'].values)[1:]
    assert {row[5] for row in rows} == {'CKPN', 'CT'}
    assert len({row[6] for row in rows}) == 2
    text = str(list(workbook[unit.name].values))
    assert 'CKPN' in text and 'CT' in text
    assert 'Retained rationale' in str(list(workbook['Remapping Review'].values))
    workbook.close()


def test_page3_cache_selection_and_refresh_are_pure(qtbot):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    other = unit.model_copy(deep=True, update={'id': 'other', 'name': 'Group B'})
    other.components[0].failure_rate = 20
    project.units.append(other)
    before = project.model_dump()
    view = VerificationView(); qtbot.addWidget(view)
    with patch.object(Calc, 'calculate_group_result', wraps=Calc.calculate_group_result) as calculate:
        view.load_project(project)
        assert calculate.call_count == 2
        assert view.card_frame_sff.isHidden()
        view._clear_all_groups()
        assert not view.card_frame_sff.isHidden()
        assert view.secondary_table.columnCount() == 1
        assert view.group_results[0]['lambda_total'] == 100
        view._select_all_groups()
        assert calculate.call_count == 2
        assert view.secondary_table.columnCount() == 2
        assert [r['lambda_total'] for r in view.group_results] == [100, 20]
        view.refresh_validation()
        assert calculate.call_count == 2
        assert project.model_dump() == before
        unit.components[0].failure_rate = 200
        view.load_project(project)
        assert calculate.call_count == 3
        assert [r['lambda_total'] for r in view.group_results] == [200, 20]
    assert view._format_metric(None, 'fit') == 'N/A'
    assert view._format_metric(0, 'fit') == '0.0000 FIT'


def test_mapping_ui_atomic_undo_and_targeted_model_refresh(qtbot):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    unit.components[0].failure_mode_assignments[0].notes = 'Original engineering work'
    window = MainWindow(); qtbot.addWidget(window)
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.show_view('unit_editor')
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.currentWidget()
    before = unit.model_dump()
    def commit(dialog):
        dialog.staged_mappings[(bom.id, 'exida', two.id)] = two
        dialog._commit_mappings()
        return QDialog.DialogCode.Accepted
    with patch.object(ComponentMappingDialog, 'exec', commit), patch.object(tab.model, 'reload_data', side_effect=AssertionError('Full rebuild')), patch.object(Calc, 'calculate_unit', wraps=Calc.calculate_unit) as calculate:
        tab._on_component_bom_mapping()
        assert calculate.call_count == 1
    assert len(unit.components) == 2
    assert len(window.undo_stack) == 1
    assert tab.model.get_distinct_component_ids() == [c.id for c in unit.components]
    window._on_undo()
    restored = window.current_project.units[0]
    assert len(restored.component_mappings) == len(restored.components) == 1
    assert restored.components[0].failure_mode_assignments[0].notes == 'Original engineering work'
    assert restored.component_mappings[0].id == before['component_mappings'][0]['id']


def test_valid_catalog_links_and_review_resolution(qtbot):
    from fmeda_tool.ui.dialogs.component_instance_dialog import ComponentInstanceDialog
    project, unit, bom, one, two = fixture()
    project.deviations = [Deviation(id='dev', name='Deviation', description='Effect',
        deviation_type='dangerous_detected', severity='high', failure_mode='descriptive text', mitigation_ids=['mit'])]
    project.diagnostic_measures = [DiagnosticMeasure(id='dm', name='Measure', description='Check')]
    project.mitigations = [Mitigation(id='mit', name='Mitigation', description='Action', mitigation_type='diagnostic')]
    add(unit, bom, one)
    a = unit.components[0].failure_mode_assignments[0]
    a.deviation_id = 'dev'; a.diagnostic_measure_id = 'dm'; a.mitigation_id = 'mit'
    plan = Remap.plan(unit.components[0], two, bom, project=project)
    assert plan.preserved == {'deviations': 1, 'diagnostic measures': 1, 'mitigations': 1}
    assert not plan.review
    component = plan.component
    component.remapping_review_assignments = [a.model_copy(deep=True)]
    before = component.model_dump()
    dialog = ComponentInstanceDialog(component, project); qtbot.addWidget(dialog)
    dialog.retained_review_checks[0][1].setChecked(True)
    dialog.reject()
    assert component.model_dump() == before
    dialog = ComponentInstanceDialog(component, project); qtbot.addWidget(dialog)
    dialog.retained_review_checks[0][1].setChecked(True)
    dialog._on_save()
    assert not component.remapping_review_assignments
    assert component.failure_mode_assignments[0].deviation_id == 'dev'


@pytest.mark.parametrize('operation', ['remove', 'remap', 'failure'])
def test_removal_remapping_and_failure_restore_all_state(qtbot, operation):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one, two)
    unit.components[0].failure_mode_assignments[0].deviation_id = 'historical-dev'
    unit.components[0].failure_mode_assignments[0].mitigation_id = 'historical-mit'
    unit.components[0].failure_mode_assignments[0].detection_percentage = 93
    window = MainWindow(); qtbot.addWidget(window)
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.show_view('unit_editor')
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    tab = window.unit_editor_view.unit_tabs.currentWidget()
    before = unit.model_dump()
    mapping_id = unit.component_mappings[0].id
    third = two.model_copy(deep=True, update={'id': 'third', 'display_name': 'Third'})
    def commit(dialog):
        if operation == 'remove':
            dialog.removed_mapping_ids.add(mapping_id)
            dialog.staged_mappings.pop(unit.component_mappings[0].pair)
        else:
            dialog.replacements[mapping_id] = Remap.plan(unit.components[0], third, bom).component
            dialog.staged_mappings.pop(unit.component_mappings[0].pair)
            dialog.staged_mappings[(bom.id, 'exida', 'third')] = third
        dialog._commit_mappings()
        return QDialog.DialogCode.Accepted
    with patch.object(ComponentMappingDialog, 'exec', commit), patch.object(QMessageBox, 'warning'):
        if operation == 'failure':
            with patch.object(Calc, 'calculate_unit', side_effect=ValueError('Calculation failure')):
                tab._on_component_bom_mapping()
            assert unit.model_dump() == before
            assert not window.undo_stack
            return
        tab._on_component_bom_mapping()
    assert len(window.undo_stack) == 1
    assert unit.components[-1].id == before['components'][-1]['id']
    if operation == 'remove':
        assert len(unit.components) == 1
    else:
        assert unit.components[0].library_component_id == 'third'
        assert unit.components[0].failure_mode_assignments[0].deviation_id == 'historical-dev'
    window._on_undo()
    restored = window.current_project.units[0]
    assert [c.model_dump() for c in restored.components] == before['components']
    assert [m.model_dump() for m in restored.component_mappings] == before['component_mappings']


def test_missing_instance_is_repaired_without_duplicating_mapping():
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    mapping_id = unit.component_mappings[0].id
    unit.components.clear()
    add(unit, bom, one)
    assert len(unit.component_mappings) == len(unit.components) == 1
    assert unit.component_mappings[0].id == mapping_id
    assert unit.component_mappings[0].component_instance_id == unit.components[0].id


def test_visible_page_refresh_coalesces_without_rebuilding_page2(qtbot):
    project, unit, bom, one, two = fixture()
    add(unit, bom, one)
    window = MainWindow(); qtbot.addWidget(window)
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.verification_view.load_project(project)
    window.show_view('verification'); window.show()
    qtbot.wait(10)
    before_undo = deepcopy(window.undo_stack)
    before_dirty = window.has_unsaved_changes
    with patch.object(window.unit_editor_view, 'load_project', side_effect=AssertionError('Page 2 rebuilt')), patch.object(Calc, 'calculate_group_result', wraps=Calc.calculate_group_result) as calculate:
        unit.components[0].failure_rate = 123
        window.verification_view.invalidate_results(project)
        window.verification_view.invalidate_results(project)
        qtbot.waitUntil(lambda: window.verification_view.group_results[0]['lambda_total'] == 123)
        assert calculate.call_count == 1
    assert window.undo_stack == before_undo
    assert window.has_unsaved_changes == before_dirty
