"""
SQLite Database Service and Initialization for FMEDA Component Library
"""

import sqlite3
import json
import logging
import re
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Global custom database path override (e.g. for test isolation)
_custom_database_path: Optional[Path] = None


def set_custom_database_path(path: Optional[Path]) -> None:
    """Sets a global custom database path override (used for test isolation)."""
    global _custom_database_path
    _custom_database_path = Path(path) if path is not None else None


def get_custom_database_path() -> Optional[Path]:
    """Gets the current global custom database path override if set."""
    return _custom_database_path


def get_project_root() -> Path:
    """Resolves the project root directory containing main.py."""
    current = Path(__file__).resolve().parent
    for p in [current, *current.parents]:
        if (p / "main.py").exists():
            return p
    # Fallback to 2 directories up from this file (fmeda_tool/db/ -> fmeda_tool/ -> root)
    return Path(__file__).resolve().parents[2]


def get_database_path() -> Path:
    """
    Returns the active SQLite database path:
    1. Global override set via set_custom_database_path()
    2. FMEDA_DB_PATH environment variable
    3. Default operational path (data/fmeda.sqlite)
    """
    if _custom_database_path is not None:
        return _custom_database_path
    if "FMEDA_DB_PATH" in os.environ and os.environ["FMEDA_DB_PATH"]:
        return Path(os.environ["FMEDA_DB_PATH"])
    return get_project_root() / "data" / "fmeda.sqlite"


def get_seed_json_path() -> Path:
    """Returns the seed JSON path in data/seed/."""
    root = get_project_root()
    p1 = root / "data" / "seed" / "Combined_Exida_Component_library_version2.json"
    if p1.exists():
        return p1
    p2 = root / "data" / "seed" / "Combined_Exida_Component_library(version2).json"
    if p2.exists():
        return p2
    return p1


def get_schema_sql_path() -> Path:
    """Returns the schema.sql path."""
    return Path(__file__).resolve().parent / "schema.sql"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Creates and returns a SQLite connection with foreign keys enabled
    and row_factory set to sqlite3.Row.
    
    Includes a test isolation guard to prevent automated tests from modifying
    the production database.
    """
    path = db_path or get_database_path()
    
    # Test Isolation Guard: ensure tests never connect to production data/fmeda.sqlite
    is_in_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("FMEDA_TEST_MODE"))
    if is_in_pytest:
        prod_path = (get_project_root() / "data" / "fmeda.sqlite").resolve()
        if path.resolve() == prod_path and not os.environ.get("ALLOW_PROD_DB_IN_TEST"):
            raise RuntimeError(
                "Test Isolation Violation: Automated tests cannot access production database 'data/fmeda.sqlite'. "
                "Tests must use isolated temporary databases (e.g. via isolated_test_db fixture or set_custom_database_path)."
            )
            
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def is_database_initialized(db_path: Optional[Path] = None) -> bool:
    """Checks if the SQLite database exists and contains expected tables and records."""
    path = db_path or get_database_path()
    if not path.exists() or path.stat().st_size == 0:
        return False
    
    try:
        with get_db_connection(path) as conn:
            cur = conn.cursor()
            # Check for required tables
            tables = {row[0] for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()}
            required = {
                "library_metadata", "profiles", "components", "component_aliases",
                "component_failure_rates", "failure_modes", "component_failure_modes",
                "legacy_components", "legacy_failure_modes", "component_change_log"
            }
            if not required.issubset(tables):
                return False
            
            # Check that counts are valid
            comp_count = cur.execute("SELECT count(*) FROM components").fetchone()[0]
            prof_count = cur.execute("SELECT count(*) FROM profiles").fetchone()[0]
            return comp_count > 0 and prof_count >= 5
    except Exception as e:
        logger.warning(f"Error checking database initialization: {e}")
        return False


class DatabaseService:
    """Service for managing the SQLite database initialization, verification, and rebuilding."""
    
    @staticmethod
    def set_custom_database_path(path: Optional[Path]) -> None:
        """Sets global custom database path."""
        set_custom_database_path(path)
        
    @staticmethod
    def get_custom_database_path() -> Optional[Path]:
        """Gets global custom database path."""
        return get_custom_database_path()
        
    @staticmethod
    def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
        """Creates connection to SQLite database."""
        return get_db_connection(db_path)
    
    @staticmethod
    def ensure_database_ready(db_path: Optional[Path] = None) -> Tuple[bool, str]:
        """
        Ensures data/fmeda.sqlite is ready on application startup:
        1. If it exists and has compatible schema, uses it directly.
        2. If not, initializes from the seed JSON.
        """
        target_path = db_path or get_database_path()
        if is_database_initialized(target_path):
            return True, f"SQLite component database ready at {target_path}"
        
        logger.info(f"Initializing SQLite database at {target_path} from seed JSON...")
        return DatabaseService.initialize_from_seed(db_path=target_path)

    @staticmethod
    def initialize_from_seed(force_rebuild: bool = False, db_path: Optional[Path] = None, seed_path: Optional[Path] = None) -> Tuple[bool, str]:
        """
        Initializes data/fmeda.sqlite from seed JSON.
        Used for startup initialization, administrator rebuilds, and test suites.
        """
        target_db = db_path or get_database_path()
        seed_file = seed_path or get_seed_json_path()
        schema_file = get_schema_sql_path()
        
        if not seed_file.exists():
            msg = f"Seed JSON file not found at {seed_file}. Cannot initialize database."
            logger.error(msg)
            return False, msg
        
        if not schema_file.exists():
            msg = f"Schema SQL file not found at {schema_file}."
            logger.error(msg)
            return False, msg
        
        target_db.parent.mkdir(parents=True, exist_ok=True)
        
        # Load seed JSON
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                seed_data = json.load(f)
        except Exception as e:
            msg = f"Failed to parse seed JSON {seed_file}: {e}"
            logger.error(msg)
            return False, msg
        
        now_str = datetime.now().isoformat()
        
        conn = get_db_connection(target_db)
        try:
            with conn:
                cur = conn.cursor()
                
                if force_rebuild:
                    # Drop all existing tables to allow clean schema recreation
                    cur.execute("PRAGMA foreign_keys = OFF;")
                    existing_tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
                    for t in existing_tables:
                        if t != "sqlite_sequence":
                            cur.execute(f"DROP TABLE IF EXISTS {t};")
                    cur.execute("PRAGMA foreign_keys = ON;")
                
                # Execute schema script
                with open(schema_file, "r", encoding="utf-8") as f:
                    cur.executescript(f.read())
                
                # 1. Insert Metadata
                lib_id = seed_data.get("library_id", "b41d2f01-9596-5b7a-958f-ed405f96955a")
                schema_ver = str(seed_data.get("schema_version", "1.0"))
                description = seed_data.get("description", "")
                policy_json = json.dumps(seed_data.get("display_name_policy", {}))
                changes_json = json.dumps(seed_data.get("migration_changes", {}))
                
                cur.execute("""
                    INSERT OR REPLACE INTO library_metadata (
                        library_id, schema_version, description, display_name_policy, migration_changes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (lib_id, schema_ver, description, policy_json, changes_json, now_str, now_str))
                
                # 2. Insert Profiles
                profile_id_map: Dict[str, str] = {}  # "Profile 1" -> "profile_1", "profile_1" -> "profile_1"
                profiles_list = seed_data.get("profiles", [])
                if not profiles_list:
                    profiles_list = [{"id": f"profile_{i}", "name": f"Profile {i}"} for i in range(1, 6)]
                
                for prof in profiles_list:
                    p_id = prof["id"]
                    p_name = prof["name"]
                    match = re.search(r"(\d+)", p_id) or re.search(r"(\d+)", p_name)
                    p_num = int(match.group(1)) if match else 1
                    cur.execute("""
                        INSERT OR REPLACE INTO profiles (id, name, profile_number, description)
                        VALUES (?, ?, ?, ?)
                    """, (p_id, p_name, p_num, f"Reliability Profile {p_num}"))
                    profile_id_map[p_name] = p_id
                    profile_id_map[p_id] = p_id
                    profile_id_map[f"Profile {p_num}"] = p_id
                    profile_id_map[f"profile_{p_num}"] = p_id
                
                # 3. Insert Exida Components
                components_list = seed_data.get("components", [])
                for comp in components_list:
                    c_id = comp["id"]
                    fr_id = comp["failure_rate_id"]
                    item_id = comp.get("item_id")
                    item_no = comp.get("item_no")
                    display_name = comp.get("display_name")
                    if display_name is not None:
                        display_name = display_name.strip() or None
                    c_type = comp["component_type"]
                    c_subtype = comp.get("component_subtype")
                    c_category = comp.get("component_use_category")
                    
                    mapping = comp.get("mapping", {})
                    mapping_status = mapping.get("status") if isinstance(mapping, dict) else None
                    mapping_basis = mapping.get("basis") if isinstance(mapping, dict) else None
                    review_req = 1 if (isinstance(mapping, dict) and mapping.get("review_required")) else 0
                    
                    source = comp.get("source", {})
                    source_name = source.get("name") if isinstance(source, dict) else None
                    source_item_no = source.get("record_item_no") if isinstance(source, dict) else None
                    
                    cur.execute("""
                        INSERT INTO components (
                            id, failure_rate_id, item_id, item_no, display_name,
                            component_type, component_subtype, component_use_category,
                            mapping_status, mapping_basis, review_required,
                            source_name, source_record_item_no, status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """, (
                        c_id, fr_id, item_id, item_no, display_name,
                        c_type, c_subtype, c_category,
                        mapping_status, mapping_basis, review_req,
                        source_name, source_item_no, now_str, now_str
                    ))
                    
                    # Aliases
                    for alias in comp.get("legacy_aliases", []):
                        if alias and alias.strip():
                            cur.execute("""
                                INSERT INTO component_aliases (component_id, alias, alias_type, created_at)
                                VALUES (?, ?, 'legacy', ?)
                            """, (c_id, alias.strip(), now_str))
                    
                    # Profile FIT failure rates (Preserve NULL as NULL, never default to 0.0)
                    for prof_key, fit_val in comp.get("failure_rates_fit", {}).items():
                        prof_id = profile_id_map.get(prof_key, prof_key.lower().replace(" ", "_"))
                        fit_float = float(fit_val) if fit_val is not None else None
                        cur.execute("""
                            INSERT INTO component_failure_rates (component_id, profile_id, fit)
                            VALUES (?, ?, ?)
                        """, (c_id, prof_id, fit_float))
                    
                    # Failure Modes & Percentages
                    for fm in comp.get("failure_modes", []):
                        fm_id = fm["id"]
                        fm_name = fm["name"]
                        fm_desc = fm.get("description")
                        cur.execute("""
                            INSERT OR IGNORE INTO failure_modes (id, name, description)
                            VALUES (?, ?, ?)
                        """, (fm_id, fm_name, fm_desc))
                        
                        for prof_key, pct_val in fm.get("percentages", {}).items():
                            prof_id = profile_id_map.get(prof_key, prof_key.lower().replace(" ", "_"))
                            pct_float = float(pct_val) if pct_val is not None else None
                            cur.execute("""
                                INSERT INTO component_failure_modes (component_id, failure_mode_id, profile_id, percentage)
                                VALUES (?, ?, ?, ?)
                            """, (c_id, fm_id, prof_id, pct_float))
                
                # 4. Insert Legacy Components (Unmapped)
                legacy_list = seed_data.get("legacy_components_unmapped", [])
                for leg in legacy_list:
                    leg_id = leg["id"]
                    leg_display_name = leg["display_name"]
                    leg_shortcut = leg.get("shortcut")
                    leg_material = leg.get("material")
                    leg_db = leg.get("database")
                    leg_fits = float(leg["fits"]) if leg.get("fits") is not None else None
                    leg_map_status = leg.get("mapping_status", "unmapped_legacy")
                    leg_review = 1 if leg.get("review_required", True) else 0
                    leg_created = leg.get("created_at", now_str)
                    leg_updated = leg.get("updated_at", now_str)
                    
                    cur.execute("""
                        INSERT INTO legacy_components (
                            id, display_name, shortcut, material, database, fits,
                            mapping_status, review_required, status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """, (
                        leg_id, leg_display_name, leg_shortcut, leg_material, leg_db, leg_fits,
                        leg_map_status, leg_review, leg_created, leg_updated
                    ))
                    
                    # Legacy failure modes
                    for fm_name, fm_pct in leg.get("failure_modes", {}).items():
                        cur.execute("""
                            INSERT INTO legacy_failure_modes (legacy_component_id, name, percentage)
                            VALUES (?, ?, ?)
                        """, (leg_id, fm_name, float(fm_pct)))
                
                # 5. Validation Checks before commit
                fk_violations = cur.execute("PRAGMA foreign_key_check;").fetchall()
                if fk_violations:
                    raise ValueError(f"Foreign key violations detected during initialization: {fk_violations}")
                
                comp_count = cur.execute("SELECT count(*) FROM components").fetchone()[0]
                expected_comps = len(components_list)
                if comp_count != expected_comps:
                    raise ValueError(f"Component count mismatch: inserted {comp_count}, expected {expected_comps}")
                
                leg_count = cur.execute("SELECT count(*) FROM legacy_components").fetchone()[0]
                expected_leg = len(legacy_list)
                if leg_count != expected_leg:
                    raise ValueError(f"Legacy component count mismatch: inserted {leg_count}, expected {expected_leg}")
                
                prof_count = cur.execute("SELECT count(*) FROM profiles").fetchone()[0]
                if prof_count != len(profiles_list):
                    raise ValueError(f"Profiles count mismatch: inserted {prof_count}, expected {len(profiles_list)}")
                
            msg = f"Database successfully initialized with {comp_count} Exida components, {leg_count} Legacy components, and {prof_count} profiles."
            logger.info(msg)
            return True, msg
            
        except Exception as e:
            conn.rollback()
            msg = f"Failed to initialize SQLite component database: {e}"
            logger.error(msg)
            return False, msg
        finally:
            conn.close()


def initialize_database(force_rebuild: bool = False, db_path: Optional[Path] = None, seed_path: Optional[Path] = None) -> Tuple[bool, str]:
    """Convenience function to initialize database from seed."""
    return DatabaseService.initialize_from_seed(force_rebuild=force_rebuild, db_path=db_path, seed_path=seed_path)


def ensure_database_ready(db_path: Optional[Path] = None) -> Tuple[bool, str]:
    """Convenience function to ensure database is ready."""
    return DatabaseService.ensure_database_ready(db_path=db_path)
