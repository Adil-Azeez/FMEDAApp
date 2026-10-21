"""Release paths, first-run persistence and application-version regressions."""
import hashlib
from pathlib import Path
import shutil
import sys
import re
import json
import subprocess
from unittest.mock import patch

import openpyxl
from PyQt6.QtGui import QIcon, QTextDocument
from PyQt6.QtWidgets import QLabel, QMessageBox

from fmeda_tool import paths
from fmeda_tool.db import database
from fmeda_tool.models import Project
from fmeda_tool.services.export_service import ExportService
from fmeda_tool.ui.main_window import MainWindow
from fmeda_tool.version import APP_VERSION, APP_DISPLAY_NAME


def test_deployment_check_runs_in_an_unrelated_working_directory(tmp_path):
    output = tmp_path / "release-check"
    result = subprocess.run(
        [sys.executable, str(paths.resource_path("main.py")), "--deployment-check", str(output)],
        cwd=tmp_path, capture_output=True, text=True, timeout=45,
    )
    report_path = output / "deployment-check.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    assert result.returncode == 0, report or result.stderr
    assert report["passed"]
    assert (output / "report.xlsx").is_file()
    assert (output / "report.pdf").read_bytes().startswith(b"%PDF")


def test_development_paths_are_independent_of_working_directory(monkeypatch, tmp_path):
    root = paths.resource_root()
    monkeypatch.delenv("FMEDA_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.resource_path("fmeda_tool", "db", "schema.sql").is_file()
    assert database.get_seed_json_path().is_file()
    assert paths.data_directory() == root / "data"
    assert paths.projects_directory() == root / "data" / "projects"
    assert paths.logs_directory() == root / "logs"


def test_frozen_resources_and_writable_user_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "installed" / "_internal"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))
    monkeypatch.delenv("FMEDA_DATA_DIR", raising=False)
    monkeypatch.delenv("FMEDA_DB_PATH", raising=False)
    monkeypatch.setattr(database, "_custom_database_path", None)
    assert paths.resource_root() == tmp_path / "installed" / "_internal"
    assert database.get_schema_sql_path() == paths.resource_root() / "fmeda_tool" / "db" / "schema.sql"
    assert database.get_database_path() == tmp_path / "user" / "FMEDA Tool" / "fmeda.sqlite"
    assert paths.projects_directory() == tmp_path / "user" / "FMEDA Tool" / "projects"
    monkeypatch.setenv("FMEDA_DB_PATH", str(tmp_path / "custom.sqlite"))
    assert database.get_database_path() == tmp_path / "custom.sqlite"


def test_first_run_copies_snapshot_and_upgrade_preserves_database(monkeypatch, tmp_path, fresh_isolated_db):
    source_root = paths.resource_root()
    bundle = tmp_path / "bundle"
    (bundle / "data").mkdir(parents=True)
    (bundle / "fmeda_tool" / "db").mkdir(parents=True)
    bundled_db = bundle / "data" / "fmeda.sqlite"
    shutil.copy2(fresh_isolated_db, bundled_db)
    shutil.copy2(source_root / "fmeda_tool" / "db" / "schema.sql", bundle / "fmeda_tool" / "db" / "schema.sql")
    digest = hashlib.sha256(bundled_db.read_bytes()).hexdigest()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(database, "_custom_database_path", None)
    monkeypatch.delenv("FMEDA_DB_PATH", raising=False)
    monkeypatch.setenv("FMEDA_DATA_DIR", str(tmp_path / "user-data"))
    assert database.DatabaseService.ensure_database_ready()[0]
    with database.get_db_connection() as conn:
        conn.execute("CREATE TABLE deployment_sentinel (value TEXT)")
        conn.execute("INSERT INTO deployment_sentinel VALUES ('keep on upgrade')")
    assert database.DatabaseService.ensure_database_ready()[0]
    with database.get_db_connection() as conn:
        assert conn.execute("SELECT value FROM deployment_sentinel").fetchone()[0] == "keep on upgrade"
    assert hashlib.sha256(bundled_db.read_bytes()).hexdigest() == digest


def test_invalid_existing_packaged_database_is_not_replaced(monkeypatch, tmp_path):
    target = tmp_path / "existing.sqlite"
    target.write_bytes(b"existing data must be preserved")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    ready, message = database.DatabaseService.ensure_database_ready(db_path=target)
    assert not ready and "preserved" in message
    assert target.read_bytes() == b"existing data must be preserved"


def test_version_in_ui_exports_and_icon(qtbot, tmp_path):
    project = Project(id="version", name="Version test", description="Metadata", version="7.2.0")
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == APP_DISPLAY_NAME
    with patch.object(QMessageBox, "about") as about:
        window._on_about()
    assert APP_DISPLAY_NAME in about.call_args.args[2]
    window.unit_editor_view.load_project(project)
    assert APP_DISPLAY_NAME in [label.text() for label in window.unit_editor_view.overview_tab.findChildren(QLabel)]
    output = tmp_path / "version.xlsx"
    assert ExportService.export_to_excel(project, str(output))
    workbook = openpyxl.load_workbook(output)
    assert workbook.properties.creator == APP_DISPLAY_NAME
    assert APP_DISPLAY_NAME in workbook["Overview"]["A2"].value
    workbook.close()
    captured = []
    printer_method = "print" if hasattr(QTextDocument, "print") else "print_"
    with patch.object(QTextDocument, printer_method, lambda self, printer: captured.append((self.toPlainText(), printer.creator()))):
        ExportService.export_to_pdf(project, str(tmp_path / "version.pdf"))
    assert APP_DISPLAY_NAME in captured[0][0]
    assert captured[0][1] == APP_DISPLAY_NAME
    assert project.version == "7.2.0"  # The project's own version is independent.
    assert not QIcon(str(paths.resource_path("assets", "FMEDA.ico"))).isNull()
    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION)
