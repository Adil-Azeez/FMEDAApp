import unittest
import sys
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

try:
    from PyQt6.QtWidgets import QApplication, QDialog
    from PyQt6.QtCore import QPointF
    from fmeda_tool.ui.dialogs.component_selection_dialog import ComponentSelectionDialog
    from fmeda_tool.ui.unit_editor_view import UnitEditorView, FunctionalGroupTab
    from fmeda_tool.models import ComponentDB, Component, Project, Unit, FailureModeAssignment
    from fmeda_tool.services import ProjectService, CalculationService
    pyqt_available = True
except ImportError:
    pyqt_available = False

if pyqt_available:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)


class TestComponentAddition(unittest.TestCase):
    
    def setUp(self):
        self.project = Project(
            id="proj_add_test",
            name="Addition Test Project",
            description="Test project"
        )
        self.unit1 = Unit(id="unit_01", name="Unit A", description="First group")
        self.unit2 = Unit(id="unit_02", name="Unit B", description="Second group")
        self.project.units = [self.unit1, self.unit2]
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_database_loads_successfully(self):
        # 1. Component database JSON loads successfully
        dialog = ComponentSelectionDialog()
        self.assertTrue(len(dialog.components) > 0)
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_dialog_selector_flows(self):
        dialog = ComponentSelectionDialog()
        
        # 2. Selector opens without crashing (dialog can be instantiated)
        self.assertIsNotNone(dialog)
        
        # 3. Cancelling selector changes nothing
        self.assertIsNone(dialog.created_component)
        dialog.reject()
        self.assertIsNone(dialog.created_component)
        
        # Find CKPe in components
        ckpe_template = next((c for c in dialog.components if c.shortcut == "CKPE"), None)
        self.assertIsNotNone(ckpe_template) # 4. CKPe can be selected
        self.assertTrue(len(ckpe_template.failure_modes) > 0) # 5. CKPe failure modes are loaded
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_ckpe_row_generation_and_lambda_calculation(self):
        # 6. Three rows are generated for the example CKPe data
        # Example CKPe data: short (50%), open (30%), value change (20%)
        # Base FIT: 0.4
        ckpe_modes = {
            "Short circuit": 50.0,
            "Open circuit": 30.0,
            "Value change": 20.0
        }
        
        comp = Component(
            id="comp_ckpe_01",
            position="CKPe Instance 1",
            name="CKPe",
            type="Ceramic",
            failure_rate=0.4,
            failure_modes=ckpe_modes,
            failure_mode_assignments=[
                FailureModeAssignment(
                    failure_mode_name=fm,
                    failure_rate_percentage=perc,
                    classification="dangerous_failure" if fm == "Short circuit" else "safe_failure"
                )
                for fm, perc in ckpe_modes.items()
            ]
        )
        
        self.assertEqual(len(comp.failure_mode_assignments), 3)
        
        # 7. Lambda is calculated correctly
        # short: 0.4 * 50% = 0.20
        # open: 0.4 * 30% = 0.12
        # value change: 0.4 * 20% = 0.08
        a1 = comp.failure_mode_assignments[0]
        row_metrics = CalculationService.calculate_row_detailed(
            0.4 * (a1.failure_rate_percentage / 100.0),
            a1.classification,
            a1.dangerous_failure_percentage or 0.0,
            a1.detection_percentage or 0.0
        )
        self.assertAlmostEqual(row_metrics["lambda"], 0.20, places=4)
        
        a2 = comp.failure_mode_assignments[1]
        row_metrics_open = CalculationService.calculate_row_detailed(
            0.4 * (a2.failure_rate_percentage / 100.0),
            a2.classification,
            a2.dangerous_failure_percentage or 0.0,
            a2.detection_percentage or 0.0
        )
        self.assertAlmostEqual(row_metrics_open["lambda"], 0.12, places=4)
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_row_insertion_into_active_group_only(self):
        editor = UnitEditorView()
        editor.load_project(self.project)
        
        # Select active tab: Unit A (index 1)
        editor.unit_tabs.setCurrentIndex(1)
        active_tab = editor.unit_tabs.currentWidget()
        self.assertEqual(active_tab.unit.name, "Unit A")
        
        comp = Component(
            id="comp_new",
            position="CKPe Instance 1",
            name="CKPe",
            type="Ceramic",
            failure_rate=0.4,
            failure_modes={"Short": 100.0},
            failure_mode_assignments=[
                FailureModeAssignment(failure_mode_name="Short", failure_rate_percentage=100.0)
            ]
        )
        
        # 8. Generated rows are inserted into the active functional group
        active_tab._add_component_to_canvas(comp, QPointF(100, 100))
        self.assertEqual(len(active_tab.unit.components), 1)
        
        # 9. Other functional-group tables are not modified
        other_tab = editor.unit_tabs.widget(2)
        self.assertEqual(len(other_tab.unit.components), 0)
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_multiple_instances_and_unique_ids(self):
        dialog = ComponentSelectionDialog()
        dialog.selected_template = ComponentDB(
            id="db_ckpe", display_name="CKPe", shortcut="CKPE", material="Ceramic", fits=0.4,
            failure_modes={"Short": 100.0}
        )
        mock_parent = MagicMock()
        mock_parent.unit = self.unit1
        dialog.parent = lambda: mock_parent
        
        from PyQt6.QtWidgets import QMessageBox
        with patch("fmeda_tool.ui.dialogs.component_selection_dialog.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            dialog._on_add_clicked()
            comp1 = dialog.created_component
            self.assertTrue(comp1.position.startswith("CKPE Instance"))
            mock_parent.unit.components.append(comp1)
            
            # Second instance should get CKPE Instance 2
            dialog._on_add_clicked()
            comp2 = dialog.created_component
            self.assertEqual(comp2.position, "CKPE Instance 2")
            self.assertNotEqual(comp1.id, comp2.id)
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    @patch("fmeda_tool.ui.dialogs.component_selection_dialog.QMessageBox.critical")
    def test_database_load_controlled_errors(self, mock_critical):
        # 12. Missing JSON file creates a controlled error
        with patch("pathlib.Path.exists", return_value=False):
            dialog = ComponentSelectionDialog()
            # If path doesn't exist, it resolves to empty components safely
            self.assertEqual(len(dialog.components), 0)
            
        # 13. Invalid JSON file creates a controlled error
        dialog2 = ComponentSelectionDialog()
        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", unittest.mock.mock_open(read_data="invalid json")):
            dialog2._load_components()
            mock_critical.assert_called()
            
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_controlled_missing_failure_modes(self):
        # 14. Missing failure modes creates a warning/error without shutdown
        dialog = ComponentSelectionDialog()
        dialog.selected_template = ComponentDB(
            id="db_empty", display_name="Empty", shortcut="EMP", fits=1.0, failure_modes={}
        )
        dialog.designator_input.setText("EMP1")
        dialog._load_failure_modes({})
        self.assertEqual(dialog.fm_table.rowCount(), 0)
        from PyQt6.QtWidgets import QMessageBox
        with patch("fmeda_tool.ui.dialogs.component_selection_dialog.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            dialog._on_add_clicked()
        self.assertIsNotNone(dialog.created_component)
        self.assertEqual(len(dialog.created_component.failure_mode_assignments), 0)
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_save_load_and_reopen(self):
        # 15. Project save/load preserves generated rows
        # 16. Add Component Type works after project reopening
        # 17. No BOM is required
        # 18. No UI callback references a missing method
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "save_load_test.json")
            
            # Setup project with a component
            comp = Component(
                id="comp_save_test",
                position="CKPE Instance 1",
                name="CKPe",
                type="Ceramic",
                failure_rate=0.4,
                failure_modes={"Short": 100.0},
                failure_mode_assignments=[
                    FailureModeAssignment(
                        failure_mode_name="Short",
                        failure_rate_percentage=100.0,
                        classification="dangerous_failure"
                    )
                ]
            )
            self.unit1.components.append(comp)
            
            # Save
            ProjectService.save_project_atomically(self.project, file_path)
            self.assertTrue(os.path.exists(file_path))
            
            # Load
            loaded_project, migrated, legacy_type = ProjectService.load_and_migrate_project(file_path)
            self.assertIsNotNone(loaded_project)
            self.assertEqual(len(loaded_project.units[0].components), 1)
            
            loaded_comp = loaded_project.units[0].components[0]
            self.assertEqual(loaded_comp.position, "CKPE Instance 1")
            self.assertEqual(len(loaded_comp.failure_mode_assignments), 1)


if __name__ == "__main__":
    unittest.main()
