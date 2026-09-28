"""
Comprehensive automated tests for SQLite Component Library, multi-tier resolution,
null FIT preservation, project snapshots, display-name management, removal to NULL,
and test database isolation.
"""

import unittest
import sqlite3
import uuid
import re
import tempfile
import shutil
import os
from pathlib import Path

from fmeda_tool.db.database import (
    DatabaseService,
    get_database_path,
    get_db_connection,
    is_database_initialized,
    set_custom_database_path,
    get_project_root
)
from fmeda_tool.services.component_library_service import ComponentLibraryService
from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment


class TestSQLiteComponentLibrary(unittest.TestCase):
    """Test suite for SQLite component library functionality"""
    
    temp_dir = None
    temp_db_path = None
    
    @classmethod
    def setUpClass(cls):
        # Create isolated temporary database for test suite
        cls.temp_dir = tempfile.mkdtemp(prefix="fmeda_test_sqlite_suite_")
        cls.temp_db_path = Path(cls.temp_dir) / "fmeda_suite.sqlite"
        DatabaseService.initialize_from_seed(force_rebuild=True, db_path=cls.temp_db_path)
        set_custom_database_path(cls.temp_db_path)

    @classmethod
    def tearDownClass(cls):
        set_custom_database_path(None)
        if cls.temp_dir and Path(cls.temp_dir).exists():
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_database_initialization_and_counts(self):
        """Verify database exists, is initialized, and has exact expected record counts and foreign keys."""
        self.assertTrue(is_database_initialized())
        self.assertTrue(get_database_path().exists())
        
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            # Check table counts
            exida_count = cur.execute("SELECT count(*) FROM components").fetchone()[0]
            legacy_count = cur.execute("SELECT count(*) FROM legacy_components").fetchone()[0]
            profile_count = cur.execute("SELECT count(*) FROM profiles").fetchone()[0]
            
            self.assertEqual(exida_count, 364)
            self.assertEqual(legacy_count, 143)
            self.assertEqual(profile_count, 5)
            
            # Foreign Key integrity check
            fk_check = cur.execute("PRAGMA foreign_key_check;").fetchall()
            self.assertEqual(len(fk_check), 0, f"Foreign key violations found: {fk_check}")
            
            # Metadata check
            meta = cur.execute("SELECT library_id, schema_version FROM library_metadata").fetchone()
            self.assertIsNotNone(meta)
            self.assertEqual(meta["schema_version"], "1.0")

    def test_02_null_fit_preservation(self):
        """Verify null FIT values in library records are preserved as NULL and not converted to 0.0."""
        with get_db_connection() as conn:
            cur = conn.cursor()
            null_count = cur.execute("SELECT count(*) FROM component_failure_rates WHERE fit IS NULL").fetchone()[0]
            self.assertGreater(null_count, 0, "Expected at least one null FIT record in database")
            
            # Query specific component known to have null FIT in Profile 2 (e.g. FR-000180)
            row = cur.execute("""
                SELECT c.id, c.failure_rate_id, cfr.fit 
                FROM components c 
                JOIN component_failure_rates cfr ON c.id = cfr.component_id 
                WHERE c.failure_rate_id = 'FR-000180' AND cfr.profile_id = 'profile_2'
            """).fetchone()
            
            self.assertIsNotNone(row)
            self.assertIsNone(row["fit"], "Null FIT was erroneously converted to non-null value")
            
        # Verify via Service
        snap = ComponentLibraryService.get_exida_component_snapshot(row["id"], profile="Profile 2")
        self.assertIsNotNone(snap)
        self.assertIsNone(snap["failure_rate"], "ComponentLibraryService converted null FIT to non-null")

    def test_03_multi_tier_component_resolution(self):
        """
        Verify multi-tier component resolution:
        1. UUID
        2. Failure Rate ID
        3. Current display name
        4. Exact legacy alias ('e' suffix)
        5. Parsed base alias + profile suffix (RM10eP2)
        6. Legacy display name / shortcut
        7. Unresolved
        """
        # Tier 1: UUID
        c_uuid = "094127de-f949-50f1-adc0-07132ba36bf3"
        stype, snap, method = ComponentLibraryService.resolve_component(c_uuid, "Profile 1")
        self.assertEqual(stype, "exida")
        self.assertEqual(method, "uuid")
        self.assertEqual(snap["library_component_id"], c_uuid)
        
        # Tier 2: Failure Rate ID
        stype, snap, method = ComponentLibraryService.resolve_component("FR-000001", "Profile 1")
        self.assertEqual(stype, "exida")
        self.assertEqual(method, "failure_rate_id")
        self.assertEqual(snap["failure_rate_id"], "FR-000001")
        
        # Tier 3: Current display name
        stype, snap, method = ComponentLibraryService.resolve_component("CEL", "Profile 1")
        self.assertEqual(stype, "exida")
        self.assertEqual(method, "display_name")
        self.assertEqual(snap["display_name"], "CEL")
        
        # Tier 4: Exact legacy alias (names ending in lowercase 'e')
        stype, snap, method = ComponentLibraryService.resolve_component("CELe", "Profile 1")
        self.assertEqual(stype, "exida")
        self.assertEqual(method, "legacy_alias")
        self.assertEqual(snap["display_name"], "CEL")
        
        # Tier 5: Parsed base alias + profile suffix (RM10eP2 -> RM10 + Profile 2)
        stype, snap, method = ComponentLibraryService.resolve_component("RM10eP2", "Profile 1")
        self.assertEqual(stype, "exida")
        self.assertEqual(method, "parsed_alias_with_profile")
        self.assertEqual(snap["selected_profile"], "Profile 2")
        self.assertEqual(snap["displayed_label"], "RM10")
        
        # Tier 6: Legacy display name
        stype, snap, method = ComponentLibraryService.resolve_component("C", "Profile 1")
        self.assertEqual(stype, "legacy")
        self.assertEqual(method, "legacy_display_name")
        self.assertEqual(snap["display_name"], "C")
        
        # Tier 7: Unresolved query
        stype, snap, method = ComponentLibraryService.resolve_component("INVALID_NON_EXISTENT_QUERY_9999")
        self.assertIsNone(stype)
        self.assertIsNone(snap)
        self.assertEqual(method, "unresolved")

    def test_04_display_name_assignment_and_history(self):
        """Verify single display-name assignment, editing, alias retention, and change log recording."""
        # Find an unassigned component
        unassigned = ComponentLibraryService.get_unassigned_display_names()
        self.assertGreater(len(unassigned), 0)
        target_comp = unassigned[0]
        c_id = target_comp["id"]
        
        legit_display_name = f"CAP_ELEC_{uuid.uuid4().hex[:6].upper()}"
        
        # 1. Assign display name
        success, msg = ComponentLibraryService.assign_display_name(
            component_id=c_id,
            new_name=legit_display_name,
            change_reason="Standardized naming assignment",
            user="engineer_user"
        )
        self.assertTrue(success, f"Assignment failed: {msg}")
        
        # Verify in database
        snap = ComponentLibraryService.get_exida_component_snapshot(c_id)
        self.assertEqual(snap["display_name"], legit_display_name)
        self.assertEqual(snap["displayed_label"], legit_display_name)
        
        # Verify in change log
        logs = ComponentLibraryService.get_change_logs(component_id=c_id)
        self.assertGreater(len(logs), 0)
        self.assertEqual(logs[0]["new_value"], legit_display_name)
        self.assertEqual(logs[0]["action"], "assign_display_name")
        
        # 2. Edit existing display name and verify previous name is saved as alias
        updated_display_name = f"{legit_display_name}_V2"
        success, msg = ComponentLibraryService.assign_display_name(
            component_id=c_id,
            new_name=updated_display_name,
            change_reason="Engineering revision update",
            user="engineer_user"
        )
        self.assertTrue(success, f"Edit failed: {msg}")
        
        # Verify old legitimate name became alias
        with get_db_connection() as conn:
            cur = conn.cursor()
            alias_row = cur.execute(
                "SELECT alias FROM component_aliases WHERE component_id = ? AND alias = ?",
                (c_id, legit_display_name)
            ).fetchone()
            self.assertIsNotNone(alias_row, "Previous approved display name was not preserved as alias")

    def test_05_display_name_validation_rules(self):
        """Verify display name validation rules (trimming, non-empty, uniqueness, no UUID/FR-ID)."""
        # Empty name
        valid, msg = ComponentLibraryService.validate_display_name("   ")
        self.assertFalse(valid)
        
        # UUID pattern
        valid, msg = ComponentLibraryService.validate_display_name(str(uuid.uuid4()))
        self.assertFalse(valid)
        self.assertIn("UUID", msg)
        
        # Failure Rate ID pattern
        valid, msg = ComponentLibraryService.validate_display_name("FR-000001")
        self.assertFalse(valid)
        self.assertIn("Failure Rate ID", msg)
        
        # Duplicate active name
        valid, msg = ComponentLibraryService.validate_display_name("CEL")
        self.assertFalse(valid)
        self.assertIn("already assigned", msg)

    def test_06_batch_display_name_assignment_atomic(self):
        """Verify atomic batch assignment with rollback on failure."""
        unassigned = ComponentLibraryService.get_unassigned_display_names()
        self.assertGreaterEqual(len(unassigned), 2)
        
        comp1 = unassigned[0]
        comp2 = unassigned[1]
        
        valid_name1 = f"CAP_BATCH_A_{uuid.uuid4().hex[:4].upper()}"
        duplicate_name = valid_name1  # Intentional conflict within batch
        
        # Try invalid batch (internal duplicates)
        assignments = [
            {"component_id": comp1["id"], "proposed_display_name": valid_name1},
            {"component_id": comp2["id"], "proposed_display_name": duplicate_name}
        ]
        
        success, msg, errors = ComponentLibraryService.batch_assign_display_names(assignments)
        self.assertFalse(success, "Batch with duplicate proposed names should fail")
        self.assertGreater(len(errors), 0)
        
        # Verify comp1 was NOT updated (atomic rollback)
        snap1 = ComponentLibraryService.get_exida_component_snapshot(comp1["id"])
        self.assertNotEqual(snap1["display_name"], valid_name1)
        
        # Now apply valid batch
        valid_name2 = f"CAP_BATCH_B_{uuid.uuid4().hex[:4].upper()}"
        valid_assignments = [
            {"component_id": comp1["id"], "proposed_display_name": valid_name1},
            {"component_id": comp2["id"], "proposed_display_name": valid_name2}
        ]
        success, msg, errors = ComponentLibraryService.batch_assign_display_names(valid_assignments)
        self.assertTrue(success, f"Valid batch failed: {msg}")
        
        snap1 = ComponentLibraryService.get_exida_component_snapshot(comp1["id"])
        snap2 = ComponentLibraryService.get_exida_component_snapshot(comp2["id"])
        self.assertEqual(snap1["display_name"], valid_name1)
        self.assertEqual(snap2["display_name"], valid_name2)

    def test_07_project_snapshot_isolation(self):
        """Verify that modifying a library component later does not change existing project calculation data."""
        # Create a component instance snapshot from Profile 1
        snap = ComponentLibraryService.get_exida_component_snapshot("094127de-f949-50f1-adc0-07132ba36bf3", "Profile 1")
        
        comp = Component(
            id="comp_test_101",
            position="C101",
            name="Decoupling Capacitor",
            type=snap["displayed_label"],
            failure_rate=snap["failure_rate"],
            failure_modes=snap["failure_modes"].copy(),
            library_component_id=snap["library_component_id"],
            failure_rate_id=snap["failure_rate_id"],
            selected_profile=snap["selected_profile"],
            snapshot=snap
        )
        
        unit = Unit(id="u1", name="Power Unit", description="Test Unit", components=[comp])
        project = Project(id="p1", name="Isolation Test", description="Desc", units=[unit])
        
        # Verify initial values
        self.assertEqual(comp.failure_rate, 5.2)
        self.assertEqual(comp.type, "CEL")
        
        # Simulate library change
        ComponentLibraryService.assign_display_name(
            component_id="094127de-f949-50f1-adc0-07132ba36bf3",
            new_name="CEL_CUSTOM_V2",
            change_reason="Snapshot isolation test"
        )
        
        # Project component instance remains unchanged
        self.assertEqual(comp.failure_rate, 5.2)
        self.assertEqual(comp.type, "CEL")
        self.assertEqual(comp.snapshot["displayed_label"], "CEL")
        
        # Revert change
        ComponentLibraryService.assign_display_name(
            component_id="094127de-f949-50f1-adc0-07132ba36bf3",
            new_name="CEL",
            change_reason="Revert test"
        )

    def test_08_profiles_failure_rate_diversity(self):
        """Verify that different profiles (1 to 5) load corresponding failure rates and failure modes."""
        c_uuid = "094127de-f949-50f1-adc0-07132ba36bf3"  # CEL
        
        p1_snap = ComponentLibraryService.get_exida_component_snapshot(c_uuid, "Profile 1")
        p2_snap = ComponentLibraryService.get_exida_component_snapshot(c_uuid, "Profile 2")
        p4_snap = ComponentLibraryService.get_exida_component_snapshot(c_uuid, "Profile 4")
        
        self.assertEqual(p1_snap["failure_rate"], 5.2)
        self.assertEqual(p2_snap["failure_rate"], 2.7)
        self.assertEqual(p4_snap["failure_rate"], 0.7)
        self.assertGreater(len(p1_snap["failure_modes"]), 0)

    def test_09_remove_display_name_to_null(self):
        """Verify removing a display name resets components.display_name to NULL and uses component_type fallback."""
        unassigned = ComponentLibraryService.get_unassigned_display_names()
        self.assertGreater(len(unassigned), 0)
        target = unassigned[0]
        c_id = target["id"]
        orig_type = target["component_type"]
        
        temp_name = f"CONN_REM_{uuid.uuid4().hex[:6].upper()}"
        
        # 1. Assign display name
        success, msg = ComponentLibraryService.assign_display_name(
            component_id=c_id,
            new_name=temp_name,
            change_reason="Assigned before removal test"
        )
        self.assertTrue(success)
        
        snap = ComponentLibraryService.get_exida_component_snapshot(c_id)
        self.assertEqual(snap["display_name"], temp_name)
        self.assertEqual(snap["displayed_label"], temp_name)
        
        # 2. Remove display name
        success, msg = ComponentLibraryService.remove_display_name(
            component_id=c_id,
            change_reason="User removed display name"
        )
        self.assertTrue(success, f"Removal failed: {msg}")
        
        # 3. Verify in database
        snap_after = ComponentLibraryService.get_exida_component_snapshot(c_id)
        self.assertIsNone(snap_after["display_name"], "display_name was not restored to NULL")
        self.assertEqual(snap_after["displayed_label"], orig_type, "displayed_label did not fallback to component_type")
        
        # 4. Verify audit log entry
        logs = ComponentLibraryService.get_change_logs(component_id=c_id)
        self.assertGreater(len(logs), 0)
        self.assertEqual(logs[0]["action"], "remove_display_name")
        self.assertEqual(logs[0]["old_value"], temp_name)
        self.assertIsNone(logs[0]["new_value"])

    def test_10_test_name_alias_suppression(self):
        """Verify test-generated names (e.g. TEST_*, BATCH_TEST_*) are not added to component_aliases."""
        unassigned = ComponentLibraryService.get_unassigned_display_names()
        self.assertGreater(len(unassigned), 0)
        target = unassigned[0]
        c_id = target["id"]
        
        test_name_1 = f"TEST_DISP_{uuid.uuid4().hex[:6]}"
        test_name_2 = f"TEST_DISP_{uuid.uuid4().hex[:6]}_V2"
        
        # 1. Assign test name
        ComponentLibraryService.assign_display_name(c_id, test_name_1)
        # 2. Edit to another test name
        ComponentLibraryService.assign_display_name(c_id, test_name_2)
        
        # 3. Verify test_name_1 was NOT added to component_aliases
        with get_db_connection() as conn:
            cur = conn.cursor()
            alias = cur.execute("SELECT * FROM component_aliases WHERE component_id = ? AND alias = ?", (c_id, test_name_1)).fetchone()
            self.assertIsNone(alias, "Test name was erroneously preserved in component_aliases")
            
        # 4. Remove test name
        ComponentLibraryService.remove_display_name(c_id)
        
        # 5. Verify no test aliases remain
        with get_db_connection() as conn:
            cur = conn.cursor()
            test_aliases = cur.execute("SELECT * FROM component_aliases WHERE component_id = ? AND alias LIKE 'TEST%'", (c_id,)).fetchall()
            self.assertEqual(len(test_aliases), 0)

    def test_11_production_database_guard(self):
        """Verify production database access guard blocks tests attempting to touch data/fmeda.sqlite."""
        prod_path = get_project_root() / "data" / "fmeda.sqlite"
        
        # In test environment, connecting to production database directly must raise RuntimeError
        with self.assertRaises(RuntimeError) as ctx:
            get_db_connection(prod_path)
            
        self.assertIn("Test Isolation Violation", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
