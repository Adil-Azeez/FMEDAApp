from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QFileDialog, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional
from pathlib import Path

from fmeda_tool.models import Project


class ExportView(QWidget):
    """Page 4: Export project report to Excel/PDF and finish workflow"""
    
    back_requested = pyqtSignal()
    save_requested = pyqtSignal()
    finish_requested = pyqtSignal()
    export_excel_requested = pyqtSignal()
    export_pdf_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.project: Optional[Project] = None
        self._setup_ui()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        self._create_header()
        main_layout.addWidget(self.header_frame)
        
        # Main Container
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(25)
        main_layout.addWidget(container)
        
        # Title
        title_lbl = QLabel("Page 4: Export Results")
        title_lbl.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(title_lbl)
        
        # Status Box
        self.status_box = QFrame()
        self.status_box.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; border-radius: 4px; padding: 20px;")
        status_layout = QVBoxLayout(self.status_box)
        status_layout.setSpacing(10)
        
        self.save_status_lbl = QLabel("Project File Status: Unsaved changes present.")
        self.save_status_lbl.setFont(QFont("Arial", 11))
        status_layout.addWidget(self.save_status_lbl)
        
        self.file_path_lbl = QLabel("Saved Location: Not saved yet.")
        self.file_path_lbl.setFont(QFont("Arial", 10))
        self.file_path_lbl.setStyleSheet("color: #6c757d;")
        status_layout.addWidget(self.file_path_lbl)
        
        layout.addWidget(self.status_box)
        
        # Options box
        opt_box = QFrame()
        opt_box.setStyleSheet("background-color: #ffffff; border: 1px solid #dee2e6; border-radius: 4px; padding: 20px;")
        opt_lay = QVBoxLayout(opt_box)
        opt_lay.setSpacing(12)
        
        opt_title = QLabel("<b>Export Options:</b>")
        opt_lay.addWidget(opt_title)
        
        self.opt_fmeda_sheets = QCheckBox("One FMEDA worksheet per Functional Group Tab (Recommended)")
        self.opt_fmeda_sheets.setChecked(True)
        opt_lay.addWidget(self.opt_fmeda_sheets)
        
        self.opt_summary_sheet = QCheckBox("Include Project Parameters & Safety Metrics Overview")
        self.opt_summary_sheet.setChecked(True)
        opt_lay.addWidget(self.opt_summary_sheet)
        
        self.opt_custom_fields = QCheckBox("Include Custom Project Fields")
        self.opt_custom_fields.setChecked(True)
        opt_lay.addWidget(self.opt_custom_fields)
        
        self.opt_change_history = QCheckBox("Include Change History Log")
        self.opt_change_history.setChecked(True)
        opt_lay.addWidget(self.opt_change_history)
        
        layout.addWidget(opt_box)
        
        # Big Action Button
        self.big_export_btn = QPushButton("📊 Export Project to formatted Excel workbook")
        self.big_export_btn.setStyleSheet("""
            background-color: #198754; 
            color: white; 
            font-size: 14px; 
            font-weight: bold; 
            padding: 15px 30px; 
            border-radius: 6px;
        """)
        self.big_export_btn.clicked.connect(self._on_big_export_clicked)
        layout.addWidget(self.big_export_btn)
        
        # PDF Action Button
        self.pdf_export_btn = QPushButton("📄 Export Project to PDF Report")
        self.pdf_export_btn.setStyleSheet("""
            background-color: #dc3545; 
            color: white; 
            font-size: 14px; 
            font-weight: bold; 
            padding: 15px 30px; 
            border-radius: 6px;
        """)
        self.pdf_export_btn.clicked.connect(self._on_pdf_export_clicked)
        layout.addWidget(self.pdf_export_btn)
        
        layout.addStretch()
        
        # Navigation Bar
        self._create_navigation_bar(main_layout)
        
    def _create_header(self):
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet("background-color: #f8f9fa; border-bottom: 2px solid #dee2e6;")
        self.header_frame.setFixedHeight(60)
        
        layout = QHBoxLayout(self.header_frame)
        layout.setContentsMargins(30, 10, 30, 10)
        
        self.project_name_label = QLabel("Untitled Project")
        font_name = QFont("Arial", 12, QFont.Weight.Bold)
        self.project_name_label.setFont(font_name)
        self.project_name_label.setStyleSheet("color: #495057;")
        layout.addWidget(self.project_name_label)
        
        layout.addStretch()
        
        title_lbl = QLabel("Page 4: Export Results")
        title_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #212529;")
        layout.addWidget(title_lbl)
        
        layout.addStretch()
        
    def _create_navigation_bar(self, parent_layout):
        nav_frame = QFrame()
        nav_frame.setStyleSheet("background-color: #f8f9fa; border-top: 1px solid #dee2e6;")
        nav_frame.setFixedHeight(60)
        
        layout = QHBoxLayout(nav_frame)
        layout.setContentsMargins(30, 10, 30, 10)
        
        self.back_btn = QPushButton("Back")
        self.back_btn.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 6px 15px;")
        self.back_btn.clicked.connect(self._on_back)
        layout.addWidget(self.back_btn)
        
        layout.addStretch()
        
        self.save_project_btn = QPushButton("Save Project")
        self.save_project_btn.setStyleSheet("background-color: #ffc107; color: black; font-weight: bold; padding: 6px 20px;")
        self.save_project_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_project_btn)
        
        self.finish_btn = QPushButton("Finish")
        self.finish_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 25px;")
        self.finish_btn.clicked.connect(self._on_finish)
        layout.addWidget(self.finish_btn)
        
        parent_layout.addWidget(nav_frame)
        
    def _on_back(self):
        self.back_requested.emit()
        
    def _on_save(self):
        self.save_requested.emit()
        
    def _on_finish(self):
        self.finish_requested.emit()
        
    def _on_big_export_clicked(self):
        self.export_excel_requested.emit()
        
    def _on_pdf_export_clicked(self):
        self.export_pdf_requested.emit()
        
    def load_project(self, project: Project, is_dirty=True):
        self.project = project
        self.project_name_label.setText(project.name)
        
        if is_dirty:
            self.save_status_lbl.setText("Project File Status: 🟡 Unsaved changes present.")
            self.save_status_lbl.setStyleSheet("color: #ffc107; font-weight: bold;")
        else:
            self.save_status_lbl.setText("Project File Status: 🟢 Project is saved up to date.")
            self.save_status_lbl.setStyleSheet("color: #198754; font-weight: bold;")
            
        data_dir = Path("data/projects")
        filename = f"{project.id}_{project.name.replace(' ', '_')}.json"
        filepath = data_dir / filename
        if filepath.exists():
            self.file_path_lbl.setText(f"Saved Location: {filepath.absolute()}")
        else:
            self.file_path_lbl.setText("Saved Location: Not saved on disk yet.")
            
    def update_save_status(self, is_dirty: bool):
        if is_dirty:
            self.save_status_lbl.setText("Project File Status: 🟡 Unsaved changes present.")
            self.save_status_lbl.setStyleSheet("color: #ffc107; font-weight: bold;")
        else:
            self.save_status_lbl.setText("Project File Status: 🟢 Project is saved up to date.")
            self.save_status_lbl.setStyleSheet("color: #198754; font-weight: bold;")
            
        if self.project:
            data_dir = Path("data/projects")
            filename = f"{self.project.id}_{self.project.name.replace(' ', '_')}.json"
            filepath = data_dir / filename
            if filepath.exists():
                self.file_path_lbl.setText(f"Saved Location: {filepath.absolute()}")
            else:
                self.file_path_lbl.setText("Saved Location: Not saved on disk yet.")
