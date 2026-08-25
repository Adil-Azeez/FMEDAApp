import unittest
import sys
import os
import tempfile
import json
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QMessageBox
from fmeda_tool.models import Project, ProjectStatus, SafetyStandard, SafetyContext, DiagnosticMeasure, Unit, Component, FailureModeAssignment
from fmeda_tool.ui.create_project_view import CreateProjectView
from fmeda_tool.ui.unit_editor_view import UnitEditorView, ProjectOverviewTab, DiagnosticMeasureManagerDialog, DiagnosticMeasureMiniDialog
from fmeda_tool.ui.export_view import ExportView
from fmeda_tool.ui.main_window import MainWindow
from fmeda_tool.services.export_service import ExportService
from fmeda_tool.services.project_service import ProjectService
from fmeda_tool.services.calculation_service import CalculationService

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestIncrement6(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Project(
            id="proj_test_inc6",
            name="Inc6 Project",
            description="Testing Increment 6 implementation",
            status=ProjectStatus.DRAFT,
            safety_standard=SafetyStandard.IEC_61508,
            target_sil="SIL 2",
            safety_context=SafetyContext(
                safety_function_name="Overpressure Protection",
                safety_function_description="Protects pipeline from overpressure",
                safe_state="Valves closed",
                dangerous_state="Valves open during pressure peak",
                no_part_failure_definition="Definition for No Part...",
                no_effect_failure_definition="Definition for No Effect...",
                safety_architecture="1oo1",
                operating_mode="Low demand mode",
                safety_boundary="Sensor to valve solenoid",
                external_sensor_included=True
            ),
            reliability_database_source="IEC 62380",
            environmental_profile="Ground Benign"
        )
        
    def tearDown(self):
        self.temp_dir.cleanup()
        
    def test_safety_context_multiline_fields(self):
        # 1. Multiline text support
        sc = SafetyContext(
            safety_function_name="Name",
            no_part_failure_definition="Line 1\nLine 2\nLine 3",
            no_effect_failure_definition="Line A\nLine B\nLine C"
        )
        self.assertEqual(sc.no_part_failure_definition, "Line 1\nLine 2\nLine 3")
        self.assertEqual(sc.no_effect_failure_definition, "Line A\nLine B\nLine C")
        
        # 2. Save and reopen preserves exact text
        self.project.safety_context = sc
        temp_filepath = os.path.join(self.temp_dir.name, "test_project.json")
        ProjectService.save_project_atomically(self.project, temp_filepath)
        
        loaded_project, _, _ = ProjectService.load_and_migrate_project(temp_filepath)
        loaded_sc = loaded_project.safety_context
        self.assertEqual(loaded_sc.no_part_failure_definition, "Line 1\nLine 2\nLine 3")
        self.assertEqual(loaded_sc.no_effect_failure_definition, "Line A\nLine B\nLine C")
        
    def test_legacy_project_compatibility(self):
        # 1. Old project without new definitions loads successfully
        legacy_json = {
            "id": "proj_legacy",
            "name": "Legacy Project",
            "description": "Legacy description",
            "status": "draft",
            "safety_context": {
                "safety_function_name": "Test Function",
                "safe_state": "Trip"
            }
        }
        temp_filepath = os.path.join(self.temp_dir.name, "legacy_project.json")
        with open(temp_filepath, "w", encoding="utf-8") as f:
            json.dump(legacy_json, f)
            
        loaded, _, _ = ProjectService.load_and_migrate_project(temp_filepath)
        self.assertIsNone(loaded.safety_context.no_part_failure_definition)
        self.assertIsNone(loaded.safety_context.no_effect_failure_definition)
        
        # 2. Old project with legacy external_actuator_included loads and ignores it
        legacy_actuator_json = {
            "id": "proj_legacy_actuator",
            "name": "Legacy Project Actuator",
            "description": "Legacy description",
            "status": "draft",
            "safety_context": {
                "safety_function_name": "Test Function",
                "safe_state": "Trip",
                "external_actuator_included": True
            }
        }
        temp_filepath_act = os.path.join(self.temp_dir.name, "legacy_project_actuator.json")
        with open(temp_filepath_act, "w", encoding="utf-8") as f:
            json.dump(legacy_actuator_json, f)
            
        loaded_act, _, _ = ProjectService.load_and_migrate_project(temp_filepath_act)
        # Should load without crash
        self.assertEqual(loaded_act.name, "Legacy Project Actuator")
        # Field should be ignored in model
        self.assertFalse(hasattr(loaded_act.safety_context, "external_actuator_included"))
        
    def test_create_project_view_ui_structure(self):
        # 1. Check UI creation
        view = CreateProjectView()
        self.assertTrue(hasattr(view, "no_part_failure_def"))
        self.assertTrue(hasattr(view, "no_effect_failure_def"))
        # External Actuator Included is absent
        self.assertFalse(hasattr(view, "actuator_included"))
        
        # 2. Empty fields do not block validation
        view.reset_form()
        view.name_input.setText("Test Project Validation")
        view.number_input.setText("VALID-001")
        view.description_input.setPlainText("Valid description")
        view.no_part_failure_def.setPlainText("")
        view.no_effect_failure_def.setPlainText("")
        self.assertTrue(view._validate_page())
        
    def test_overview_dashboard_rendering(self):
        tab = ProjectOverviewTab(None)
        tab.refresh(self.project)
        # Verify definitions are loaded
        # Since it is a grid layout, let's verify no crashes occur during refresh
        self.assertEqual(tab.project.name, "Inc6 Project")
        
    def test_pdf_export_service(self):
        temp_pdf = os.path.join(self.temp_dir.name, "test_report.pdf")
        # 1. Export call runs without crash
        success = ExportService.export_to_pdf(self.project, temp_pdf)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(temp_pdf))
        self.assertTrue(os.path.getsize(temp_pdf) > 0)
        
        # 2. HTML special characters escape test
        self.project.safety_context.no_part_failure_definition = "<b>Bold Text</b> & <script>alert(1)</script>"
        success_esc = ExportService.export_to_pdf(self.project, temp_pdf)
        self.assertTrue(success_esc)
        
    def test_excel_export_service(self):
        temp_xlsx = os.path.join(self.temp_dir.name, "test_workbook.xlsx")
        success = ExportService.export_to_excel(self.project, temp_xlsx)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(temp_xlsx))
        self.assertTrue(os.path.getsize(temp_xlsx) > 0)
        
    def test_diagnostic_measure_notes(self):
        # 1. Notes field support
        dm_with_notes = DiagnosticMeasure(
            id="dm_inc6_01",
            dc=99.0,
            description="Diagnostic Measure with Notes",
            notes="Optional engineering notes here"
        )
        self.assertEqual(dm_with_notes.notes, "Optional engineering notes here")
        
        dm_without_notes = DiagnosticMeasure(
            id="dm_inc6_02",
            dc=90.0,
            description="Diagnostic Measure without Notes"
        )
        self.assertIsNone(dm_without_notes.notes)
        
        # 2. Safe notes cell access test
        self.assertEqual(getattr(dm_without_notes, "notes", None) or "", "")
        self.assertEqual(getattr(dm_with_notes, "notes", None) or "", "Optional engineering notes here")
        
    def test_diagnostic_measure_deletion_warning(self):
        # Create a project with a diagnostic measure
        dm = DiagnosticMeasure(id="dm_to_del", dc=90.0, description="Delete Me")
        self.project.diagnostic_measures.append(dm)
        
        # Assign it to a failure mode
        assignment = FailureModeAssignment(
            failure_mode_name="Short",
            failure_rate_percentage=100.0,
            diagnostic_measure_id="dm_to_del",
            detection_percentage=90.0
        )
        component = Component(
            id="comp_inc6",
            position="R1",
            name="Resistor",
            type="Resistor",
            failure_rate=10.0,
            failure_modes={"Short": 100.0},
            failure_mode_assignments=[assignment]
        )
        unit = Unit(id="unit_inc6", name="FG1", description="FG1 desc", components=[component])
        self.project.units.append(unit)
        
        # Verify assignment is active
        self.assertEqual(assignment.diagnostic_measure_id, "dm_to_del")
        
        # Detect assigned measures manually (same logic as deletion check)
        assigned_locations = []
        for u in self.project.units:
            for comp in u.components:
                for a in comp.failure_mode_assignments:
                    if a.diagnostic_measure_id == dm.id:
                        assigned_locations.append((u, comp, a))
                        
        self.assertEqual(len(assigned_locations), 1)
        
        # Clear assignments (simulate deletion confirm)
        for u, comp, a in assigned_locations:
            a.diagnostic_measure_id = None
            
        self.assertIsNone(assignment.diagnostic_measure_id)
        
    def test_regression_hiding_controls(self):
        # Verify that DC Test Ref remains commented out or not active in row validation
        assignment = FailureModeAssignment(
            failure_mode_name="Open",
            failure_rate_percentage=100.0,
            diagnostic_measure_id="dm_some",
            detection_percentage=90.0,
            classification="dangerous_failure",
            deviation_id="dev_some",
            notes="Some notes",
            dangerous_failure_percentage=100.0
        )
        component = Component(
            id="comp_reg",
            position="R2",
            name="Resistor",
            type="Resistor",
            failure_rate=10.0,
            failure_modes={"Open": 100.0},
            failure_mode_assignments=[assignment]
        )
        
        from fmeda_tool.services.validation_service import ValidationService
        status, msgs = ValidationService.validate_row(assignment, component)
        # Validation should succeed without warnings/errors about missing dc_test_ref
        self.assertEqual(status, "valid")


if __name__ == "__main__":
    unittest.main()
