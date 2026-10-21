"""Opt-in release smoke check; writes only to the explicitly supplied new folder."""
from pathlib import Path
import json
import os
import traceback


def run(output_directory: str) -> int:
    output = Path(output_directory).resolve()
    # Refuse an existing location so this check cannot replace user data.
    output.mkdir(parents=True, exist_ok=False)
    os.environ["FMEDA_DATA_DIR"] = str(output)
    os.environ["FMEDA_DB_PATH"] = str(output / "fmeda.sqlite")
    report = {"passed": False}
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog, QInputDialog
        from PyQt6.QtGui import QIcon
        from unittest.mock import patch
        import inspect
        import openpyxl
        from fmeda_tool.paths import resource_path
        from fmeda_tool.version import APP_DISPLAY_NAME
        from fmeda_tool.db.database import DatabaseService, get_db_connection
        from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment, DiagnosticMeasure, Deviation, Mitigation
        from fmeda_tool.services.component_library_service import ComponentLibraryService
        from fmeda_tool.services.project_service import ProjectService
        from fmeda_tool.services.export_service import ExportService
        from fmeda_tool.services.calculation_service import CalculationService
        from fmeda_tool.ui.main_window import MainWindow
        from fmeda_tool.ui.unit_editor_view import DiagnosticMeasureManagerDialog

        app = QApplication.instance() or QApplication([])
        ready, message = DatabaseService.ensure_database_ready()
        assert ready, message
        with get_db_connection() as connection:
            report["library_components"] = connection.execute("SELECT count(*) FROM components").fetchone()[0]
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        ok, message, custom = ComponentLibraryService.create_custom_component(
            component_type="Resistor", fits=10, failure_modes={"Open": 50, "Short": 50},
            display_name="Deployment Check", description="Isolated release test")
        assert ok, message
        assert custom
        project = Project(id="deployment", name="Deployment check", description="Isolated release smoke test",
            diagnostic_measures=[DiagnosticMeasure(id="dm", name="Monitor", description="Check voltage", dc=90)],
            deviations=[Deviation(id="dev", name="Supply high", description="High voltage", failure_mode="Open", deviation_type="dangerous_detected", severity="high")],
            mitigations=[Mitigation(id="mit", name="Clamp", description="Limit voltage", mitigation_type="protective_circuit")],
            units=[Unit(id="u", name="Power", description="Power supply", components=[
                Component(id="c", name="Resistor", type="Resistor", position="R1", failure_rate=10,
                          failure_modes={"Open": 100}, failure_mode_assignments=[
                              FailureModeAssignment(failure_mode_name="Open", failure_rate_percentage=100,
                                  diagnostic_measure_id="dm", deviation_id="dev", mitigation_id="mit", detection_percentage=90)
                          ])])])
        project.deviations[0].mitigation_ids = ["mit"]
        saved = output / "projects" / "original.json"
        ProjectService.save_project_atomically(project, str(saved), record_history=False)
        reopened, _, _ = ProjectService.load_and_migrate_project(str(saved))
        window = MainWindow()
        window.current_project = reopened
        window.unit_editor_view.load_project(reopened)
        window.show_view("unit_editor")
        with patch.object(QMessageBox, "information"), patch.object(QInputDialog, "getMultiLineText", return_value=("", True)):
            assert window._on_save_project_from_editor()
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(output / "save-as.json"), "")):
                window._on_save_as()
        assert (output / "save-as.json").exists()
        window.unit_editor_view.formulas_btn.click()
        reference = window.get_current_view()
        assert "PFDavg" in reference.browser.toPlainText()
        assert "def calculate_scope" in inspect.getsource(CalculationService.calculate_scope)
        reference.back_btn.click()
        catalog = DiagnosticMeasureManagerDialog(reopened)
        catalog.search_input.setText("monitor")
        assert not catalog.table.isRowHidden(0)
        icon = QIcon(str(resource_path("assets", "FMEDA.ico")))
        assert not icon.isNull()
        assert ExportService.export_to_excel(reopened, str(output / "report.xlsx"))
        workbook = openpyxl.load_workbook(output / "report.xlsx")
        assert workbook.properties.creator == APP_DISPLAY_NAME
        workbook.close()
        assert ExportService.export_to_pdf(reopened, str(output / "report.pdf"))
        assert (output / "report.pdf").read_bytes().startswith(b"%PDF")
        assert (output / "report.pdf").stat().st_size > 1000
        # Reinitialization must preserve the custom database record.
        assert DatabaseService.ensure_database_ready()[0]
        assert ComponentLibraryService.search_custom_components(query="Deployment Check")
        report.update(passed=True, version=APP_DISPLAY_NAME,
                      checks=["startup", "sqlite", "custom components", "project open/save/save as",
                              "diagnostic measures", "deviations", "mitigations", "formulas/source links", "icon", "Excel", "PDF"])
        catalog.close()
        window.close()
    except Exception:
        report["error"] = traceback.format_exc()
    (output / "deployment-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1
