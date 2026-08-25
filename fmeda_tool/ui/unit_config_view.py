

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, List, Dict
import uuid

from fmeda_tool.models import Unit, Deviation, Mitigation, Project
from fmeda_tool.ui.dialogs.deviation_dialog import DeviationDialog


class UnitConfigView(QWidget):
    """View for creating/editing a unit with deviations"""
    
    unit_saved = pyqtSignal(Unit, list, list)  # Unit, list of Deviations, list of Mitigations
    cancel_requested = pyqtSignal()
    
    def __init__(self, project: Project, unit: Optional[Unit] = None):
        super().__init__()
        self.project = project
        self.unit = unit
        self.is_editing = unit is not None
        
        # Store deviations and mitigations being configured
        self.deviations: List[Deviation] = []
        self.mitigations: List[Mitigation] = []
        self.deviation_mitigations: Dict[str, List[str]] = {}  # deviation_id -> list of mitigation_ids
        
        # Load existing deviations if editing
        if self.is_editing:
            self._load_existing_data()
        
        self._setup_ui()
        if self.unit:
            self._load_unit_data()
        self._refresh_deviations_table()
    
    def _load_existing_data(self):
        """Load existing deviations and mitigations from project"""
        # Find deviations in project that belong to this unit
        # For now, we'll load all project deviations - could filter by component relationships
        self.deviations = [dev for dev in self.project.deviations]
        self.mitigations = [mit for mit in self.project.mitigations]
        
        # Build deviation-mitigation relationships
        for deviation in self.deviations:
            self.deviation_mitigations[deviation.id] = deviation.mitigation_ids.copy()
    
    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with title and save button
        self._create_header(layout)
        
        # Main content area
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #f8f9fa;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(40, 30, 40, 30)
        content_layout.setSpacing(20)
        
        # Form fields
        self._create_form(content_layout)
        
        # Deviations table
        self._create_deviations_section(content_layout)
        
        layout.addWidget(content_widget)
    
    def _create_header(self, parent_layout):
        """Create header with title and save button"""
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-bottom: 2px solid #dee2e6;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(40, 20, 40, 20)
        
        # Title
        title_text = self.unit.name if self.unit else "New Unit"
        self.title_label = QLabel(title_text)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #212529;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 10px 24px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        cancel_btn.clicked.connect(self.cancel_requested.emit)
        header_layout.addWidget(cancel_btn)
        
        # Save button
        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #198754;
                color: white;
                border: none;
                padding: 10px 24px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #157347;
            }
        """)
        save_btn.clicked.connect(self._on_save)
        header_layout.addWidget(save_btn)
        
        parent_layout.addWidget(header_frame)
    
    def _create_form(self, parent_layout):
        """Create form fields"""
        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                padding: 20px;
            }
        """)
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(15)
        
        # Unit Name field
        name_label = QLabel("Unit Name:")
        name_label.setStyleSheet("font-weight: bold; color: #495057;")
        form_layout.addWidget(name_label)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter unit name...")
        self.name_input.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #0d6efd;
            }
        """)
        self.name_input.textChanged.connect(self._on_name_changed)
        form_layout.addWidget(self.name_input)
        
        # Description field
        desc_label = QLabel("Description:")
        desc_label.setStyleSheet("font-weight: bold; color: #495057;")
        form_layout.addWidget(desc_label)
        
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Enter detailed description of the unit...")
        self.description_input.setMinimumHeight(120)
        self.description_input.setStyleSheet("""
            QTextEdit {
                padding: 10px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 14px;
            }
            QTextEdit:focus {
                border-color: #0d6efd;
            }
        """)
        form_layout.addWidget(self.description_input)
        
        parent_layout.addWidget(form_frame)
    
    def _create_deviations_section(self, parent_layout):
        """Create deviations table section"""
        # Section header with label and add button
        section_header = QHBoxLayout()
        
        deviations_label = QLabel("Deviations")
        deviations_font = QFont()
        deviations_font.setPointSize(13)
        deviations_font.setBold(True)
        deviations_label.setFont(deviations_font)
        deviations_label.setStyleSheet("color: #212529;")
        section_header.addWidget(deviations_label)
        
        section_header.addStretch()
        
        add_deviation_btn = QPushButton("➕ Add Deviation")
        add_deviation_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
        """)
        add_deviation_btn.clicked.connect(self._on_add_deviation)
        section_header.addWidget(add_deviation_btn)
        
        parent_layout.addLayout(section_header)
        
        # Deviations table
        self.deviations_table = QTableWidget()
        self.deviations_table.setColumnCount(4)
        self.deviations_table.setHorizontalHeaderLabels(["Name", "Impact", "Mitigations", "Actions"])
        
        # Style the table
        self.deviations_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 12px 8px;
                border: none;
                border-bottom: 2px solid #dee2e6;
                font-weight: bold;
                color: #495057;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        
        # Enable independent column resizing
        self.deviations_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.deviations_table.setColumnWidth(0, 200)  # Name
        self.deviations_table.setColumnWidth(1, 200)  # Impact
        self.deviations_table.setColumnWidth(2, 120)  # Mitigations
        self.deviations_table.setColumnWidth(3, 180)  # Actions
        
        # Enable horizontal scrollbar if columns exceed table width
        self.deviations_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        parent_layout.addWidget(self.deviations_table)
    
    def _refresh_deviations_table(self):
        """Refresh the deviations table"""
        self.deviations_table.setRowCount(0)
        
        for deviation in self.deviations:
            row = self.deviations_table.rowCount()
            self.deviations_table.insertRow(row)
            
            # Name
            self.deviations_table.setItem(row, 0, QTableWidgetItem(deviation.name))
            
            # Impact
            impact = deviation.effect or "N/A"
            self.deviations_table.setItem(row, 1, QTableWidgetItem(impact))
            
            # Mitigations count
            mitigation_ids = self.deviation_mitigations.get(deviation.id, [])
            mitigation_count = len(mitigation_ids)
            self.deviations_table.setItem(row, 2, QTableWidgetItem(f"{mitigation_count} mitigation(s)"))
            
            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            
            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0d6efd;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #0b5ed7;
                }
            """)
            edit_btn.clicked.connect(lambda checked, d=deviation: self._on_edit_deviation(d))
            actions_layout.addWidget(edit_btn)
            
            delete_btn = QPushButton("Delete")
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #bb2d3b;
                }
            """)
            delete_btn.clicked.connect(lambda checked, d=deviation: self._on_delete_deviation(d))
            actions_layout.addWidget(delete_btn)
            
            self.deviations_table.setCellWidget(row, 3, actions_widget)
    
    def _load_unit_data(self):
        """Load unit data into form"""
        if not self.unit:
            return
        
        self.name_input.setText(self.unit.name)
        self.description_input.setPlainText(self.unit.description)
    
    def _on_name_changed(self):
        """Update header title when name changes"""
        name = self.name_input.text().strip() or "New Unit"
        self.title_label.setText(name)
    
    def _on_add_deviation(self):
        """Handle add deviation button click"""
        unit_name = self.name_input.text().strip() or "New Unit"
        dialog = DeviationDialog(unit_name, parent=self)
        dialog.deviation_saved.connect(self._on_deviation_saved)
        dialog.exec()
    
    def _on_edit_deviation(self, deviation: Deviation):
        """Handle edit deviation button click"""
        unit_name = self.name_input.text().strip() or "New Unit"
        
        # Get mitigations for this deviation
        mitigation_ids = self.deviation_mitigations.get(deviation.id, [])
        deviation_mitigations = [m for m in self.mitigations if m.id in mitigation_ids]
        
        dialog = DeviationDialog(unit_name, deviation, deviation_mitigations, parent=self)
        dialog.deviation_saved.connect(lambda dev, mits: self._on_deviation_updated(dev, mits))
        dialog.exec()
    
    def _on_deviation_saved(self, deviation: Deviation, mitigations: List[Mitigation]):
        """Handle new deviation created"""
        self.deviations.append(deviation)
        
        # Add mitigations
        mitigation_ids = []
        for mitigation in mitigations:
            if mitigation.id not in [m.id for m in self.mitigations]:
                self.mitigations.append(mitigation)
            mitigation_ids.append(mitigation.id)
        
        self.deviation_mitigations[deviation.id] = mitigation_ids
        self._refresh_deviations_table()
    
    def _on_deviation_updated(self, deviation: Deviation, mitigations: List[Mitigation]):
        """Handle deviation updated"""
        # Update mitigations for this deviation
        mitigation_ids = []
        for mitigation in mitigations:
            if mitigation.id not in [m.id for m in self.mitigations]:
                self.mitigations.append(mitigation)
            else:
                # Update existing mitigation
                existing_idx = next(i for i, m in enumerate(self.mitigations) if m.id == mitigation.id)
                self.mitigations[existing_idx] = mitigation
            mitigation_ids.append(mitigation.id)
        
        self.deviation_mitigations[deviation.id] = mitigation_ids
        self._refresh_deviations_table()
    
    def _on_delete_deviation(self, deviation: Deviation):
        """Handle delete deviation button click"""
        reply = QMessageBox.question(
            self,
            "Delete Deviation",
            f"Are you sure you want to delete deviation '{deviation.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.deviations.remove(deviation)
            if deviation.id in self.deviation_mitigations:
                del self.deviation_mitigations[deviation.id]
            self._refresh_deviations_table()
    
    def _on_save(self):
        """Handle save button click"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please enter a unit name.")
            return
        
        description = self.description_input.toPlainText().strip()
        if not description:
            QMessageBox.warning(self, "Validation Error", "Please enter a description.")
            return
        
        if self.is_editing:
            # Update existing unit
            self.unit.name = name
            self.unit.description = description
            unit_to_save = self.unit
        else:
            # Create new unit
            unit_id = f"unit_{uuid.uuid4().hex[:8]}"
            unit_to_save = Unit(
                id=unit_id,
                name=name,
                description=description
            )
        
        # Update deviation relationships
        for deviation in self.deviations:
            mitigation_ids = self.deviation_mitigations.get(deviation.id, [])
            deviation.mitigation_ids = mitigation_ids
        
        # Update mitigation relationships
        for mitigation in self.mitigations:
            mitigation.deviation_ids = [
                dev_id for dev_id, mit_ids in self.deviation_mitigations.items()
                if mitigation.id in mit_ids
            ]
        
        self.unit_saved.emit(unit_to_save, self.deviations, self.mitigations)
