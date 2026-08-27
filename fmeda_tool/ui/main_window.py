

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget,
    QMenuBar, QMenu, QMessageBox, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QAction, QScreen
from typing import Optional
import json
from pathlib import Path

from fmeda_tool.models import Project, DiagnosticMeasure, Component
from .create_project_view import CreateProjectView
from .create_diagnostic_measure_view import CreateDiagnosticMeasureView
from .unit_editor_view import UnitEditorView
from .components_db_view import ComponentsDBView
from .unit_config_view import UnitConfigView
from .verification_view import VerificationView
from .export_view import ExportView


class MainWindow(QMainWindow):
    """Main application window with menu bar"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FMEDA Tool")
        
        # Get screen size and calculate appropriate window size (80% of screen)
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        
        # Calculate 80% of screen size while maintaining 16:9 aspect ratio
        target_width = int(screen_width * 0.8)
        target_height = int(target_width * 9 / 16)
        
        # If height exceeds screen, recalculate based on height
        if target_height > screen_height * 0.8:
            target_height = int(screen_height * 0.8)
            target_width = int(target_height * 16 / 9)
        
        # Set window size and minimum size
        self.resize(target_width, target_height)
        self.setMinimumSize(960, 540)  # Minimum 16:9 size
        
        # Center window on screen
        frame_geometry = self.frameGeometry()
        center_point = screen_geometry.center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())
        
        # Current project
        self.current_project: Optional[Project] = None
        self.undo_stack = []
        
        # Track if we're editing a diagnostic measure and which row
        self.editing_diagnostic_measure_row: Optional[int] = None
        
        # Navigation history
        self.navigation_history = []
        self.is_navigating_back = False
        
        # Track unsaved changes
        self.has_unsaved_changes = False
        
        # Create central widget with stacked layout for different views
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Stacked widget to switch between different views
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)
        
        # Setup menu bar (header)
        self._create_menu_bar()
        
        # Store references to views
        self.views = {}
        
        # Create create project view (Page 1)
        self.create_project_view = CreateProjectView()
        self.create_project_view.project_saved.connect(self._on_project_created)
        self.create_project_view.cancel_requested.connect(self._on_create_project_cancelled)
        self.add_view("create_project", self.create_project_view)
        
        # Create unit editor view (Page 2)
        self.unit_editor_view = UnitEditorView()
        self.unit_editor_view.main_window = self
        self.unit_editor_view.save_requested.connect(self._on_save_project_from_editor)
        self.unit_editor_view.back_requested.connect(self._on_fmeda_back)
        self.unit_editor_view.next_requested.connect(self._on_fmeda_next)
        self.add_view("unit_editor", self.unit_editor_view)
        
        # Create verification view (Page 3)
        self.verification_view = VerificationView()
        self.verification_view.back_requested.connect(self._on_verification_back)
        self.verification_view.next_requested.connect(self._on_verification_next)
        self.verification_view.re_verify_requested.connect(self._on_reverify_project)
        self.verification_view.alert_clicked.connect(self._on_verification_alert_clicked)
        self.add_view("verification", self.verification_view)
        
        # Create export view (Page 4)
        self.export_view = ExportView()
        self.export_view.back_requested.connect(self._on_export_back)
        self.export_view.save_requested.connect(self._on_save_project_from_editor)
        self.export_view.finish_requested.connect(self._on_export_finish)
        self.export_view.export_excel_requested.connect(self._on_export_excel)
        self.export_view.export_pdf_requested.connect(self._on_export_pdf)
        self.add_view("export_view", self.export_view)
        
        # Create components database view
        self.components_db_view = ComponentsDBView()
        self.add_view("components_db", self.components_db_view)
        
    def _create_menu_bar(self):
        """Create the menu bar with File, Edit, System, Help menus"""
        menubar = self.menuBar()
        
        # Navigation Menu
        nav_menu = menubar.addMenu("&Navigate")
        
        # Navigate -> Back
        self.back_action = QAction("← &Back", self)
        self.back_action.setShortcut("Alt+Left")
        self.back_action.setStatusTip("Go back to previous view")
        self.back_action.triggered.connect(self._on_back)
        self.back_action.setEnabled(False)  # Disabled initially
        nav_menu.addAction(self.back_action)
        
        # File Menu
        file_menu = menubar.addMenu("&File")
        
        # File -> Home
        home_action = QAction(" &Home", self)
        home_action.setShortcut("Ctrl+H")
        home_action.setStatusTip("Return to main menu")
        home_action.triggered.connect(self._on_home)
        file_menu.addAction(home_action)
        
        file_menu.addSeparator()
        
        # File -> New Project
        new_project_action = QAction("&New Project", self)
        new_project_action.setShortcut("Ctrl+N")
        new_project_action.setStatusTip("Create a new FMEDA project")
        new_project_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_project_action)
        
        # File -> Open Project
        open_project_action = QAction("&Open Project...", self)
        open_project_action.setShortcut("Ctrl+O")
        open_project_action.setStatusTip("Open an existing project")
        open_project_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_project_action)
        
        file_menu.addSeparator()
        
        # File -> Edit Project
        edit_project_action = QAction("&Edit Project...", self)
        edit_project_action.setShortcut("Ctrl+E")
        edit_project_action.setStatusTip("Edit current project settings")
        edit_project_action.triggered.connect(self._on_edit_project)
        file_menu.addAction(edit_project_action)
        
        file_menu.addSeparator()
        
        # File -> Save
        save_action = QAction("&Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.setStatusTip("Save current project")
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)
        
        # File -> Save As
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.setStatusTip("Save project with a new name")
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        # File -> Import
        import_menu = file_menu.addMenu("&Import")
        
        import_pdf_action = QAction("Import PDF...", self)
        import_pdf_action.setStatusTip("Import component data from PDF")
        import_pdf_action.triggered.connect(self._on_import_pdf)
        import_menu.addAction(import_pdf_action)
        
        import_excel_action = QAction("Import Excel...", self)
        import_excel_action.setStatusTip("Import data from Excel file")
        import_excel_action.triggered.connect(self._on_import_excel)
        import_menu.addAction(import_excel_action)
        
        # File -> Export
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
        
        # File -> Recent Projects
        recent_menu = file_menu.addMenu("&Recent Projects")
        # TODO: Populate with recent projects
        no_recent_action = QAction("No recent projects", self)
        no_recent_action.setEnabled(False)
        recent_menu.addAction(no_recent_action)
        
        file_menu.addSeparator()
        
        # File -> Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        
        # Edit -> Undo
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.setStatusTip("Undo last action")
        undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(undo_action)
        
        # Edit -> Redo
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.setStatusTip("Redo last undone action")
        redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        # Edit -> Cut
        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.setStatusTip("Cut selection")
        cut_action.triggered.connect(self._on_cut)
        edit_menu.addAction(cut_action)
        
        # Edit -> Copy
        copy_action = QAction("&Copy", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.setStatusTip("Copy selection")
        copy_action.triggered.connect(self._on_copy)
        edit_menu.addAction(copy_action)
        
        # Edit -> Paste
        paste_action = QAction("&Paste", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.setStatusTip("Paste from clipboard")
        paste_action.triggered.connect(self._on_paste)
        edit_menu.addAction(paste_action)
        
        edit_menu.addSeparator()
        
        # Edit -> Find
        find_action = QAction("&Find...", self)
        find_action.setShortcut("Ctrl+F")
        find_action.setStatusTip("Find in current view")
        find_action.triggered.connect(self._on_find)
        edit_menu.addAction(find_action)
        
        edit_menu.addSeparator()
        
        # Edit -> Preferences
        preferences_action = QAction("&Preferences...", self)
        preferences_action.setStatusTip("Open preferences dialog")
        preferences_action.triggered.connect(self._on_preferences)
        edit_menu.addAction(preferences_action)
        
        # System Menu
        system_menu = menubar.addMenu("&System")
        
        # System -> Project Settings
        project_settings_action = QAction("&Project Settings...", self)
        project_settings_action.setStatusTip("Configure project settings")
        project_settings_action.triggered.connect(self._on_project_settings)
        system_menu.addAction(project_settings_action)
        
        # System -> Units Management
        units_action = QAction("&Units Management...", self)
        units_action.setStatusTip("Manage project units")
        units_action.triggered.connect(self._on_units_management)
        system_menu.addAction(units_action)
        
        # System -> Deviations Management
        deviations_action = QAction("&Deviations Management...", self)
        deviations_action.setStatusTip("Manage deviations")
        deviations_action.triggered.connect(self._on_deviations_management)
        system_menu.addAction(deviations_action)
        
        # System -> Mitigations Management
        mitigations_action = QAction("&Mitigations Management...", self)
        mitigations_action.setStatusTip("Manage mitigations")
        mitigations_action.triggered.connect(self._on_mitigations_management)
        system_menu.addAction(mitigations_action)
        
        system_menu.addSeparator()
        
        # System -> Database
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
        
        # System -> FMEDA Analysis
        analysis_action = QAction("&Run FMEDA Analysis...", self)
        analysis_action.setShortcut("F5")
        analysis_action.setStatusTip("Run FMEDA analysis on current project")
        analysis_action.triggered.connect(self._on_run_analysis)
        system_menu.addAction(analysis_action)
        
        # Help Menu
        help_menu = menubar.addMenu("&Help")
        
        # Help -> Documentation
        docs_action = QAction("&Documentation", self)
        docs_action.setShortcut("F1")
        docs_action.setStatusTip("Open documentation")
        docs_action.triggered.connect(self._on_documentation)
        help_menu.addAction(docs_action)
        
        # Help -> User Guide
        guide_action = QAction("&User Guide", self)
        guide_action.setStatusTip("Open user guide")
        guide_action.triggered.connect(self._on_user_guide)
        help_menu.addAction(guide_action)
        
        help_menu.addSeparator()
        
        # Help -> About
        about_action = QAction("&About FMEDA Tool", self)
        about_action.setStatusTip("Show information about this application")
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
        
        # Help -> Check for Updates
        updates_action = QAction("Check for &Updates...", self)
        updates_action.setStatusTip("Check for application updates")
        updates_action.triggered.connect(self._on_check_updates)
        help_menu.addAction(updates_action)
    
    # File Menu Actions
    def _on_new_project(self):
        """Handle File -> New Project"""
        # Reset the form
        self.create_project_view.reset_form()
        
        # Add to views if not already added
        if "create_project" not in self.views:
            self.add_view("create_project", self.create_project_view)
        
        # Show the create project view
        self.show_view("create_project")
    
    def _on_edit_project(self):
        """Handle File -> Edit Project"""
        if not self.current_project:
            QMessageBox.warning(
                self,
                "No Project Open",
                "Please create or open a project first before editing."
            )
            return
        
        # Convert project to dict for loading
        project_dict = self.current_project.model_dump(mode='json')
        
        # Load project into the form
        self.create_project_view.load_project(project_dict)
        
        # Add to views if not already added
        if "create_project" not in self.views:
            self.add_view("create_project", self.create_project_view)
        
        # Show the create project view
        self.show_view("create_project")
    
    def _on_project_created(self, project: Project):
        """Handle project creation"""
        self.current_project = project
        self.setWindowTitle(f"FMEDA Tool - {project.name}")
        
        # Newly created project has unsaved changes until saved to disk
        self.has_unsaved_changes = True
        
        print(f"✓ Project created: {project.name}")
        print(f"  ID: {project.id}")
        print(f"  Version: {project.version}")
        
        # Load project into the main workspace (Page 2)
        self.unit_editor_view.load_project(project)
        
        # Navigate directly to Page 2
        self.show_view("unit_editor")
    
    def _on_create_project_cancelled(self):
        """Handle cancel from create project view"""
        # Navigate back to main menu
        self.show_view("main_menu")
        
    def _on_open_project(self):
        """Handle File -> Open Project"""
        # Open file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "data/projects",
            "JSON Files (*.json);;All Files (*.*)"
        )
        
        if not file_path:
            return  # User cancelled
        
        try:
            from fmeda_tool.services.project_service import ProjectService
            
            # Load and migrate project using service
            project, was_migrated, migration_msg = ProjectService.load_and_migrate_project(file_path)
            self.current_project = project
            
            # Show migration notification if needed
            if was_migrated:
                QMessageBox.information(
                    self,
                    "Project Schema Migrated",
                    migration_msg
                )
            
            # Update window title
            self.setWindowTitle(f"FMEDA Tool - {self.current_project.name}")
            
            # Show success message
            QMessageBox.information(
                self,
                "Project Opened",
                f"Project '{self.current_project.name}' opened successfully!"
            )
            
            # Load project into editor and navigate there
            self.unit_editor_view.load_project(self.current_project)
            
            # Restore active tab if saved
            if self.current_project.last_active_tab_id:
                if self.current_project.last_active_tab_id == "overview":
                    self.unit_editor_view.unit_tabs.setCurrentIndex(0)
                else:
                    for tab_idx in range(1, self.unit_editor_view.unit_tabs.count()):
                        widget = self.unit_editor_view.unit_tabs.widget(tab_idx)
                        if hasattr(widget, "unit") and widget.unit.id == self.current_project.last_active_tab_id:
                            self.unit_editor_view.unit_tabs.setCurrentIndex(tab_idx)
                            break
            
            # Add to views if not already added
            if "unit_editor" not in self.views:
                self.add_view("unit_editor", self.unit_editor_view)
            
            # Show the editor
            self.show_view("unit_editor")
            
            # No unsaved changes after opening
            self.has_unsaved_changes = False
            
            print(f"✓ Project opened: {self.current_project.name}")
            print(f"  ID: {self.current_project.id}")
            print(f"  Version: {self.current_project.version}")
            print(f"  Units: {len(self.current_project.units)}")
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Opening Project",
                f"Failed to open project:\n{str(e)}"
            )
            print(f"✗ Error opening project: {e}")
        
    def _on_save(self):
        """Handle File -> Save"""
        self._on_save_project_from_editor()
        
    def _on_save_as(self):
        """Handle File -> Save As"""
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
            # Update timestamp
            from datetime import datetime
            self.current_project.updated_at = datetime.now()
            
            # Save the active tab ID
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
        """Handle File -> Import -> PDF"""
        print("Import PDF clicked")
        # TODO: Implement PDF import
        
    def _on_import_excel(self):
        """Handle File -> Import -> Excel"""
        print("Import Excel clicked")
        # TODO: Implement Excel import
        
    def _on_export_excel(self):
        """Handle File -> Export -> Excel"""
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
        """Handle File -> Export -> PDF"""
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
            
        # Append .pdf if omitted
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
        """Handle File -> Export -> JSON"""
        print("Export to JSON clicked")
        # TODO: Implement JSON export
    
    # Edit Menu Actions
    def push_undo_state(self, action_desc: str):
        if self.current_project is not None:
            # Serialize the current project state (before modification)
            project_dump = self.current_project.model_dump()
            self.undo_stack.append((project_dump, action_desc))
            
            # Limit the size of the stack
            if len(self.undo_stack) > 50:
                self.undo_stack.pop(0)
                
            # Enable undo button and update its tooltip
            self.unit_editor_view.undo_btn.setEnabled(True)
            self.unit_editor_view.undo_btn.setToolTip(f"Undo: {action_desc}")
            
            # Mark unsaved changes
            self.has_unsaved_changes = True

    def _on_undo(self):
        """Handle Edit -> Undo"""
        if not self.undo_stack:
            return
            
        # Pop the last state
        project_dump, action_desc = self.undo_stack.pop()
        
        # Restore the project from the serialized dump
        self.current_project = Project.model_validate(project_dump)
        
        # Recalculate
        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.current_project)
        
        # Update editor project reference and load it
        self.unit_editor_view.load_project(self.current_project)
        
        # Update undo button state and tooltip
        if self.undo_stack:
            next_action_desc = self.undo_stack[-1][1]
            self.unit_editor_view.undo_btn.setEnabled(True)
            self.unit_editor_view.undo_btn.setToolTip(f"Undo: {next_action_desc}")
        else:
            self.unit_editor_view.undo_btn.setEnabled(False)
            self.unit_editor_view.undo_btn.setToolTip("Nothing to undo")
            
        # Set unsaved changes to true when undoing
        self.has_unsaved_changes = True
        
    def _on_redo(self):
        """Handle Edit -> Redo"""
        print("Redo clicked")
        # TODO: Implement redo functionality
        
    def _on_cut(self):
        """Handle Edit -> Cut"""
        print("Cut clicked")
        # TODO: Implement cut functionality
        
    def _on_copy(self):
        """Handle Edit -> Copy"""
        print("Copy clicked")
        # TODO: Implement copy functionality
        
    def _on_paste(self):
        """Handle Edit -> Paste"""
        print("Paste clicked")
        # TODO: Implement paste functionality
        
    def _on_find(self):
        """Handle Edit -> Find"""
        print("Find clicked")
        # TODO: Implement find dialog
        
    def _on_preferences(self):
        """Handle Edit -> Preferences"""
        print("Preferences clicked")
        # TODO: Implement preferences dialog
    
    # System Menu Actions
    def _on_project_settings(self):
        """Handle System -> Project Settings"""
        print("Project Settings clicked")
        # TODO: Implement project settings dialog
        
    def _on_units_management(self):
        """Handle System -> Units Management (Open Editor)"""
        if not self.current_project:
            QMessageBox.warning(
                self,
                "No Project Open",
                "Please create or open a project first before managing units."
            )
            return
        
        # Load project into editor
        self.unit_editor_view.load_project(self.current_project)
        
        # Add to views if not already added
        if "unit_editor" not in self.views:
            self.add_view("unit_editor", self.unit_editor_view)
        
        # Show the editor
        self.show_view("unit_editor")
    
    def _on_save_project_from_editor(self):
        """Handle save request from editor"""
        if not self.current_project:
            return
        
        try:
            # Save to JSON file
            data_dir = Path("data/projects")
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename from project name
            filename = f"{self.current_project.id}_{self.current_project.name.replace(' ', '_')}.json"
            filepath = data_dir / filename
            
            # Update timestamp
            from datetime import datetime
            self.current_project.updated_at = datetime.now()
            
            # Save the active tab ID
            active_idx = self.unit_editor_view.unit_tabs.currentIndex()
            if active_idx == 0:
                self.current_project.last_active_tab_id = "overview"
            else:
                if self.current_project.units and active_idx - 1 < len(self.current_project.units):
                    self.current_project.last_active_tab_id = self.current_project.units[active_idx - 1].id
            
            # Save atomically
            from fmeda_tool.services.project_service import ProjectService
            ProjectService.save_project_atomically(self.current_project, str(filepath))
            
            # Mark as saved
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
            print(f"✗ Error saving project: {e}")
    
    def _on_fmeda_back(self):
        """Handle Back clicked on Page 2 -> Page 1"""
        self.show_view("create_project")
        
    def _on_fmeda_next(self):
        """Handle Next clicked on Page 2 -> Page 3"""
        if not self.current_project:
            return
        self.verification_view.load_project(self.current_project)
        self.show_view("verification")
        
    def _on_verification_back(self):
        """Handle Back clicked on Page 3 -> Page 2"""
        self.show_view("unit_editor")
        
    def _on_verification_next(self):
        """Handle Next clicked on Page 3 -> Page 4"""
        if not self.current_project:
            return
        self.export_view.load_project(self.current_project, is_dirty=self.has_unsaved_changes)
        self.show_view("export_view")
        
    def _on_reverify_project(self):
        """Handle Re-Verify clicked on Page 3"""
        self.verification_view.refresh_validation()
        
    def _on_verification_alert_clicked(self, unit_id: str, row_index: int):
        """Handle clicking validation alert -> Jump to Page 2 row"""
        self.show_view("unit_editor")
        self.unit_editor_view.focus_unit_row(unit_id, row_index)
        
    def _on_export_back(self):
        """Handle Back clicked on Page 4 -> Page 3"""
        self.show_view("verification")
        
    def _on_export_finish(self):
        """Handle Finish clicked on Page 4 -> Start Page"""
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
        """Handle System -> Deviations Management"""
        print("Deviations Management clicked")
        # TODO: Implement deviations management view
        
    def _on_mitigations_management(self):
        """Handle System -> Mitigations Management"""
        print("Mitigations Management clicked")
        # TODO: Implement mitigations management view
        
    def _on_backup_database(self):
        """Handle System -> Database -> Backup"""
        print("Backup Database clicked")
        # TODO: Implement database backup
        
    def _on_restore_database(self):
        """Handle System -> Database -> Restore"""
        print("Restore Database clicked")
        # TODO: Implement database restore
        
    def _on_run_analysis(self):
        """Handle System -> Run FMEDA Analysis"""
        print("Run FMEDA Analysis clicked")
        # TODO: Implement FMEDA analysis
    
    # Help Menu Actions
    def _on_documentation(self):
        """Handle Help -> Documentation"""
        print("Documentation clicked")
        # TODO: Open documentation
    
    def _on_components_db(self):
        """Handle Components Database"""
        # Add to views if not already added
        if "components_db" not in self.views:
            self.add_view("components_db", self.components_db_view)
        
        # Show the components database view
        self.show_view("components_db")
        
    def _on_user_guide(self):
        """Handle Help -> User Guide"""
        print("User Guide clicked")
        # TODO: Open user guide
        
    def _on_about(self):
        """Handle Help -> About"""
        QMessageBox.about(
            self,
            "About FMEDA Tool",
            "<h2>FMEDA Tool</h2>"
            "<p>Version 1.0.0</p>"
            "<p>Failure Mode, Effects and Diagnostic Analysis Tool</p>"
            "<p>Copyright © 2026</p>"
        )
        
    def _on_check_updates(self):
        """Handle Help -> Check for Updates"""
        print("Check for Updates clicked")
        # TODO: Implement update check
    
    def add_view(self, name: str, widget: QWidget):
        """Add a view to the stacked widget"""
        self.views[name] = widget
        self.stacked_widget.addWidget(widget)
    
    def show_view(self, name: str):
        """Switch to a specific view"""
        if name in self.views:
            # Track navigation history (but not when going back)
            if not self.is_navigating_back:
                # Get current view name before switching
                current_widget = self.stacked_widget.currentWidget()
                current_view_name = None
                for view_name, widget in self.views.items():
                    if widget == current_widget:
                        current_view_name = view_name
                        break
                
                # Only add to history if we're switching to a different view
                if current_view_name and current_view_name != name:
                    self.navigation_history.append(current_view_name)
                    # Enable back button
                    self.back_action.setEnabled(True)
            
            self.stacked_widget.setCurrentWidget(self.views[name])
            self.is_navigating_back = False
        else:
            print(f"Warning: View '{name}' not found")
    
    def get_current_view(self) -> QWidget:
        """Get the currently active view"""
        return self.stacked_widget.currentWidget()
    
    def _on_back(self):
        """Navigate back to previous view"""
        if self.navigation_history:
            # Pop the last view from history
            previous_view = self.navigation_history.pop()
            
            # Disable back button if no more history
            if not self.navigation_history:
                self.back_action.setEnabled(False)
            
            # Set flag to prevent adding to history during navigation
            self.is_navigating_back = True
            
            # Switch to previous view
            self.show_view(previous_view)
    
    def _on_home(self):
        """Navigate to home (main menu) with unsaved changes check"""
        # Check for unsaved changes
        if self.has_unsaved_changes and self.current_project:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"You have unsaved changes in project '{self.current_project.name}'.\n\nDo you want to save before returning to the main menu?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Save the project first
                self._on_save_project_from_editor()
                # Then go home
                self.show_view("main_menu")
            elif reply == QMessageBox.StandardButton.No:
                # Don't save, just go home
                self.has_unsaved_changes = False
                self.show_view("main_menu")
            # If Cancel, do nothing
        else:
            # No unsaved changes, go directly to home
            self.show_view("main_menu")
