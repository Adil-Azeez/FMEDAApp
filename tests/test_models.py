import unittest
from datetime import datetime
from pydantic import ValidationError
from fmeda_tool.models import Project, ProjectStatus, SafetyStandard, DiagnosticMeasure, ComponentDB, Unit, Component


class TestModels(unittest.TestCase):
    
    def test_diagnostic_measure_model(self):
        # Valid creation
        dm = DiagnosticMeasure(
            id="dm_test_01",
            dc=95.5,
            description="Test diagnostic measure description"
        )
        self.assertEqual(dm.id, "dm_test_01")
        self.assertEqual(dm.dc, 95.5)
        self.assertEqual(dm.description, "Test diagnostic measure description")
        
        # Test validation limits
        with self.assertRaises(ValidationError):
            DiagnosticMeasure(id="dm_err", dc=105.0, description="Too high")
        with self.assertRaises(ValidationError):
            DiagnosticMeasure(id="dm_err", dc=-1.0, description="Too low")

    def test_component_db_model(self):
        comp = ComponentDB(
            id="compdb_001",
            display_name="Resistor 10k",
            shortcut="R10K",
            fits=0.2,
            failure_modes={"Short": 20.0, "Open": 80.0}
        )
        self.assertEqual(comp.id, "compdb_001")
        self.assertEqual(comp.fits, 0.2)
        self.assertEqual(comp.failure_modes["Short"], 20.0)

    def test_project_model(self):
        project = Project(
            id="proj_test_01",
            name="Test Project",
            description="Testing project model creation",
            status=ProjectStatus.DRAFT,
            safety_standard=SafetyStandard.IEC_61508,
            target_sil="SIL 2"
        )
        self.assertEqual(project.id, "proj_test_01")
        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.status, ProjectStatus.DRAFT)


if __name__ == "__main__":
    unittest.main()
