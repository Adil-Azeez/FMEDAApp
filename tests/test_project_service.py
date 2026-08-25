import unittest
import json
import os
import shutil
from pathlib import Path
from fmeda_tool.models import Project, Unit
from fmeda_tool.services import ProjectService


class TestProjectService(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = Path("tests/scratch_project_service")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        self.project = Project(
            id="proj_test_atomic",
            name="Atomic Save Test",
            description="Testing atomic saves and backups"
        )
        
    def tearDown(self):
        # Clean up scratch directory
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            
    def test_atomic_save_creates_file_and_backup(self):
        file_path = self.test_dir / "project.json"
        backup_path = self.test_dir / "project.json.bak"
        temp_path = self.test_dir / "project.tmp"
        
        # First save
        ProjectService.save_project_atomically(self.project, str(file_path))
        self.assertTrue(file_path.exists())
        self.assertFalse(backup_path.exists())
        self.assertFalse(temp_path.exists())
        
        # Second save (should create a backup)
        self.project.description = "Updated description"
        ProjectService.save_project_atomically(self.project, str(file_path))
        
        self.assertTrue(file_path.exists())
        self.assertTrue(backup_path.exists())
        
        # Verify content of backup has old description and target has new
        with open(backup_path, 'r', encoding='utf-8') as f:
            bak_data = json.load(f)
        with open(file_path, 'r', encoding='utf-8') as f:
            target_data = json.load(f)
            
        self.assertEqual(bak_data["description"], "Testing atomic saves and backups")
        self.assertEqual(target_data["description"], "Updated description")
        
    def test_migration_from_v1_to_v2(self):
        # Create a mock V1 project JSON
        v1_data = {
            "id": "proj_v1_legacy",
            "name": "Legacy V1 Project",
            "description": "Legacy description",
            "createdBy": "Legacy Author",  # camelCase key
            "customFields": {              # camelCase key
                "diagnostic_measures": json.dumps([
                    {
                        "id": "dm_01",
                        "name": "Legacy DM",
                        "description": "Legacy Diagnostic Measure",
                        "dc": 95.0
                    }
                ])
            }
        }
        
        file_path = self.test_dir / "legacy_project.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(v1_data, f, indent=2)
            
        # Load and migrate
        project, was_migrated, msg = ProjectService.load_and_migrate_project(str(file_path))
        
        self.assertTrue(was_migrated)
        self.assertIn("migrated from V1 to V2", msg)
        self.assertEqual(project.schema_version, 2)
        
        # Check CamelCase normalization
        self.assertEqual(project.created_by, "Legacy Author")
        
        # Check diagnostic measures extraction
        self.assertEqual(len(project.diagnostic_measures), 1)
        self.assertEqual(project.diagnostic_measures[0].id, "dm_01")
        self.assertEqual(project.diagnostic_measures[0].dc, 95.0)
        
        # Check backup created
        backup_path = file_path.with_suffix(".json.bak")
        self.assertTrue(backup_path.exists())


if __name__ == "__main__":
    unittest.main()
