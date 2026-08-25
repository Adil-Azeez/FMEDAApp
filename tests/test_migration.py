import unittest
import json
from fmeda_tool.models import Project


class TestMigration(unittest.TestCase):
    
    def test_legacy_diagnostic_measures_migration(self):
        # Create a mock legacy project dictionary
        legacy_data = {
            "id": "proj_mock_01",
            "name": "Legacy Project",
            "description": "A legacy project format",
            "customFields": {
                "some_key": "some_value",
                "diagnostic_measures": '[{"id": "dm_001", "dc": 90.0, "description": "Legacy watchdog"}]'
            },
            "safetyStandard": "IEC 61508",
            "targetSIL": "SIL 2"
        }
        
        # Mimic the migration block from main_window.py
        project_data = json.loads(json.dumps(legacy_data)) # deep copy
        
        custom_fields = project_data.get('customFields', project_data.get('custom_fields', {}))
        legacy_measures = custom_fields.pop('diagnostic_measures', None)
        if legacy_measures:
            if isinstance(legacy_measures, str):
                try:
                    legacy_measures = json.loads(legacy_measures)
                except Exception:
                    legacy_measures = []
            if 'diagnostic_measures' not in project_data and 'diagnosticMeasures' not in project_data:
                project_data['diagnostic_measures'] = legacy_measures
        if 'customFields' in project_data:
            project_data['customFields'] = custom_fields
        if 'custom_fields' in project_data:
            project_data['custom_fields'] = custom_fields

        # Normalize camelCase keys to snake_case for Project pydantic model
        key_mappings = {
            'customFields': 'custom_fields',
            'safetyStandard': 'safety_standard',
            'targetSIL': 'target_sil',
            'productName': 'product_name',
            'productVersion': 'product_version',
            'missionTime': 'mission_time',
            'testInterval': 'test_interval',
            'completedAt': 'completed_at',
            'createdBy': 'created_by'
        }
        for camel, snake in key_mappings.items():
            if camel in project_data and snake not in project_data:
                project_data[snake] = project_data.pop(camel)
            
        # Parse into Project
        proj = Project(**project_data)
        
        # Asserts
        self.assertEqual(len(proj.diagnostic_measures), 1)
        self.assertEqual(proj.diagnostic_measures[0].id, "dm_001")
        self.assertEqual(proj.diagnostic_measures[0].dc, 90.0)
        self.assertEqual(proj.diagnostic_measures[0].description, "Legacy watchdog")
        self.assertNotIn("diagnostic_measures", proj.custom_fields)
        self.assertEqual(proj.custom_fields["some_key"], "some_value")
        self.assertEqual(proj.safety_standard.value, "IEC 61508")
        self.assertEqual(proj.target_sil, "SIL 2")


if __name__ == "__main__":
    unittest.main()
