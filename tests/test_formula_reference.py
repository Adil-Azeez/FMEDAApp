"""Navigation, read-only behavior, native layout and formula traceability."""
import ast
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import inspect
import textwrap
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QDialog, QPlainTextEdit

from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.ui.formula_reference_view import FormulaReferenceView, FORMULA_SECTIONS
from fmeda_tool.ui.main_window import MainWindow


# Documentation review gate, not a second implementation of the formulas.
# Ignore formatting/comments/docstrings; if calculation code changes, review the
# corresponding reference entries against that code before updating these hashes.
DOCUMENTED_IMPLEMENTATIONS = {
    'calculate_row_detailed': '1ab5f625ca7902c5d25558a43487e99ab14cc68a38d5d5dc9199e9d47ce7c1cb',
    'calculate_assignment': '3a12716a05abcaca3541ede24cb0e2761767a69d13e61868e683ea3ebeed7817',
    'calculate_component': '3e9936386d93cfc279b6e80024a09ccec215d872ca89bd38979a2c83fcadf173',
    'calculate_diagnostic_lambda': 'f0abd443436dbb1b2ba5aa3a8713abef1192651b489a280703eee907a225113e',
    'calculate_unit': 'dbe9c7f05a3781e54ba4abcabff338daa5cf8d972d22b99134b587754150982e',
    'calculate_scope': '098c4f9af6789c16b71ef90caf7d32814032eb815088bcfc7fa108c61fd07c46',
    'calculate_unit_metrics': 'c7d349ed8e3c71b20f74ee19906a5408b5c32f2f258197edf2ece366b2df47a6',
    'calculate_group_result': '75da8a8b9a45150859874dbfffac11d6b5e4c9843b1e8474a6ec9df93eff2651',
}


@pytest.mark.parametrize('method_name, expected', DOCUMENTED_IMPLEMENTATIONS.items())
def test_formula_documentation_matches_reviewed_calculation_code(method_name, expected):
    node = ast.parse(textwrap.dedent(inspect.getsource(getattr(CalculationService, method_name)))).body[0]
    if ast.get_docstring(node):
        node.body.pop(0)
    actual = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
    assert actual == expected, f'Review Formula Reference against changed CalculationService.{method_name}'


def project_fixture():
    assignment = FailureModeAssignment(failure_mode_name='Open', failure_rate_percentage=100,
                                      dangerous_failure_percentage=60, detection_percentage=80,
                                      diagnostic_function='Yes', notes='Preserve this note')
    component = Component(id='c', name='Resistor', type='Resistor', position='R1', failure_rate=100,
                          failure_modes={'Open': 100}, failure_mode_assignments=[assignment])
    return Project(id='p', name='Formula test', description='Reference navigation',
                   units=[Unit(id='u', name='Group', description='Test', components=[component])])


@pytest.mark.parametrize('edit_mode', [False, True])
def test_navigation_is_read_only_and_preserves_workspace(qtbot, edit_mode):
    window = MainWindow()
    qtbot.addWidget(window)
    project = project_fixture()
    window.current_project = project
    window.unit_editor_view.load_project(project)
    window.verification_view.load_project(project)
    window.show_view('unit_editor')
    editor = window.unit_editor_view
    editor.unit_tabs.setCurrentIndex(1)
    tab = editor.unit_tabs.currentWidget()
    if edit_mode:
        tab.enable_editing()
    tab.search_bar.search_input.setText('Open')
    window.undo_stack.append({'sentinel': 'existing undo entry'})
    before = project.model_dump_json()
    undo = deepcopy(window.undo_stack)
    dirty = window.has_unsaved_changes
    history = list(window.navigation_history)
    verification = window.verification_view.card_val_sff.text()
    with ExitStack() as stack:
        for service in (CalculationService, ValidationService):
            for name, value in vars(service).items():
                if isinstance(value, staticmethod):
                    stack.enter_context(patch.object(service, name, side_effect=AssertionError(f'Unexpected {name}')))
        stack.enter_context(qtbot.assertNotEmitted(editor.project_changed))
        for _ in range(2):
            editor.formulas_btn.click()
            qtbot.waitUntil(lambda: isinstance(window.get_current_view(), FormulaReferenceView))
            window.get_current_view().back_btn.click()
            qtbot.waitUntil(lambda: window.get_current_view() is editor)
        editor.formulas_btn.click()
        window.back_action.trigger()  # Existing navigation shortcut also works.
    assert window.get_current_view() is editor
    assert window.navigation_history == history
    assert editor.unit_tabs.currentWidget() is tab
    assert tab.is_in_edit_mode == edit_mode
    assert tab.model.is_edit_mode == edit_mode
    assert tab.search_bar.search_input.text() == 'Open'
    assert project.model_dump_json() == before
    assert window.undo_stack == undo
    assert window.has_unsaved_changes == dirty
    assert window.verification_view.card_val_sff.text() == verification


def test_reference_contains_all_implemented_metrics_and_source_links(qtbot):
    page = FormulaReferenceView()
    qtbot.addWidget(page)
    text = page.browser.toPlainText()
    assert [section for section, _ in FORMULA_SECTIONS] == [
        'Failure Rates', 'Classification Buckets', 'Safety Channel', 'Diagnostic Metrics', 'Safety Metrics', 'Reliability Metrics']
    expected = {'lambda_total', 'lambda_safe', 'lambda_dangerous', 'lambda_sd', 'lambda_su',
                'lambda_dd', 'lambda_du', 'lambda_diag_gesamt', 'sff', 'dc', 'mttfd', 'pfd_avg',
                'pfhd', 'mtbf', 'proof_coverage', 'sil', 'lambda_row', 'units',
                'lambda_no_part', 'lambda_no_effect', 'lambda_diag_failure', 'legacy_classification'}
    assert {f.key for _, formulas in FORMULA_SECTIONS for f in formulas} == expected
    for section, formulas in FORMULA_SECTIONS:
        assert section in text
        for formula in formulas:
            assert formula.name in text
            assert formula.expression and formula.explanation and formula.methods
            assert set(formula.methods) <= DOCUMENTED_IMPLEMENTATIONS.keys()
    assert page.browser.isReadOnly()
    assert not page.browser.openExternalLinks()
    assert '1oo2' in text and '2oo2' in text and '1oo1D' in text
    assert 'MTTFdsafety' in text and 'MTTFdrow' in text
    assert '<img' not in page.browser.toHtml()


@pytest.mark.parametrize('width', [640, 960, 1440, 1920])
def test_rich_text_wraps_without_horizontal_clipping(qtbot, width):
    page = FormulaReferenceView()
    qtbot.addWidget(page)
    page.resize(width, 700)
    page.show()
    qtbot.waitUntil(lambda: page.browser.document().size().height() > 700)
    browser = page.browser
    assert browser.horizontalScrollBar().maximum() == 0
    assert browser.document().size().width() <= browser.viewport().width()
    block = browser.document().begin()
    while block.isValid():
        layout = block.layout()
        for i in range(layout.lineCount()):
            line = layout.lineAt(i)
            assert line.naturalTextWidth() <= line.width() + 1
        block = block.next()


def test_implementation_links_show_actual_read_only_source(qtbot):
    page = FormulaReferenceView()
    qtbot.addWidget(page)
    shown = []

    def inspect_dialog(dialog):
        source = dialog.findChild(QPlainTextEdit)
        assert source.isReadOnly()
        shown.append(source.toPlainText())
        return QDialog.DialogCode.Rejected

    with patch.object(QDialog, 'exec', inspect_dialog):
        page.browser.anchorClicked.emit(QUrl('source:calculate_scope'))
        page.browser.anchorClicked.emit(QUrl('https://example.com'))
    assert shown == [inspect.getsource(CalculationService.calculate_scope)]
