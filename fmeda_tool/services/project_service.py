"""
Project file persistence, atomic saving, backups, and schema migrations.
"""

import json
import shutil
import os
import uuid
import time
from pathlib import Path
from typing import Tuple, Optional, Any
from fmeda_tool.models import Project
from fmeda_tool.utils.performance import PerformanceTimer


class ProjectService:
    """Service to handle atomic project file saving, backups, and schema migrations"""
    
    @staticmethod
    def save_project_atomically(project: Project, file_path: str) -> None:
        """
        Saves a project atomically using a temporary file in the same directory,
        flushes/fsyncs to disk, verifies JSON integrity, creates a .json.bak backup,
        and safely replaces the target file via os.replace.
        """
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Unique temporary file in the same directory to guarantee same-filesystem atomic rename
        temp_path = path.parent / f".tmp_{path.stem}_{uuid.uuid4().hex[:8]}.json"
        
        try:
            # 1. Write project JSON to temporary file and fsync
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(
                    project.model_dump(mode='json'),
                    f,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                    default=str
                )
                f.flush()
                os.fsync(f.fileno())
                
            # 2. Validate that the written temporary file is non-empty and contains valid JSON
            with open(temp_path, 'r', encoding='utf-8') as f:
                validated_data = json.load(f)
            if not isinstance(validated_data, dict) or "id" not in validated_data:
                raise ValueError("Temporary project file validation failed: invalid JSON structure.")
                
            # 3. Create/update the previous-version .json.bak file if target exists
            if path.exists():
                backup_path = path.with_suffix(".json.bak")
                try:
                    shutil.copy2(path, backup_path)
                except Exception as be:
                    print(f"Warning: Failed to update previous version backup: {be}")
                    
            # 4. Atomically replace target with validated temp file
            os.replace(temp_path, path)
            print(f"[OK] Project saved atomically to: {path}")
            
        finally:
            # 5. Clean up temporary file if it still exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    @staticmethod
    def load_and_migrate_project(
        file_path: str,
        timer: Optional[PerformanceTimer] = None
    ) -> Tuple[Project, bool, str]:
        """
        Loads a project file, tracks timing phases, checks schema version,
        and migrates legacy V1 schemas to V2 if necessary.
        
        Returns:
            A tuple of (project_object, was_migrated, migration_message)
        """
        path = Path(file_path)
        file_size = path.stat().st_size if path.exists() else 0
        
        # Phase 1: File reading
        if timer:
            timer.start_phase("file_reading")
        t0 = time.perf_counter()
        with open(path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        if timer:
            timer.end_phase("file_reading")
            
        # Phase 2: JSON parsing
        if timer:
            timer.start_phase("json_parsing")
        project_data = json.loads(raw_content)
        if timer:
            timer.end_phase("json_parsing")
            
        schema_version = project_data.get("schema_version", 1)
        was_migrated = False
        migration_msg = ""
        
        # Phase 3: Schema migration
        if timer:
            timer.start_phase("schema_migration")
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
            was_migrated = True
            migration_msg = (
                f"Project schema migrated from V1 to V2.\n"
                f"Recovered diagnostic measures from custom fields.\n"
                f"Created backup file at: {backup_path.name}"
            )
        if timer:
            timer.end_phase("schema_migration")
            
        # Phase 4: Pydantic model validation
        if timer:
            timer.start_phase("pydantic_validation")
        project = Project.model_validate(project_data)
        if timer:
            timer.end_phase("pydantic_validation")
            timer.record_project_metrics(project, file_size)
            
        if was_migrated:
            ProjectService.save_project_atomically(project, str(path))
            
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
            "user": user or getattr(project, "created_by", None) or "System"
        }
        if not hasattr(project, "change_history") or project.change_history is None:
            project.change_history = []
        project.change_history.append(entry)
