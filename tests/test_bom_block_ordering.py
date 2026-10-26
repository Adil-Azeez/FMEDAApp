"""BOM visual blocks are read-only, model-aware, and shared with Excel."""
from unittest.mock import patch

import openpyxl
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from fmeda_tool.models import Project, Unit, BOMComponent, ComponentDB
from fmeda_tool.services.mapping_service import MappingService
from fmeda_tool.services.component_ordering import component_blocks, ordered_components
from fmeda_tool.services.calculation_service import CalculationService as Calc
from fmeda_tool.services.project_service import ProjectService
from fmeda_tool.services.export_service import ExportService
from fmeda_tool.services.import_service import ImportService
from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel, COLUMN_HEADERS
from fmeda_tool.ui.main_window import MainWindow
from fmeda_tool.ui.dialogs.bulk_assignment_dialogs import DeleteComponentsConfirmDialog


def fixture():
    boms = [BOMComponent(id=f'bom-{pos}', designator=pos, row_number=i + 7)
            for i, pos in enumerate(['C5', 'C6', 'C12', 'C13', 'C14'])]
    unit = Unit(id='u', name='Group', description='Test', bom_components=boms)
    project = Project(id='p', name='Grouping', description='Test', units=[unit])
    ct = ComponentDB(id='CT', display_name='CT', source_type='exida', fits=100,
                     failure_modes={'Change in Value': 30, 'Open Circuit': 30, 'Short Circuit': 40})
    cel = ComponentDB(id='CEL', display_name='CEL', source_type='exida', fits=20,
                     failure_modes={'Change in Value': 20, 'Increased Leakage': 20,
                                    'Open Circuit': 30, 'Short Circuit': 30})
    return project, unit, ct, cel


def add(unit, position, template):
    bom = next(b for b in unit.bom_components if b.designator == position)
    proposed = MappingService.prepare_batch(unit, [(bom.id, template)])
    return MappingService.commit_batch(unit, proposed)


def model_components(model):
    seen = []
    for entry in model.rows:
        if not entry.is_separator and (not seen or seen[-1] is not entry.component):
            seen.append(entry.component)
    return seen


def test_incremental_mapping_order_grouping_and_no_recalculation_of_unchanged_rows(qapp):
    p, unit, ct, cel = fixture()
    for pos in ['C14', 'C12', 'C13']:
        add(unit, pos, ct)
    model = FmedaTableModel(unit, p)
    assert [c.position for c in model_components(model)] == ['C12', 'C13', 'C14']
    for pos in ['C6', 'C5']:
        changed = add(unit, pos, ct)
        with patch.object(model, '_compute_entry_metrics', wraps=model._compute_entry_metrics) as compute:
            model.sync_components(changed)
            assert compute.call_count == 3
    changed = add(unit, 'C12', cel)
    model.sync_components(changed)
    assert [(c.position, c.name) for c in model_components(model)] == [
        ('C5', 'CT'), ('C6', 'CT'), ('C12', 'CT'), ('C12', 'CEL'), ('C13', 'CT'), ('C14', 'CT')]
    c12_rows = [i for i, e in enumerate(model.rows) if e.component and e.component.position == 'C12']
    assert len(c12_rows) == 7
    assert c12_rows == list(range(c12_rows[0], c12_rows[-1] + 1))
    assert model.rows[c12_rows[-1] + 1].is_separator
    assert sum(e.is_separator for e in model.rows) == 4
    before = p.model_dump()
    with patch.object(Calc, 'calculate_assignment', side_effect=AssertionError('Display reorder calculated')):
        model.sync_components(set())
        assert len(component_blocks(unit)) == 5
    assert p.model_dump() == before
    assert len(unit.components) == len(unit.component_mappings) == 6
    assert Calc.calculate_group_result(unit, p)['lambda_total'] == 520


def test_stable_bom_identity_and_import_sequence_override_positions(qapp):
    p, unit, ct, cel = fixture()
    add(unit, 'C12', ct); add(unit, 'C14', ct); add(unit, 'C12', cel)
    first = unit.components[0]
    first.position = 'different label'  # Mapping identity, not a display label, binds the record.
    unit.bom_components = [unit.bom_components[4], *unit.bom_components[:4]]
    before = p.model_dump()
    assert [c.id for c in ordered_components(unit)] == [unit.components[1].id, first.id, unit.components[2].id]
    assert [c.id for c in model_components(FmedaTableModel(unit, p))] == [c.id for c in ordered_components(unit)]
    assert p.model_dump() == before


def test_legacy_bom_order_natural_unlinked_order_and_roundtrip(qapp, tmp_path):
    p, unit, ct, cel = fixture()
    add(unit, 'C12', ct); add(unit, 'C13', ct); add(unit, 'C12', cel)
    for bom in unit.bom_components:
        bom.row_number = None
    for pos in ['R14', 'R5', 'R12', 'R6', 'R13']:
        clone = unit.components[0].model_copy(deep=True, update={'id': pos, 'position': pos})
        unit.components.insert(0, clone)
    before = p.model_dump()
    expected = ['C12', 'C12', 'C13', 'R5', 'R6', 'R12', 'R13', 'R14']
    assert [c.position for c in ordered_components(unit)] == expected
    assert p.model_dump() == before
    path = tmp_path / 'grouped.json'
    ProjectService.save_project_atomically(p, str(path))
    saved = path.read_bytes()
    loaded, _, _ = ProjectService.load_and_migrate_project(str(path))
    assert path.read_bytes() == saved
    assert [c.position for c in model_components(FmedaTableModel(loaded.units[0], loaded))] == expected
    assert [m.model_dump() for m in loaded.units[0].component_mappings] == before['units'][0]['component_mappings']
    assert Calc.calculate_group_result(loaded.units[0], loaded) == Calc.calculate_group_result(unit, p)


def test_reimported_sequence_reorders_existing_blocks_without_changing_models(qapp):
    p, unit, ct, cel = fixture()
    add(unit, 'C12', ct); add(unit, 'C14', ct); add(unit, 'C12', cel)
    model = FmedaTableModel(unit, p)
    txt = 'Pos  MN        Benennung    Wert    Beschreibung    Lage\nC14  000014    CAP          10n     Capacitor        TOP\nC12  000012    CAP          10n     Capacitor        TOP\n'
    records, errors, _ = ImportService.parse_bom_txt(txt)
    assert not errors
    assert [b.designator for b in records] == ['C14', 'C12']
    # Reconciliation retains existing stable IDs while replacing the imported sequence.
    ids = {b.designator: b.id for b in unit.bom_components}
    for bom in records:
        bom.id = ids[bom.designator]
    components = [c.model_dump() for c in unit.components]
    unit.bom_components = records
    with patch.object(Calc, 'calculate_assignment', side_effect=AssertionError('Order-only refresh calculated')):
        model.sync_components(set())
    assert [c.position for c in model_components(model)] == ['C14', 'C12', 'C12']
    assert [c.model_dump() for c in unit.components] == components


@pytest.mark.parametrize('per_group', [True, False])
def test_excel_grouping_and_order_match_application(qapp, tmp_path, per_group):
    p, unit, ct, cel = fixture()
    for pos in ['C14', 'C12', 'C13', 'C6', 'C5']:
        add(unit, pos, ct)
    add(unit, 'C12', cel)
    for c in unit.components:
        for a in c.failure_mode_assignments:
            a.notes = c.id + ':' + a.failure_mode_name
    before = p.model_dump()
    path = tmp_path / 'ordered.xlsx'
    assert ExportService.export_to_excel(p, str(path), fmeda_per_fg=per_group)
    workbook = openpyxl.load_workbook(path)
    sheet = workbook['Group' if per_group else 'FMEDA Workspace']
    rows = list(sheet.values)
    position = rows[0].index('Component ID / Designator')
    name = rows[0].index('Display Name / Component Type')
    note = rows[0].index('Comments / Justification')
    model = FmedaTableModel(unit, p)
    expected = [(e.component.position, e.component.type, e.assignment.notes)
                for e in model.rows if not e.is_separator]
    assert [(r[position], r[name], r[note]) for r in rows[1:]] == expected
    assert len(rows) - 1 == 19
    assert [row[3] for row in list(workbook['Component Mappings'].values)[1:]] == [
        'C5', 'C6', 'C12', 'C12', 'C13', 'C14']
    assert p.model_dump() == before
    assert Calc.calculate_group_result(unit, p)['lambda_total'] == 520
    workbook.close()


def test_search_selection_edit_delete_undo_and_confirm_are_model_aware(qtbot):
    p, unit, ct, cel = fixture()
    add(unit, 'C12', ct); add(unit, 'C13', ct); add(unit, 'C12', cel)
    window = MainWindow(); qtbot.addWidget(window)
    window.current_project = p
    window.unit_editor_view.load_project(p)
    window.show_view('unit_editor')
    window.unit_editor_view.unit_tabs.setCurrentIndex(1)
    window.show()
    tab = window.unit_editor_view.unit_tabs.currentWidget()
    original = unit.components[0].model_dump()
    cel_component = unit.components[2]
    tab.search_bar.search_input.setText('CEL')
    visible = [e for i, e in enumerate(tab.model.rows) if not tab.table.isRowHidden(i)]
    assert len(visible) == 4
    assert {e.component.id for e in visible} == {cel_component.id}
    assert {tab.model.data(tab.model.index(i, 0)) for i in tab.search_bar.matches} == {'C12'}
    tab.search_bar.search_input.clear()
    tab.enable_editing()
    row = tab.model.get_row_indices_for_component(cel_component.id)[0]
    tab.table.scrollTo(tab.model.index(row, 0))
    qtbot.mouseClick(tab.table.viewport(), Qt.MouseButton.LeftButton,
                     pos=tab.table.visualRect(tab.model.index(row, 0)).center())
    assert tab.table.selected_component_ids == {cel_component.id}
    assert tab.model.setData(tab.model.index(row, COLUMN_HEADERS.index('Comments / Justification')), 'CEL only')
    assert unit.components[0].model_dump() == original
    tab.confirm_changes()
    assert [(c.position, c.name) for c in model_components(tab.model)] == [('C12', 'CT'), ('C12', 'CEL'), ('C13', 'CT')]
    tab.enable_editing()
    tab.table.selected_component_ids = {cel_component.id}
    with patch.object(DeleteComponentsConfirmDialog, 'exec', return_value=QDialog.DialogCode.Accepted):
        assert tab.delete_selected_components()
    assert len(unit.component_mappings) == 2
    assert unit.components[0].model_dump() == original
    window._on_undo()
    restored = window.current_project.units[0]
    assert [c.name for c in ordered_components(restored)] == ['CT', 'CEL', 'CT']
    assert len(restored.component_mappings) == 3
    assert next(c for c in restored.components if c.id == cel_component.id).failure_mode_assignments[0].notes == 'CEL only'


def test_remap_keeps_the_same_subgroup_and_engineering_assignments(qapp):
    from fmeda_tool.services.component_remapping_service import ComponentRemappingService
    p, unit, ct, cel = fixture()
    add(unit, 'C12', ct); add(unit, 'C14', ct); add(unit, 'C12', cel)
    model = FmedaTableModel(unit, p)
    original = unit.components[0].model_dump()
    selected = unit.components[2]
    selected.failure_mode_assignments[0].notes = 'CEL engineering work'
    mapping = next(m for m in unit.component_mappings if m.component_instance_id == selected.id)
    replacement = cel.model_copy(deep=True, update={'id': 'CEL2', 'display_name': 'CEL2', 'fits': 25})
    bom = next(b for b in unit.bom_components if b.id == mapping.bom_component_id)
    proposed = ComponentRemappingService.plan(selected, replacement, bom).component
    changed = MappingService.commit_batch(unit, MappingService.prepare_batch(unit, replacements={mapping.id: proposed}))
    model.sync_components(changed)
    assert [c.name for c in model_components(model)] == ['CT', 'CEL2', 'CT']
    assert unit.components[0].model_dump() == original
    assert proposed.id == selected.id
    assert proposed.failure_mode_assignments[0].notes == 'CEL engineering work'
    assert sum(e.is_separator for e in model.rows) == 1
    assert Calc.calculate_group_result(unit, p)['lambda_total'] == 225


def test_same_position_text_does_not_merge_distinct_bom_record_ids(qapp):
    p, unit, ct, cel = fixture()
    add(unit, 'C12', ct)
    second = BOMComponent(id='different-physical-record', designator='C12')
    unit.bom_components.append(second)
    MappingService.commit_batch(unit, MappingService.prepare_batch(unit, [(second.id, cel)]))
    blocks = component_blocks(unit)
    assert [block.key for block in blocks] == [('bom', 'bom-C12'), ('bom', second.id)]
    assert sum(e.is_separator for e in FmedaTableModel(unit, p).rows) == 1
