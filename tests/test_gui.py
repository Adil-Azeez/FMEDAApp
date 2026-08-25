import unittest
import sys

try:
    from PyQt6.QtWidgets import QApplication
    from fmeda_tool.ui.unit_table_view import UnitTableView
    from fmeda_tool.ui.unit_editor_view import UnitEditorView, ProjectOverviewTab, FunctionalGroupTab
    from fmeda_tool.ui.create_project_view import CreateProjectView
    pyqt_available = True
except ImportError:
    pyqt_available = False

from fmeda_tool.models import Unit, Project, Component, FailureModeAssignment, Deviation, DeviationType, DeviationSeverity

if pyqt_available:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)


class TestGUIComponents(unittest.TestCase):
    
    def setUp(self):
        # Create a mock project
        self.project = Project(
            id="proj_test_02",
            name="Mock Project",
            description="Mock Project for UI testing",
            deviations=[
                Deviation(
                    id="dev_001",
                    name="Voltage Collapse",
                    description="Mock description",
                    deviation_type=DeviationType.DANGEROUS_DETECTED,
                    severity=DeviationSeverity.HIGH,
                    failure_mode="Short"
                )
            ]
        )
        
        # Create a unit with components and assignments
        self.unit = Unit(
            id="unit_test_02",
            name="ADC Unit",
            description="Mock ADC Unit",
            components=[
                Component(
                    id="comp_001",
                    position="C101",
                    name="Filter Cap",
                    type="Capacitor",
                    failure_rate=0.4,
                    failure_modes={"Short": 100.0},
                    failure_mode_assignments=[
                        FailureModeAssignment(
                            failure_mode_name="Short",
                            failure_rate_percentage=100.0,
                            deviation_id="dev_001"
                        )
                    ]
                )
            ]
        )
        self.project.units.append(self.unit)

    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_unit_table_view_resolves_deviation_name(self):
        # Instantiate table view with the mock unit and project
        table_view = UnitTableView(self.unit, self.project)
        
        # Verify that row 0, column 7 (Deviation column) is set to "Voltage Collapse" instead of "dev_001"
        item = table_view.table.item(0, 7)
        self.assertIsNotNone(item)
        self.assertEqual(item.text(), "Voltage Collapse")
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_unit_editor_view_has_new_buttons(self):
        # Instantiate editor view
        editor_view = UnitEditorView()
        
        # Verify buttons exist
        self.assertIsNotNone(editor_view.add_comp_btn)
        self.assertIsNotNone(editor_view.config_comp_btn)
        
        # Verify initial state is disabled
        self.assertFalse(editor_view.add_comp_btn.isEnabled())
        self.assertFalse(editor_view.config_comp_btn.isEnabled())
        
        # Load project and verify they are enabled
        editor_view.load_project(self.project)
        self.assertTrue(editor_view.add_comp_btn.isEnabled())
        self.assertTrue(editor_view.config_comp_btn.isEnabled())

    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_create_project_wizard_flow(self):
        # Instantiate form view
        view = CreateProjectView()
        
        # Connect signal to capture saved project
        saved_project = []
        view.project_saved.connect(lambda p: saved_project.append(p))
        
        # Populate required fields
        view.name_input.setText("Test Project")
        view.number_input.setText("PRJ-100")
        view.description_input.setPlainText("Test Project Description")
        view.version_input.setText("1.0.0")
        view.mission_time_input.setValue(87600)
        view.test_interval_input.setValue(8760)
        
        # Populate optional fields
        view.safety_fn_name.setText("Shut down reactor")
        view.safe_state.setText("Valve open")
        view.dangerous_state.setText("Valve closed")
        view.rel_db_source.setText("SN29500")
        view.env_profile.setText("GB")
        
        # Save project
        view._on_next()
        
        # Assertions
        self.assertEqual(len(saved_project), 1)
        project = saved_project[0]
        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.project_number, "PRJ-100")
        self.assertEqual(project.description, "Test Project Description")
        self.assertEqual(project.mission_time, 87600)
        self.assertEqual(project.test_interval, 8760)
        self.assertEqual(project.safety_context.safety_function_name, "Shut down reactor")
        self.assertEqual(project.safety_context.safe_state, "Valve open")
        self.assertEqual(project.safety_context.dangerous_state, "Valve closed")
        self.assertEqual(project.reliability_database_source, "SN29500")
        self.assertEqual(project.environmental_profile, "GB")

    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_workspace_tabs_and_overview(self):
        # Instantiate editor view (Project Workspace)
        editor_view = UnitEditorView()
        
        # Load the mock project
        editor_view.load_project(self.project)
        
        # Tab 0 should be Project Overview
        self.assertEqual(editor_view.unit_tabs.tabText(0), "Project Overview")
        overview_widget = editor_view.unit_tabs.widget(0)
        self.assertIsInstance(overview_widget, ProjectOverviewTab)
        
        # Tab 1 should be the mock unit ADC Unit
        self.assertEqual(editor_view.unit_tabs.tabText(1), "ADC Unit")
        fg_widget = editor_view.unit_tabs.widget(1)
        self.assertIsInstance(fg_widget, FunctionalGroupTab)
        
        # Verify functional group tab has the save button (toggle view is hidden)
        # self.assertIsNotNone(fg_widget.toggle_view_btn)
        self.assertIsNotNone(fg_widget.save_btn)

    def test_validation_service_rules(self):
        from fmeda_tool.services.validation_service import ValidationService
        
        # Test 1: Assignment with no deviation should return warning
        assignment = FailureModeAssignment(
            failure_mode_name="Short",
            failure_rate_percentage=100.0
        )
        status, msgs = ValidationService.validate_row(assignment, self.unit.components[0])
        self.assertEqual(status, "warning")
        self.assertIn("Missing deviation assignment.", msgs)
        
        # Test 2: Assignment with invalid dangerous percentage should return error
        assignment.dangerous_failure_percentage = 150.0  # invalid > 100
        status, msgs = ValidationService.validate_row(assignment, self.unit.components[0])
        self.assertEqual(status, "error")
        self.assertTrue(any("out of bounds" in m for m in msgs))


if __name__ == "__main__":
    unittest.main()
