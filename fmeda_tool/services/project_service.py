import json
import shutil
from pathlib import Path
from typing import Tuple, Optional
from fmeda_tool.models import Project


class ProjectService:
    """Service to handle atomic project file saving, backups, and schema migrations"""
    
    @staticmethod
    def save_project_atomically(project: Project, file_path: str) -> None:
        """
        Saves a project atomically using a temporary file, creating a backup of the original.
        """
        path = Path(file_path)
        temp_path = path.with_suffix(".tmp")
        
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Write to temporary file
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(project.model_dump(mode='json'), f, indent=2, ensure_ascii=False, default=str)
            
        # 2. Backup existing file if it exists
        if path.exists():
            backup_path = path.with_suffix(".json.bak")
            # Remove old backup if it exists
            if backup_path.exists():
                backup_path.unlink()
            path.rename(backup_path)
            
        # 3. Rename temp file to target
        temp_path.rename(path)
        print(f"Project saved atomically to: {path}")

    @staticmethod
    def load_and_migrate_project(file_path: str) -> Tuple[Project, bool, str]:
        """
        Loads a project file, checks schema version, and migrates V1 schemas to V2 if necessary.
        
        Returns:
            A tuple of (project_object, was_migrated, migration_message)
        """
        path = Path(file_path)
        with open(path, 'r', encoding='utf-8') as f:
            project_data = json.load(f)
            
        schema_version = project_data.get("schema_version", 1)
        was_migrated = False
        migration_msg = ""
        
        if schema_version < 2:
            # 1. Create a backup of the original file
            backup_path = path.with_suffix(".json.bak")
            shutil.copy2(path, backup_path)
            
            # 2. Migrate diagnostic measures
            custom_fields = project_data.get('customFields', project_data.get('custom_fields', {}))
            legacy_measures = custom_fields.pop('diagnostic_measures', None)
            if legacy_measures:
                if isinstance(legacy_measures, str):
                    try:
                        legacy_measures = json.loads(legacy_measures)
                    except Exception:
                        legacy_measures = []
                if 'diagnostic_measures' not in project_data:
                    project_data['diagnostic_measures'] = legacy_measures
            project_data['custom_fields'] = custom_fields
            
            # Normalize camelCase to snake_case
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
                    
            project_data["schema_version"] = 2
            
            project = Project(**project_data)
            ProjectService.save_project_atomically(project, str(path))
            
            was_migrated = True
            migration_msg = (
                f"Project schema migrated from V1 to V2.\n"
                f"Recovered diagnostic measures from custom fields.\n"
                f"Created backup file at: {backup_path.name}"
            )
        else:
            project = Project(**project_data)
            
        return project, was_migrated, migration_msg

    @staticmethod
    def log_change(project: Project, action: str, details: str, user: Optional[str] = None) -> None:
        """
        Appends a change history log entry to the project.
        """
        from datetime import datetime
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
            "user": user or project.created_by or "System"
        }
        if not hasattr(project, "change_history") or project.change_history is None:
            project.change_history = []
        project.change_history.append(entry)
