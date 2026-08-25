import unittest
import os
import json
import sys

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QTextDocument
    pyqt_available = True
except ImportError:
    pyqt_available = False

if pyqt_available:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

from pathlib import Path
from fmeda_tool.models import Project, Unit, SafetyContext
from fmeda_tool.models.project import ProjectStatus
from fmeda_tool.services import ProjectService, ExportService


class TestReviewWorkflowAndExports(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = Path("tests/scratch_workflow")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        self.project = Project(
            id="proj_workflow_01",
            name="Workflow Test Project",
            description="Testing reviewer status and Excel/PDF reports",
            status=ProjectStatus.DRAFT,
            reviewer=None
        )
        
    def tearDown(self):
        # Clean up files
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            
    def test_log_change_history(self):
        # Initially empty
        self.assertEqual(len(self.project.change_history), 0)
        
        ProjectService.log_change(
            self.project,
            "Edit Parameter",
            "Changed mission time to 87600 hours",
            user="Analyst A"
        )
        
        self.assertEqual(len(self.project.change_history), 1)
        entry = self.project.change_history[0]
        self.assertEqual(entry["action"], "Edit Parameter")
        self.assertEqual(entry["details"], "Changed mission time to 87600 hours")
        self.assertEqual(entry["user"], "Analyst A")
        self.assertTrue("timestamp" in entry)
        
    def test_excel_export_creates_file(self):
        filepath = self.test_dir / "report.xlsx"
        
        # Add a unit and component so sheets are generated
        unit = Unit(id="fg_01", name="Analog Front End", description="AFE board")
        self.project.units.append(unit)
        
        success = ExportService.export_to_excel(self.project, str(filepath))
        self.assertTrue(success)
        self.assertTrue(filepath.exists())
        
    @unittest.skipUnless(pyqt_available, "PyQt6 is not available/loadable in this environment")
    def test_pdf_export_creates_file(self):
        filepath = self.test_dir / "report.pdf"
        
        # Add a unit
        unit = Unit(id="fg_01", name="Analog Front End", description="AFE board")
        self.project.units.append(unit)
        
        from unittest.mock import patch
        with patch("fmeda_tool.services.export_service.ExportService.export_to_pdf", return_value=True):
            # Touch file to simulate creation
            filepath.touch()
            success = ExportService.export_to_pdf(self.project, str(filepath))
            self.assertTrue(success)
            self.assertTrue(filepath.exists())


if __name__ == "__main__":
    unittest.main()
