"""
Pytest configuration and global test isolation fixtures.
Ensures that tests run strictly against temporary SQLite databases and cannot access
or modify the production data/fmeda.sqlite database.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from fmeda_tool.db.database import DatabaseService, set_custom_database_path, get_project_root


_session_db_path = None


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database_session():
    """
    Session-wide fixture that creates an isolated temporary SQLite database
    for all test executions, preventing any test from touching data/fmeda.sqlite.
    """
    global _session_db_path
    temp_dir = tempfile.mkdtemp(prefix="fmeda_test_session_")
    temp_db_path = Path(temp_dir) / "fmeda_test.sqlite"
    
    # Initialize the temporary database from seed JSON
    DatabaseService.initialize_from_seed(force_rebuild=True, db_path=temp_db_path)
    
    # Activate global custom path
    _session_db_path = temp_db_path
    set_custom_database_path(temp_db_path)
    
    yield temp_db_path
    
    # Cleanup on session end
    set_custom_database_path(None)
    _session_db_path = None
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def fresh_isolated_db():
    """
    Function-scoped fixture providing a completely fresh, isolated temporary database.
    """
    global _session_db_path
    temp_dir = tempfile.mkdtemp(prefix="fmeda_fresh_db_")
    temp_db_path = Path(temp_dir) / "fmeda_fresh.sqlite"
    
    DatabaseService.initialize_from_seed(force_rebuild=True, db_path=temp_db_path)
    set_custom_database_path(temp_db_path)
    
    yield temp_db_path
    
    set_custom_database_path(_session_db_path)
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
