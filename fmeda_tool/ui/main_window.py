from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget,
    QMenuBar, QMenu, QMessageBox, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, QRect, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QScreen
from typing import Optional, Any
import json
import time
from pathlib import Path

from fmeda_tool.models import Project, DiagnosticMeasure, Component
from fmeda_tool.ui.create_project_view import CreateProjectView
from fmeda_tool.ui.create_diagnostic_measure_view import CreateDiagnosticMeasureView
from fmeda_tool.ui.unit_editor_view import UnitEditorView
from fmeda_tool.ui.components_db_view import ComponentsDBView
from fmeda_tool.ui.unit_config_view import UnitConfigView
from fmeda_tool.ui.verification_view import VerificationView
from fmeda_tool.ui.export_view import ExportView
from fmeda_tool.ui.main_menu import MainMenu
from fmeda_tool.ui.dialogs import ProjectLoadingDialog
from fmeda_tool.utils.performance import PerformanceTimer


class ProjectLoadWorker(QThread):
    """Background worker thread to read, parse, migrate, validate, and prepare calculations without freezing UI."""
    
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(object, bool, str, object, float)  # (project, was_migrated, migration_msg, timer, finish_timestamp)
    error = pyqtSignal(str)
    
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        
    def run(self):
        timer = PerformanceTimer("Open Project")
        try:
            from fmeda_tool.services.project_service import ProjectService
            from fmeda_tool.services.calculation_service import CalculationService
            from fmeda_tool.services.validation_service import ValidationService
            
            self.progress.emit("Reading project file...", 15)
            
            project, was_migrated, migration_msg = ProjectService.load_and_migrate_project(
                self.file_path, timer=timer
            )
            
            self.progress.emit("Calculating FMEDA metrics...", 50)
            timer.start_phase("project_calculation")
            CalculationService.calculate_project(project)
            timer.end_phase("project_calculation")
            timer.counters.calculate_project_count += 1
            
            self.progress.emit("Verifying project safety rules...", 70)
            timer.start_phase("project_verification")
            ValidationService.validate_project(project)
            timer.end_phase("project_verification")
            timer.counters.validate_project_count += 1
            
            self.progress.emit("Preparing workspace tabs...", 85)
            finish_ts = time.perf_counter()
            self.finished.emit(project, was_migrated, migration_msg, timer, finish_ts)
            
        except Exception as e:
            import traceback
            err_details = traceback.format_exc()
            print(f"[ERROR Loading Project] {err_details}")
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window with menu bar"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FMEDA Tool")
        
        # Get screen size and calculate appropriate window size (80% of screen)
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        
        target_width = int(screen_width * 0.8)
        target_height = int(target_width * 9 / 16)
        
        if target_height > screen_height * 0.8:
            target_height = int(screen_height * 0.8)
            target_width = int(target_height * 16 / 9)
        
        self.resize(target_width, target_height)
        self.setMinimumSize(960, 540)
        
        frame_geometry = self.frameGeometry()
        center_point = screen_geometry.center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())
        
        self.current_project: Optional[Project] = None
        self.undo_stack = []
        self.editing_diagnostic_measure_row: Optional[int] = None
        
        self.navigation_history = []
        self.is_navigating_back = False
        self.has_unsaved_changes = False
        self._load_worker: Optional[ProjectLoadWorker] = None
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)
        
        self._create_menu_bar()
        
        self.views = {}
        
        self.main_menu = MainMenu()
        self.main_menu.new_project_clicked.connect(self._on_new_project)
        self.main_menu.open_project_clicked.connect(self._on_open_project)
        self.main_menu.components_db_clicked.connect(self._on_components_db)
        self.add_view("main_menu", self.main_menu)
        
        self.create_project_view = CreateProjectView()
        self.create_project_view.project_saved.connect(self._on_project_created)
        self.create_project_view.cancel_requested.connect(self._on_create_project_cancelled)
        self.add_view("create_project", self.create_project_view)
        
        self.unit_editor_view = UnitEditorView()
        self.unit_editor_view.main_window = self
        self.unit_editor_view.save_requested.connect(self._on_save_project_from_editor)
        self.unit_editor_view.back_requested.connect(self._on_fmeda_back)
        self.unit_editor_view.next_requested.connect(self._on_fmeda_next)
        self.add_view("unit_editor", self.unit_editor_view)
        
        self.verification_view = VerificationView()
        self.verification_view.back_requested.connect(self._on_verification_back)
        self.verification_view.next_requested.connect(self._on_verification_next)
        self.verification_view.re_verify_requested.connect(self._on_reverify_project)
        self.verification_view.alert_clicked.connect(self._on_verification_alert_clicked)
        self.add_view("verification", self.verification_view)
        
        self.export_view = ExportView()
        self.export_view.back_requested.connect(self._on_export_back)
        self.export_view.save_requested.connect(self._on_save_project_from_editor)
        self.export_view.finish_requested.connect(self._on_export_finish)
        self.export_view.export_excel_requested.connect(self._on_export_excel)
        self.export_view.export_pdf_requested.connect(self._on_export_pdf)
        self.add_view("export_view", self.export_view)
        
        self.components_db_view = ComponentsDBView()
        self.components_db_view.back_to_menu_requested.connect(lambda: self.show_view("main_menu"))
        self.add_view("components_db", self.components_db_view)
        
        self.show_view("main_menu")
        
    def _create_menu_bar(self):
        menubar = self.menuBar()
        
        nav_menu = menubar.addMenu("&Navigate")
        self.back_action = QAction("← &Back", self)
        self.back_action.setShortcut("Alt+Left")
        self.back_action.setStatusTip("Go back to previous view")
        self.back_action.triggered.connect(self._on_back)
        self.back_action.setEnabled(False)
        nav_menu.addAction(self.back_action)
        
        file_menu = menubar.addMenu("&File")
        
        home_action = QAction(" &Home", self)
        home_action.setShortcut("Ctrl+H")
        home_action.setStatusTip("Return to main menu")
        home_action.triggered.connect(self._on_home)
        file_menu.addAction(home_action)
        
        file_menu.addSeparator()
        
        new_project_action = QAction("&New Project", self)
        new_project_action.setShortcut("Ctrl+N")
        new_project_action.setStatusTip("Create a new FMEDA project")
        new_project_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_project_action)
        
        open_project_action = QAction("&Open Project...", self)
        open_project_action.setShortcut("Ctrl+O")
        open_project_action.setStatusTip("Open an existing project")
        open_project_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_project_action)
        
        file_menu.addSeparator()
        
        edit_project_action = QAction("&Edit Project...", self)
        edit_project_action.setShortcut("Ctrl+E")
        edit_project_action.setStatusTip("Edit current project settings")
        edit_project_action.triggered.connect(self._on_edit_project)
        file_menu.addAction(edit_project_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("&Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.setStatusTip("Save current project")
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.setStatusTip("Save project with a new name")
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        import_menu = file_menu.addMenu("&Import")
        import_pdf_action = QAction("Import PDF...", self)
        import_pdf_action.setStatusTip("Import component data from PDF")
        import_pdf_action.triggered.connect(self._on_import_pdf)
        import_menu.addAction(import_pdf_action)
        
        import_excel_action = QAction("Import Excel...", self)
        import_excel_action.setStatusTip("Import data from Excel file")
        import_excel_action.triggered.connect(self._on_import_excel)
        import_menu.addAction(import_excel_action)
        
        export_menu = file_menu.addMenu("&Export")
        export_excel_action = QAction("Export to Excel...", self)
        export_excel_action.setStatusTip("Export project to Excel format")
        export_excel_action.triggered.connect(self._on_export_excel)
        export_menu.addAction(export_excel_action)
        
        export_pdf_action = QAction("Export to PDF...", self)
        export_pdf_action.setStatusTip("Export project to PDF format")
        export_pdf_action.triggered.connect(self._on_export_pdf)
        export_menu.addAction(export_pdf_action)
        
        export_json_action = QAction("Export to JSON...", self)
        export_json_action.setStatusTip("Export project to JSON format")
        export_json_action.triggered.connect(self._on_export_json)
        export_menu.addAction(export_json_action)
        
        file_menu.addSeparator()
        
        recent_menu = file_menu.addMenu("&Recent Projects")
        no_recent_action = QAction("No recent projects", self)
        no_recent_action.setEnabled(False)
        recent_menu.addAction(no_recent_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        edit_menu = menubar.addMenu("&Edit")
        
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.setStatusTip("Undo last action")
        undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(undo_action)
        
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.setStatusTip("Redo last undone action")
        redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.setStatusTip("Cut selection")
        cut_action.triggered.connect(self._on_cut)
        edit_menu.addAction(cut_action)
        
        copy_action = QAction("&Copy", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.setStatusTip("Copy selection")
        copy_action.triggered.connect(self._on_copy)
        edit_menu.addAction(copy_action)
        
        paste_action = QAction("&Paste", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.setStatusTip("Paste from clipboard")
        paste_action.triggered.connect(self._on_paste)
        edit_menu.addAction(paste_action)
        
        edit_menu.addSeparator()
        
        find_action = QAction("&Find...", self)
        find_action.setShortcut("Ctrl+F")
        find_action.setStatusTip("Find in current view")
        find_action.triggered.connect(self._on_find)
        edit_menu.addAction(find_action)
        
        edit_menu.addSeparator()
        
        preferences_action = QAction("&Preferences...", self)
        preferences_action.setStatusTip("Open preferences dialog")
        preferences_action.triggered.connect(self._on_preferences)
        edit_menu.addAction(preferences_action)
        
        system_menu = menubar.addMenu("&System")
        
        project_settings_action = QAction("&Project Settings...", self)
        project_settings_action.setStatusTip("Configure project settings")
        project_settings_action.triggered.connect(self._on_project_settings)
        system_menu.addAction(project_settings_action)
        
        units_action = QAction("&Units Management...", self)
        units_action.setStatusTip("Manage project units")
        units_action.triggered.connect(self._on_units_management)
        system_menu.addAction(units_action)
        
        deviations_action = QAction("&Deviations Management...", self)
        deviations_action.setStatusTip("Manage deviations")
        deviations_action.triggered.connect(self._on_deviations_management)
        system_menu.addAction(deviations_action)
        
        mitigations_action = QAction("&Mitigations Management...", self)
        mitigations_action.setStatusTip("Manage mitigations")
        mitigations_action.triggered.connect(self._on_mitigations_management)
        system_menu.addAction(mitigations_action)
        
        system_menu.addSeparator()
        
        database_menu = system_menu.addMenu("&Database")
        
        backup_db_action = QAction("Backup Database...", self)
        backup_db_action.setStatusTip("Create database backup")
        backup_db_action.triggered.connect(self._on_backup_database)
        database_menu.addAction(backup_db_action)
        
        restore_db_action = QAction("Restore Database...", self)
        restore_db_action.setStatusTip("Restore database from backup")
        restore_db_action.triggered.connect(self._on_restore_database)
        database_menu.addAction(restore_db_action)
        
        system_menu.addSeparator()
        
        analysis_action = QAction("&Run FMEDA Analysis...", self)
        analysis_action.setShortcut("F5")
        analysis_action.setStatusTip("Run FMEDA analysis on current project")
        analysis_action.triggered.connect(self._on_run_analysis)
        system_menu.addAction(analysis_action)
        
        help_menu = menubar.addMenu("&Help")
        
        docs_action = QAction("&Documentation", self)
        docs_action.setShortcut("F1")
        docs_action.setStatusTip("Open documentation")
        docs_action.triggered.connect(self._on_documentation)
        help_menu.addAction(docs_action)
        
        guide_action = QAction("&User Guide", self)
        guide_action.setStatusTip("Open user guide")
        guide_action.triggered.connect(self._on_user_guide)
        help_menu.addAction(guide_action)
        
        help_menu.addSeparator()
        
        about_action = QAction("&About FMEDA Tool", self)
        about_action.setStatusTip("Show information about this application")
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
        
        updates_action = QAction("Check for &Updates...", self)
        updates_action.setStatusTip("Check for application updates")
        updates_action.triggered.connect(self._on_check_updates)
        help_menu.addAction(updates_action)
    
    def _on_new_project(self):
        self.create_project_view.reset_form()
        if "create_project" not in self.views:
            self.add_view("create_project", self.create_project_view)
        self.show_view("create_project")
    
    def _on_edit_project(self):
        if not self.current_project:
            QMessageBox.warning(
                self,
                "No Project Open",
                "Please create or open a project first before editing."
            )
            return
        
        project_dict = self.current_project.model_dump(mode='json')
        self.create_project_view.load_project(project_dict)
        if "create_project" not in self.views:
            self.add_view("create_project", self.create_project_view)
        self.show_view("create_project")
    
    def _on_project_created(self, project: Project):
        self.current_project = project
        self.setWindowTitle(f"FMEDA Tool - {project.name}")
        self.has_unsaved_changes = True
        
        print(f"[OK] Project created: {project.name}")
        print(f"  ID: {project.id}")
        print(f"  Version: {project.version}")
        
        self.unit_editor_view.load_project(project)
        self.show_view("unit_editor")
    
    def _on_create_project_cancelled(self):
        self.show_view("main_menu")
        
    def _on_open_project(self):
        """Handle File -> Open Project with background loading worker and progress dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "data/projects",
            "JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
            
        loading_dialog = ProjectLoadingDialog(Path(file_path).name, parent=self)
        loading_dialog.update_stage("Starting project loader...", 5)
        
        self._load_worker = ProjectLoadWorker(file_path, self)
        
        self._load_worker.progress.connect(loading_dialog.update_stage)
        self._load_worker.finished.connect(
            lambda proj, migrated, msg, timer, finish_ts: self._on_project_load_success(
                proj, migrated, msg, timer, finish_ts, loading_dialog
            )
        )
        self._load_worker.error.connect(
            lambda err: self._on_project_load_error(err, loading_dialog)
        )
        
        self._load_worker.start()
        loading_dialog.exec()
        
    def _on_project_load_success(
        self,
        project: Project,
        was_migrated: bool,
        migration_msg: str,
        timer: PerformanceTimer,
        finish_ts: float,
        dialog: Any
    ):
        """Handles successful background loading of project model and performs main thread UI initialization."""
        try:
            # 1. Signal delivery measurement
            timer.start_phase("worker_finished_signal_delivery", start_time=finish_ts)
            timer.end_phase("worker_finished_signal_delivery")
            
            # 2. Main window project assignment
            timer.start_phase("mainwindow_project_assignment")
            dialog.update_stage("Populating active workspace...", 90)
            
            self.current_project = project
            self.setWindowTitle(f"FMEDA Tool - {self.current_project.name}")
            
            self.undo_stack.clear()
            self.unit_editor_view.undo_btn.setEnabled(False)
            self.unit_editor_view.undo_btn.setToolTip("Nothing to undo")
            timer.end_phase("mainwindow_project_assignment")
            
            # 3. Load into editor view (lazy tabs populate only active tab)
            timer.start_phase("uniteditorview_load_project")
            self.unit_editor_view.load_project(self.current_project, timer=timer)
            timer.end_phase("uniteditorview_load_project")
            
            # 4. View switch & final event processing
            timer.start_phase("loading_dialog_close_and_final_ui_refresh")
            if "unit_editor" not in self.views:
                self.add_view("unit_editor", self.unit_editor_view)
            self.show_view("unit_editor")
            self.has_unsaved_changes = False
            
            dialog.accept()
            QApplication.processEvents()
            timer.end_phase("loading_dialog_close_and_final_ui_refresh")
            
            # Finalize timer metrics BEFORE modal blocking dialogs
            timer.finish()
            
            if was_migrated:
                QMessageBox.information(
                    self,
                    "Project Schema Migrated",
                    migration_msg
                )
                
            QMessageBox.information(
                self,
                "Project Opened",
                f"Project '{self.current_project.name}' opened successfully!"
            )
            
            print(f"[OK] Project opened: {self.current_project.name}")
            print(f"  ID: {self.current_project.id}")
            print(f"  Version: {self.current_project.version}")
            print(f"  Units: {len(self.current_project.units)}")
            
        except Exception as e:
            dialog.reject()
            import traceback
            print(f"[UI RENDER ERROR] {traceback.format_exc()}")
            QMessageBox.critical(
                self,
                "UI Render Error",
                f"Failed to render project workspace:\n{str(e)}"
            )

    def _on_project_load_error(self, err_msg: str, dialog: Any):
        dialog.reject()
        QMessageBox.critical(
            self,
            "Error Opening Project",
            f"Failed to open project:\n{err_msg}"
        )
        print(f"[ERROR] Failed to open project: {err_msg}")
        
    def _on_save(self):
        self._on_save_project_from_editor()
        
    def _on_save_as(self):
        if not self.current_project:
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            f"data/projects/{self.current_project.id}_{self.current_project.name.replace(' ', '_')}.json",
            "JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
            
        try:
            from datetime import datetime
            self.current_project.updated_at = datetime.now()
            
            active_idx = self.unit_editor_view.unit_tabs.currentIndex()
            if active_idx == 0:
                self.current_project.last_active_tab_id = "overview"
            else:
                if self.current_project.units and active_idx - 1 < len(self.current_project.units):
                    self.current_project.last_active_tab_id = self.current_project.units[active_idx - 1].id
                    
            from fmeda_tool.services.project_service import ProjectService
            ProjectService.save_project_atomically(self.current_project, file_path)
            
            self.has_unsaved_changes = False
            QMessageBox.information(
                self,
                "Project Saved",
                f"Project saved successfully to {Path(file_path).name}!"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Saving Project",
                f"Failed to save project:\n{str(e)}"
            )
        
    def _on_import_pdf(self):
        print("Import PDF clicked")
        
    def _on_import_excel(self):
        print("Import Excel clicked")
        
    def _on_export_excel(self):
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export FMEDA to Excel",
            f"{self.current_project.name.replace(' ', '_')}_FMEDA.xlsx",
            "Excel Files (*.xlsx);;All Files (*.*)"
        )
        if not file_path:
            return
            
        try:
            include_summary = self.export_view.opt_summary_sheet.isChecked()
            include_custom = self.export_view.opt_custom_fields.isChecked()
            include_history = self.export_view.opt_change_history.isChecked()
            fmeda_per_fg = self.export_view.opt_fmeda_sheets.isChecked()
            
            from fmeda_tool.services.export_service import ExportService
            ExportService.export_to_excel(
                self.current_project,
                file_path,
                include_summary=include_summary,
                include_custom=include_custom,
                include_history=include_history,
                fmeda_per_fg=fmeda_per_fg
            )
            QMessageBox.information(
                self,
                "Export Complete",
                f"FMEDA project successfully exported to Excel:\n{Path(file_path).name}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export to Excel:\n{str(e)}"
            )
        
    def _on_export_pdf(self):
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return
            
        try:
            from fmeda_tool.services.calculation_service import CalculationService
            CalculationService.calculate_project(self.current_project)
        except Exception as ce:
            import sys
            import traceback
            print(f"[RECALCULATION ERROR] {traceback.format_exc()}", file=sys.stderr)
            
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export FMEDA to PDF Report",
            f"{self.current_project.name.replace(' ', '_')}_FMEDA_Report.pdf",
            "PDF Files (*.pdf);;All Files (*.*)"
        )
        if not file_path:
            return
            
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"
            
        try:
            from fmeda_tool.services.export_service import ExportService
            ExportService.export_to_pdf(self.current_project, file_path)
            QMessageBox.information(
                self,
                "Export Complete",
                f"FMEDA report successfully exported to PDF:\n{Path(file_path).name}"
            )
        except Exception as e:
            import sys
            import traceback
            print(f"[PDF EXPORT ERROR] Failed to export to PDF:\n{traceback.format_exc()}", file=sys.stderr)
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export to PDF:\n{str(e)}"
            )
        
    def _on_export_json(self):
        print("Export to JSON clicked")
    
    def push_undo_state(self, action_desc: str):
        if getattr(self.unit_editor_view, "is_loading_project", False):
            return
        if self.current_project is not None:
            project_dump = self.current_project.model_dump()
            self.undo_stack.append((project_dump, action_desc))
            if len(self.undo_stack) > 50:
                self.undo_stack.pop(0)
            self.unit_editor_view.undo_btn.setEnabled(True)
            self.unit_editor_view.undo_btn.setToolTip(f"Undo: {action_desc}")
            self.has_unsaved_changes = True

    def _on_undo(self):
        if not self.undo_stack:
            return
            
        project_dump, action_desc = self.undo_stack.pop()
        self.current_project = Project.model_validate(project_dump)
        
        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.current_project)
        
        self.unit_editor_view.load_project(self.current_project)
        
        if self.undo_stack:
            next_action_desc = self.undo_stack[-1][1]
            self.unit_editor_view.undo_btn.setEnabled(True)
            self.unit_editor_view.undo_btn.setToolTip(f"Undo: {next_action_desc}")
        else:
            self.unit_editor_view.undo_btn.setEnabled(False)
            self.unit_editor_view.undo_btn.setToolTip("Nothing to undo")
            
        self.has_unsaved_changes = True
        
    def _on_redo(self):
        print("Redo clicked")
        
    def _on_cut(self):
        print("Cut clicked")
        
    def _on_copy(self):
        print("Copy clicked")
        
    def _on_paste(self):
        print("Paste clicked")
        
    def _on_find(self):
        print("Find clicked")
        
    def _on_preferences(self):
        print("Preferences clicked")
    
    def _on_project_settings(self):
        print("Project Settings clicked")
        
    def _on_units_management(self):
        if not self.current_project:
            QMessageBox.warning(
                self,
                "No Project Open",
                "Please create or open a project first before managing units."
            )
            return
        self.unit_editor_view.load_project(self.current_project)
        if "unit_editor" not in self.views:
            self.add_view("unit_editor", self.unit_editor_view)
        self.show_view("unit_editor")
    
    def _on_save_project_from_editor(self):
        if not self.current_project:
            return
        try:
            data_dir = Path("data/projects")
            data_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"{self.current_project.id}_{self.current_project.name.replace(' ', '_')}.json"
            filepath = data_dir / filename
            
            from datetime import datetime
            self.current_project.updated_at = datetime.now()
            
            active_idx = self.unit_editor_view.unit_tabs.currentIndex()
            if active_idx == 0:
                self.current_project.last_active_tab_id = "overview"
            else:
                if self.current_project.units and active_idx - 1 < len(self.current_project.units):
                    self.current_project.last_active_tab_id = self.current_project.units[active_idx - 1].id
            
            from fmeda_tool.services.project_service import ProjectService
            ProjectService.save_project_atomically(self.current_project, str(filepath))
            
            self.has_unsaved_changes = False
            QMessageBox.information(
                self,
                "Project Saved",
                f"Project '{self.current_project.name}' saved successfully!"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Saving Project",
                f"Failed to save project:\n{str(e)}"
            )
            print(f"Error saving project: {e}")
    
    def _on_fmeda_back(self):
        self.show_view("create_project")
        
    def _on_fmeda_next(self):
        if not self.current_project:
            return
        self.verification_view.load_project(self.current_project)
        self.show_view("verification")
        
    def _on_verification_back(self):
        self.show_view("unit_editor")
        
    def _on_verification_next(self):
        if not self.current_project:
            return
        self.export_view.load_project(self.current_project, is_dirty=self.has_unsaved_changes)
        self.show_view("export_view")
        
    def _on_reverify_project(self):
        self.verification_view.refresh_validation()
        
    def _on_verification_alert_clicked(self, unit_id: str, row_index: int):
        self.show_view("unit_editor")
        self.unit_editor_view.focus_unit_row(unit_id, row_index)
        
    def _on_export_back(self):
        self.show_view("verification")
        
    def _on_export_finish(self):
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Would you like to save them before finishing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_save_project_from_editor()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        self.show_view("main_menu")
        
    def _on_deviations_management(self):
        print("Deviations Management clicked")
        
    def _on_mitigations_management(self):
        print("Mitigations Management clicked")
        
    def _on_backup_database(self):
        print("Backup Database clicked")
        
    def _on_restore_database(self):
        print("Restore Database clicked")
        
    def _on_run_analysis(self):
        print("Run FMEDA Analysis clicked")
    
    def _on_documentation(self):
        print("Documentation clicked")
    
    def _on_components_db(self):
        if "components_db" not in self.views:
            self.add_view("components_db", self.components_db_view)
        self.show_view("components_db")
        
    def _on_user_guide(self):
        print("User Guide clicked")
        
    def _on_about(self):
        QMessageBox.about(
            self,
            "About FMEDA Tool",
            "<h2>FMEDA Tool</h2>"
            "<p>Version 1.0.0</p>"
            "<p>Failure Mode, Effects and Diagnostic Analysis Tool</p>"
            "<p>Copyright © 2026</p>"
        )
        
    def _on_check_updates(self):
        print("Check for Updates clicked")
    
    def add_view(self, name: str, widget: QWidget):
        self.views[name] = widget
        self.stacked_widget.addWidget(widget)
    
    def show_view(self, name: str):
        if name in self.views:
            if not self.is_navigating_back:
                current_widget = self.stacked_widget.currentWidget()
                current_view_name = None
                for view_name, widget in self.views.items():
                    if widget == current_widget:
                        current_view_name = view_name
                        break
                
                if current_view_name and current_view_name != name:
                    self.navigation_history.append(current_view_name)
                    self.back_action.setEnabled(True)
            
            self.stacked_widget.setCurrentWidget(self.views[name])
            self.is_navigating_back = False
        else:
            print(f"Warning: View '{name}' not found")
    
    def get_current_view(self) -> QWidget:
        return self.stacked_widget.currentWidget()
    
    def _on_back(self):
        if self.navigation_history:
            previous_view = self.navigation_history.pop()
            if not self.navigation_history:
                self.back_action.setEnabled(False)
            self.is_navigating_back = True
            self.show_view(previous_view)
    
    def _on_home(self):
        if self.has_unsaved_changes and self.current_project:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"You have unsaved changes in project '{self.current_project.name}'.\n\nDo you want to save before returning to the main menu?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_save_project_from_editor()
                self.show_view("main_menu")
            elif reply == QMessageBox.StandardButton.No:
                self.has_unsaved_changes = False
                self.show_view("main_menu")
        else:
            self.show_view("main_menu")
