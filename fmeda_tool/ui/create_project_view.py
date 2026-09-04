from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QFrame, QDoubleSpinBox, QMessageBox, QStackedWidget,
    QDialog, QDialogButtonBox, QCheckBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, Dict, List
import uuid
import json
from datetime import datetime
from pathlib import Path

from fmeda_tool.models import (
    Project, ProjectStatus, SafetyStandard, SafetyContext, SourceDocument, Unit
)


class DocumentDialog(QDialog):
    """Dialog to add/edit source documents"""
    
    def __init__(self, doc: Optional[SourceDocument] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Source Document" if doc is None else "Edit Source Document")
        self.setMinimumWidth(500)
        self.doc = doc
        self._setup_ui()
        if self.doc:
            self._load_data()
            
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "BOM", "Schematic", "Safety Concept", "Requirements",
            "Existing FMEDA", "Reliability Database", "Test Specification", "Other"
        ])
        form_layout.addRow("Document Type*:", self.type_combo)
        
        self.number_input = QLineEdit()
        form_layout.addRow("Document Number*:", self.number_input)
        
        self.name_input = QLineEdit()
        form_layout.addRow("Document Name*:", self.name_input)
        
        self.version_input = QLineEdit()
        self.version_input.setText("1.0")
        form_layout.addRow("Version:", self.version_input)
        
        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("YYYY-MM-DD")
        form_layout.addRow("Date:", self.date_input)
        
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        path_layout.addWidget(browse_btn)
        form_layout.addRow("Local File Path:", path_layout)
        
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80)
        form_layout.addRow("Notes:", self.notes_input)
        
        layout.addLayout(form_layout)
        
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Document File", "", "All Files (*.*)")
        if path:
            self.path_input.setText(path)
            
    def _on_accept(self):
        if not self.number_input.text().strip() or not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Document Number and Name are required.")
            return
        
        self.doc = SourceDocument(
            document_type=self.type_combo.currentText(),
            document_number=self.number_input.text().strip(),
            document_name=self.name_input.text().strip(),
            version=self.version_input.text().strip() or "1.0",
            date=self.date_input.text().strip() or None,
            local_file_path=self.path_input.text().strip() or None,
            notes=self.notes_input.toPlainText().strip() or None
        )
        self.accept()
        
    def _load_data(self):
        if not self.doc:
            return
        self.type_combo.setCurrentText(self.doc.document_type)
        self.number_input.setText(self.doc.document_number)
        self.name_input.setText(self.doc.document_name)
        self.version_input.setText(self.doc.version)
        self.date_input.setText(self.doc.date or "")
        self.path_input.setText(self.doc.local_file_path or "")
        self.notes_input.setPlainText(self.doc.notes or "")


class CreateProjectView(QWidget):
    """Page 1: Project Information configuration view"""
    
    project_saved = pyqtSignal(Project)
    cancel_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.project: Optional[Project] = None
        self.source_docs: List[SourceDocument] = []
        self.functional_groups: List[Unit] = []
        self.edit_mode: bool = False
        self._setup_ui()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        self._create_header()
        main_layout.addWidget(self.header_frame)
        
        # Scroll Area for Form fields
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(scroll)
        
        widget = QWidget()
        self.form_layout = QVBoxLayout(widget)
        self.form_layout.setContentsMargins(40, 20, 40, 20)
        self.form_layout.setSpacing(15)
        scroll.setWidget(widget)
        
        # Required Section
        req_label = QLabel("Page 1: Required Project Information")
        req_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.form_layout.addWidget(req_label)
        
        self.form = QFormLayout()
        self.form.setSpacing(10)
        
        self.name_input = QLineEdit()
        self.name_input.textChanged.connect(self._update_header_name)
        self.form.addRow("Project Name*:", self.name_input)
        
        self.number_input = QLineEdit()
        self.form.addRow("Project Number*:", self.number_input)
        
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(60)
        self.form.addRow("Description*:", self.description_input)
        
        self.version_input = QLineEdit()
        self.version_input.setText("1.0.0")
        self.form.addRow("Project Version:", self.version_input)
        
        self.created_by_input = QLineEdit()
        self.form.addRow("Created By:", self.created_by_input)
        
        self.organization_input = QLineEdit()
        self.form.addRow("Organization:", self.organization_input)
        
        self.standard_combo = QComboBox()
        self.standard_combo.addItems([standard.value for standard in SafetyStandard])
        self.form.addRow("Safety Standard:", self.standard_combo)
        
        self.target_sil_combo = QComboBox()
        self.target_sil_combo.addItems(["SIL 1", "SIL 2", "SIL 3", "SIL 4"])
        self.target_sil_combo.setCurrentIndex(1)  # Default SIL 2
        self.form.addRow("Target SIL:", self.target_sil_combo)
        
        self.product_name_input = QLineEdit()
        self.form.addRow("Product Name:", self.product_name_input)
        
        self.product_group_input = QLineEdit()
        self.form.addRow("Product Group:", self.product_group_input)
        
        self.product_version_input = QLineEdit()
        self.form.addRow("Product Version:", self.product_version_input)
        
        # Mission / Proof / Diag spinboxes
        mission_layout = QHBoxLayout()
        self.mission_time_input = QDoubleSpinBox()
        self.mission_time_input.setRange(1, 1000000)
        self.mission_time_input.setValue(87600)  # Default 10 years
        self.mission_time_input.valueChanged.connect(self._update_mission_label)
        mission_layout.addWidget(self.mission_time_input)
        self.mission_years_label = QLabel("(10.0 years)")
        mission_layout.addWidget(self.mission_years_label)
        self.form.addRow("Mission Time (hours):", mission_layout)
        
        test_layout = QHBoxLayout()
        self.test_interval_input = QDoubleSpinBox()
        self.test_interval_input.setRange(1, 1000000)
        self.test_interval_input.setValue(8760)  # Default 1 year
        self.test_interval_input.valueChanged.connect(self._update_test_label)
        test_layout.addWidget(self.test_interval_input)
        self.test_years_label = QLabel("(1.0 years)")
        test_layout.addWidget(self.test_years_label)
        self.form.addRow("Proof Test Interval (hours):", test_layout)
        
        self.diagnostic_interval_input = QDoubleSpinBox()
        self.diagnostic_interval_input.setRange(0.01, 100000)
        self.diagnostic_interval_input.setValue(1.0)
        self.diagnostic_interval_input.setSuffix(" hours")
        self.form.addRow("Diagnostic Test Interval:", self.diagnostic_interval_input)
        
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Draft", "In Progress", "Under Review", "Completed", "Archived"])
        self.form.addRow("Project Status:", self.status_combo)
        
        self.reviewer_input = QLineEdit()
        self.form.addRow("Reviewer Name:", self.reviewer_input)
        
        # Custom Fields Table
        custom_layout = QVBoxLayout()
        self.custom_fields_table = QTableWidget()
        self.custom_fields_table.setColumnCount(3)
        self.custom_fields_table.setHorizontalHeaderLabels(["Field Name", "Field Value", "Actions"])
        self.custom_fields_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.custom_fields_table.setMaximumHeight(150)
        custom_layout.addWidget(self.custom_fields_table)
        
        add_custom_btn = QPushButton("+ Add Custom Field")
        add_custom_btn.clicked.connect(self._add_custom_field)
        custom_layout.addWidget(add_custom_btn)
        self.form.addRow("Custom Project Fields:", custom_layout)
        
        self.form_layout.addLayout(self.form)
        
        # Expandable Optional / Safety Context Section
        self.toggle_optional_btn = QPushButton("▼ Show Optional & Safety Context Information")
        self.toggle_optional_btn.setStyleSheet("background-color: #e9ecef; font-weight: bold; padding: 6px;")
        self.toggle_optional_btn.setCheckable(True)
        self.toggle_optional_btn.setChecked(False)
        self.toggle_optional_btn.clicked.connect(self._on_toggle_optional)
        self.form_layout.addWidget(self.toggle_optional_btn)
        
        self.optional_frame = QFrame()
        self.optional_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.optional_frame.setStyleSheet("QFrame { background-color: #fcfcfc; border: 1px solid #dee2e6; border-radius: 4px; }")
        self.optional_frame.setVisible(False)
        
        opt_layout = QVBoxLayout(self.optional_frame)
        opt_form = QFormLayout()
        
        self.safety_fn_name = QLineEdit()
        opt_form.addRow("Safety Function Name:", self.safety_fn_name)
        
        self.safety_fn_desc = QTextEdit()
        self.safety_fn_desc.setMaximumHeight(60)
        opt_form.addRow("Safety Function Desc:", self.safety_fn_desc)
        
        self.safe_state = QLineEdit()
        opt_form.addRow("Safe State Definition:", self.safe_state)
        
        self.dangerous_state = QLineEdit()
        opt_form.addRow("Dangerous State Definition:", self.dangerous_state)
        
        self.no_part_failure_def = QTextEdit()
        self.no_part_failure_def.setMaximumHeight(60)
        self.no_part_failure_def.setPlaceholderText("Enter the project-specific definition and criteria for a No Part Failure...")
        opt_form.addRow("No Part Failure Definition:", self.no_part_failure_def)
        
        self.no_effect_failure_def = QTextEdit()
        self.no_effect_failure_def.setMaximumHeight(60)
        self.no_effect_failure_def.setPlaceholderText("Enter the project-specific definition and criteria for a No Effect Failure...")
        opt_form.addRow("No Effect Failure Definition:", self.no_effect_failure_def)
        
        self.architecture_combo = QComboBox()
        self.architecture_combo.addItems(["1oo1", "1oo1D", "1oo2", "1oo2D", "2oo2", "2oo3", "Other"])
        opt_form.addRow("Safety Architecture:", self.architecture_combo)
        
        self.operating_mode_combo = QComboBox()
        self.operating_mode_combo.addItems(["Low demand mode", "High demand mode", "Continuous mode"])
        opt_form.addRow("Operating Mode:", self.operating_mode_combo)
        
        self.boundary_input = QTextEdit()
        self.boundary_input.setMaximumHeight(60)
        opt_form.addRow("Safety Boundary Definition:", self.boundary_input)
        
        self.sensor_included = QComboBox()
        self.sensor_included.addItems(["No", "Yes"])
        opt_form.addRow("External Sensor Included:", self.sensor_included)
        
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"])
        opt_form.addRow("Exida Reliability Profile*:", self.profile_combo)
        
        self.rel_db_source = QLineEdit()
        self.rel_db_source.setPlaceholderText("e.g. SN 29500, IEC 62380...")
        opt_form.addRow("Reliability DB Source:", self.rel_db_source)
        
        self.env_profile = QLineEdit()
        self.env_profile.setPlaceholderText("e.g. GB (Ground Benign), GF...")
        opt_form.addRow("Environmental Profile:", self.env_profile)
        
        # Source Documents Table
        sources_layout = QVBoxLayout()
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(4)
        self.sources_table.setHorizontalHeaderLabels(["Type", "Number", "Name", "Actions"])
        self.sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sources_table.setMaximumHeight(150)
        sources_layout.addWidget(self.sources_table)
        
        add_source_btn = QPushButton("+ Add Source Document Reference")
        add_source_btn.clicked.connect(self._add_source_doc)
        sources_layout.addWidget(add_source_btn)
        opt_form.addRow("Source Documents:", sources_layout)
        
        self.safety_notes = QTextEdit()
        self.safety_notes.setMaximumHeight(80)
        opt_form.addRow("Safety Context Notes:", self.safety_notes)
        
        opt_layout.addLayout(opt_form)
        self.form_layout.addWidget(self.optional_frame)
        
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
        
        title_lbl = QLabel("Page 1: Project Information")
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
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 6px 15px;")
        self.cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_btn)
        
        layout.addStretch()
        
        self.next_btn = QPushButton("Next")
        self.next_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 25px;")
        self.next_btn.clicked.connect(self._on_next)
        layout.addWidget(self.next_btn)
        
        parent_layout.addWidget(nav_frame)
        
    def _on_toggle_optional(self, checked):
        if checked:
            self.toggle_optional_btn.setText("▲ Hide Optional & Safety Context Information")
            self.optional_frame.setVisible(True)
        else:
            self.toggle_optional_btn.setText("▼ Show Optional & Safety Context Information")
            self.optional_frame.setVisible(False)
            
    def _update_header_name(self, text: str):
        if text.strip():
            self.project_name_label.setText(text.strip())
        else:
            self.project_name_label.setText("Untitled Project")
            
    def _update_mission_label(self, val):
        self.mission_years_label.setText(f"({val / 8760.0:.1f} years)")
        
    def _update_test_label(self, val):
        self.test_years_label.setText(f"({val / 8760.0:.1f} years)")
        
    def _add_custom_field(self):
        row = self.custom_fields_table.rowCount()
        self.custom_fields_table.insertRow(row)
        self.custom_fields_table.setItem(row, 0, QTableWidgetItem(f"Field_{row+1}"))
        self.custom_fields_table.setItem(row, 1, QTableWidgetItem(""))
        
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(lambda: self.custom_fields_table.removeRow(self.custom_fields_table.currentRow()))
        self.custom_fields_table.setCellWidget(row, 2, del_btn)
        
    def _add_source_doc(self):
        dialog = DocumentDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.doc:
            self.source_docs.append(dialog.doc)
            self._refresh_sources_table()
            
    def _edit_source_doc(self, idx: int):
        dialog = DocumentDialog(self.source_docs[idx], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.doc:
            self.source_docs[idx] = dialog.doc
            self._refresh_sources_table()
            
    def _delete_source_doc(self, idx: int):
        self.source_docs.pop(idx)
        self._refresh_sources_table()
        
    def _refresh_sources_table(self):
        self.sources_table.setRowCount(0)
        for idx, doc in enumerate(self.source_docs):
            row = self.sources_table.rowCount()
            self.sources_table.insertRow(row)
            self.sources_table.setItem(row, 0, QTableWidgetItem(doc.document_type))
            self.sources_table.setItem(row, 1, QTableWidgetItem(doc.document_number))
            self.sources_table.setItem(row, 2, QTableWidgetItem(doc.document_name))
            
            actions = QWidget()
            lay = QHBoxLayout(actions)
            lay.setContentsMargins(2, 2, 2, 2)
            
            edit = QPushButton("Edit")
            edit.clicked.connect(lambda checked, i=idx: self._edit_source_doc(i))
            lay.addWidget(edit)
            
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda checked, i=idx: self._delete_source_doc(i))
            lay.addWidget(delete)
            
            self.sources_table.setCellWidget(row, 3, actions)
            
    def _validate_page(self) -> bool:
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Project Name is required.")
            return False
        if not self.number_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Project Number is required.")
            return False
        if not self.description_input.toPlainText().strip():
            QMessageBox.warning(self, "Validation Error", "Description is required.")
            return False
        return True
        
    def _on_next(self):
        if not self._validate_page():
            return
            
        # Compile model
        custom_fields = {}
        for r in range(self.custom_fields_table.rowCount()):
            k = self.custom_fields_table.item(r, 0)
            v = self.custom_fields_table.item(r, 1)
            if k and k.text().strip():
                custom_fields[k.text().strip()] = v.text().strip() if v else ""
                
        sc = SafetyContext(
            safety_function_name=self.safety_fn_name.text().strip(),
            safety_function_description=self.safety_fn_desc.toPlainText().strip(),
            safe_state=self.safe_state.text().strip(),
            dangerous_state=self.dangerous_state.text().strip(),
            no_part_failure_definition=self.no_part_failure_def.toPlainText().strip() or None,
            no_effect_failure_definition=self.no_effect_failure_def.toPlainText().strip() or None,
            safety_architecture=self.architecture_combo.currentText(),
            operating_mode=self.operating_mode_combo.currentText(),
            safety_boundary=self.boundary_input.toPlainText().strip(),
            external_sensor_included=(self.sensor_included.currentText() == "Yes"),
            notes=self.safety_notes.toPlainText().strip() or None
        )
        
        status_map = {
            "Draft": ProjectStatus.DRAFT,
            "In Progress": ProjectStatus.IN_PROGRESS,
            "Under Review": ProjectStatus.UNDER_REVIEW,
            "Completed": ProjectStatus.COMPLETED,
            "Archived": ProjectStatus.ARCHIVED
        }
        
        p_id = self.project.id if self.project else f"proj_{uuid.uuid4().hex[:8]}"
        p_units = self.project.units if self.project else []
        p_deviations = self.project.deviations if self.project else []
        p_mitigations = self.project.mitigations if self.project else []
        p_diag = self.project.diagnostic_measures if self.project else []
        
        self.project = Project(
            id=p_id,
            name=self.name_input.text().strip(),
            project_number=self.number_input.text().strip(),
            description=self.description_input.toPlainText().strip(),
            version=self.version_input.text().strip() or "1.0.0",
            created_by=self.created_by_input.text().strip() or None,
            organization=self.organization_input.text().strip() or None,
            safety_standard=SafetyStandard(self.standard_combo.currentText()) if self.standard_combo.currentText() else None,
            target_sil=self.target_sil_combo.currentText() or None,
            product_name=self.product_name_input.text().strip() or None,
            product_group=self.product_group_input.text().strip() or None,
            product_version=self.product_version_input.text().strip() or None,
            mission_time=self.mission_time_input.value(),
            test_interval=self.test_interval_input.value(),
            diagnostic_test_interval=self.diagnostic_interval_input.value(),
            status=status_map.get(self.status_combo.currentText(), ProjectStatus.DRAFT),
            reviewer=self.reviewer_input.text().strip() or None,
            custom_fields=custom_fields,
            safety_context=sc,
            source_documents_list=self.source_docs.copy(),
            reliability_database_source=self.rel_db_source.text().strip() or None,
            selected_profile=self.profile_combo.currentText(),
            environmental_profile=self.env_profile.text().strip() or None,
            units=p_units,
            deviations=p_deviations,
            mitigations=p_mitigations,
            diagnostic_measures=p_diag
        )
        
        self.project_saved.emit(self.project)
        
    def _on_cancel(self):
        self.cancel_requested.emit()
        
    def reset_form(self):
        self.project = None
        self.edit_mode = False
        self.name_input.clear()
        self.number_input.clear()
        self.description_input.clear()
        self.version_input.setText("1.0.0")
        self.created_by_input.clear()
        self.organization_input.clear()
        self.standard_combo.setCurrentIndex(0)
        self.target_sil_combo.setCurrentIndex(1)
        self.product_name_input.clear()
        self.product_group_input.clear()
        self.product_version_input.clear()
        self.mission_time_input.setValue(87600)
        self.test_interval_input.setValue(8760)
        self.diagnostic_interval_input.setValue(1.0)
        self.status_combo.setCurrentIndex(0)
        self.reviewer_input.clear()
        self.custom_fields_table.setRowCount(0)
        
        # Optional
        self.safety_fn_name.clear()
        self.safety_fn_desc.clear()
        self.safe_state.clear()
        self.dangerous_state.clear()
        self.no_part_failure_def.clear()
        self.no_effect_failure_def.clear()
        self.architecture_combo.setCurrentIndex(0)
        self.operating_mode_combo.setCurrentIndex(0)
        self.boundary_input.clear()
        self.sensor_included.setCurrentIndex(0)
        self.profile_combo.setCurrentText("Profile 1")
        self.rel_db_source.clear()
        self.env_profile.clear()
        self.source_docs = []
        self.sources_table.setRowCount(0)
        self.safety_notes.clear()
        
        self.project_name_label.setText("Untitled Project")
        
    def load_project(self, project_data: dict):
        self.reset_form()
        self.edit_mode = True
        self.project = Project(**project_data)
        self.project_name_label.setText(self.project.name)
        
        self.name_input.setText(self.project.name)
        self.number_input.setText(self.project.project_number or "")
        self.description_input.setPlainText(self.project.description)
        self.version_input.setText(self.project.version)
        self.created_by_input.setText(self.project.created_by or "")
        self.organization_input.setText(self.project.organization or "")
        
        std_idx = self.standard_combo.findText(self.project.safety_standard.value if self.project.safety_standard else "")
        if std_idx >= 0:
            self.standard_combo.setCurrentIndex(std_idx)
            
        sil_idx = self.target_sil_combo.findText(self.project.target_sil or "")
        if sil_idx >= 0:
            self.target_sil_combo.setCurrentIndex(sil_idx)
            
        self.product_name_input.setText(self.project.product_name or "")
        self.product_group_input.setText(self.project.product_group or "")
        self.product_version_input.setText(self.project.product_version or "")
        self.mission_time_input.setValue(self.project.mission_time or 87600)
        self.test_interval_input.setValue(self.project.test_interval or 8760)
        self.diagnostic_interval_input.setValue(self.project.diagnostic_test_interval or 1.0)
        
        status_text = self.project.status.value.replace("_", " ").title()
        status_idx = self.status_combo.findText(status_text)
        if status_idx >= 0:
            self.status_combo.setCurrentIndex(status_idx)
            
        self.reviewer_input.setText(self.project.reviewer or "")
        
        # Custom fields
        for k, v in self.project.custom_fields.items():
            if k == "diagnostic_measures":
                continue
            row = self.custom_fields_table.rowCount()
            self.custom_fields_table.insertRow(row)
            self.custom_fields_table.setItem(row, 0, QTableWidgetItem(k))
            self.custom_fields_table.setItem(row, 1, QTableWidgetItem(str(v)))
            
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda: self.custom_fields_table.removeRow(self.custom_fields_table.currentRow()))
            self.custom_fields_table.setCellWidget(row, 2, del_btn)
            
        # Load Page 2 Safety
        sc = self.project.safety_context
        if sc:
            self.safety_fn_name.setText(sc.safety_function_name or "")
            self.safety_fn_desc.setPlainText(sc.safety_function_description or "")
            self.safe_state.setText(sc.safe_state or "")
            self.dangerous_state.setText(sc.dangerous_state or "")
            self.no_part_failure_def.setPlainText(getattr(sc, "no_part_failure_definition", None) or "")
            self.no_effect_failure_def.setPlainText(getattr(sc, "no_effect_failure_definition", None) or "")
            
            arch_idx = self.architecture_combo.findText(sc.safety_architecture or "1oo1")
            if arch_idx >= 0:
                self.architecture_combo.setCurrentIndex(arch_idx)
                
            mode_idx = self.operating_mode_combo.findText(sc.operating_mode or "Low demand mode")
            if mode_idx >= 0:
                self.operating_mode_combo.setCurrentIndex(mode_idx)
                
            self.boundary_input.setPlainText(sc.safety_boundary or "")
            self.sensor_included.setCurrentText("Yes" if getattr(sc, "external_sensor_included", False) else "No")
            self.safety_notes.setPlainText(sc.notes or "")
            
        # Load Page 3 sources
        self.source_docs = self.project.source_documents_list.copy()
        self._refresh_sources_table()
        self.profile_combo.setCurrentText(getattr(self.project, "selected_profile", "Profile 1") or "Profile 1")
        self.rel_db_source.setText(self.project.reliability_database_source or "")
        self.env_profile.setText(self.project.environmental_profile or "")
