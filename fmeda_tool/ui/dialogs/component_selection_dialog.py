from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QHeaderView, QMessageBox, QGroupBox, QFormLayout, QDoubleSpinBox,
    QComboBox, QScrollArea, QFrame, QTextEdit, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import List, Optional, Dict
import json
import uuid
from pathlib import Path

from fmeda_tool.models import ComponentDB, Component, FailureModeAssignment


class ComponentSelectionDialog(QDialog):
    """Dialog for selecting a component from the database and configuring it"""
    
    component_selected = pyqtSignal(object)  # Emits the constructed Component model
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.components: List[ComponentDB] = []
        self.filtered_components: List[ComponentDB] = []
        self.selected_template: Optional[ComponentDB] = None
        self.created_component: Optional[Component] = None
        self.spinboxes = {}
        self.comboboxes = {}
        
        self.setWindowTitle("Select & Configure Component")
        self.setMinimumWidth(950)
        self.setMinimumHeight(650)
        
        self._setup_ui()
        self._load_components()
        
    def _setup_ui(self):
        """Setup the split selection and configuration user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        # Title
        title_label = QLabel("Add Component from Database")
        title_font = QFont("Arial", 14, QFont.Weight.Bold)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)
        
        # Horizontal Split Layout
        split_layout = QHBoxLayout()
        main_layout.addLayout(split_layout)
        
        # --- LEFT SIDE: Search and Template Selection ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search Template:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name, shortcut, technology...")
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)
        
        # Templates table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Code", "Technology", "FITs"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_template_selection_changed)
        left_layout.addWidget(self.table)
        
        split_layout.addWidget(left_widget, stretch=1)
        
        # --- RIGHT SIDE: Configuration Panel ---
        right_widget = QGroupBox("Configure Component Details")
        right_layout = QVBoxLayout(right_widget)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_layout.addWidget(scroll)
        
        scroll_widget = QWidget()
        form_layout = QFormLayout(scroll_widget)
        form_layout.setSpacing(10)
        scroll.setWidget(scroll_widget)
        
        # Metadata configuration
        self.designator_input = QLineEdit()
        self.designator_input.setPlaceholderText("e.g. R101, C204, U301...")
        form_layout.addRow("Component Label / Designator*:", self.designator_input)
        
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("e.g. 10k, 100nF, TPS5430...")
        form_layout.addRow("Value / Description:", self.value_input)
        
        self.fits_input = QDoubleSpinBox()
        self.fits_input.setRange(0.0, 100000.0)
        self.fits_input.setDecimals(4)
        self.fits_input.setValue(1.0)
        form_layout.addRow("Base Failure Rate (FIT)*:", self.fits_input)
        
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(60)
        form_layout.addRow("Notes:", self.notes_input)
        
        # Failure modes configuration table
        form_layout.addRow(QLabel("<b>Configure Failure Mode Distribution:</b>"))
        
        self.fm_table = QTableWidget()
        self.fm_table.setColumnCount(3)
        self.fm_table.setHorizontalHeaderLabels(["Failure Mode", "Distribution %", "Classification"])
        self.fm_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.fm_table.verticalHeader().setVisible(False)
        self.fm_table.setMaximumHeight(200)
        form_layout.addRow(self.fm_table)
        
        # Total distribution display
        self.total_dist_label = QLabel("Total: 0.0% (Must be 100%)")
        self.total_dist_label.setStyleSheet("color: #dc3545; font-weight: bold;")
        form_layout.addRow(self.total_dist_label)
        
        split_layout.addWidget(right_widget, stretch=1)
        
        # Bottom Actions Bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        self.add_btn = QPushButton("Add Component")
        self.add_btn.setMinimumWidth(120)
        self.add_btn.setStyleSheet("""
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
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.add_btn.setEnabled(False)
        button_layout.addWidget(self.add_btn)
        
        main_layout.addLayout(button_layout)
        
    def _load_components(self):
        """Load component templates from local JSON database"""
        try:
            db_path = Path("data/components_db.json")
            if db_path.exists():
                with open(db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.components = [ComponentDB(**comp) for comp in data]
                self.filtered_components = self.components.copy()
                self._refresh_templates_table()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load components database:\n{str(e)}")
            
    def _refresh_templates_table(self):
        self.table.setRowCount(0)
        for component in self.filtered_components:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(component.display_name))
            self.table.setItem(row, 1, QTableWidgetItem(component.shortcut or ""))
            self.table.setItem(row, 2, QTableWidgetItem(component.material or ""))
            self.table.setItem(row, 3, QTableWidgetItem(f"{component.fits:.4f}" if component.fits else ""))
            
    def _on_search(self):
        search_term = self.search_input.text().strip().lower()
        if not search_term:
            self.filtered_components = self.components.copy()
        else:
            self.filtered_components = [
                c for c in self.components
                if search_term in c.display_name.lower() or
                (c.shortcut and search_term in c.shortcut.lower()) or
                (c.material and search_term in c.material.lower())
            ]
        self._refresh_templates_table()
        
    def _on_template_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_template = None
            self.add_btn.setEnabled(False)
            self.fm_table.setRowCount(0)
            return
            
        row = selected_rows[0].row()
        if 0 <= row < len(self.filtered_components):
            self.selected_template = self.filtered_components[row]
            self.add_btn.setEnabled(True)
            
            # Pre-populate details
            self.designator_input.setText(self.selected_template.shortcut or "")
            self.fits_input.setValue(self.selected_template.fits or 1.0)
            self.value_input.setText(self.selected_template.display_name)
            
            # Load failure modes configuration
            self._load_failure_modes(self.selected_template.failure_modes)
            
    def _load_failure_modes(self, failure_modes: Dict[str, float]):
        self.fm_table.setRowCount(0)
        self.spinboxes = {}
        self.comboboxes = {}
        
        for fm_name, fm_perc in failure_modes.items():
            row = self.fm_table.rowCount()
            self.fm_table.insertRow(row)
            
            # Failure Mode Name
            self.fm_table.setItem(row, 0, QTableWidgetItem(fm_name))
            
            # Spinbox for percentage
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setValue(fm_perc)
            spin.setDecimals(1)
            spin.setSuffix(" %")
            spin.valueChanged.connect(self._update_total_distribution)
            self.fm_table.setCellWidget(row, 1, spin)
            self.spinboxes[fm_name] = spin
            
            # Combo for classification
            combo = QComboBox()
            combo.addItems([
                "Not Evaluated",
                "Safe Failure",
                "Dangerous Failure",
                "No Effect Failure",
                "No Part Failure",
                "Diagnostic Function Failure"
            ])
            # Intelligent pre-classification based on keywords
            fm_lower = fm_name.lower()
            if "short" in fm_lower or "open" in fm_lower or "drift" in fm_lower:
                combo.setCurrentText("Dangerous Failure")
            else:
                combo.setCurrentText("Not Evaluated")
            self.fm_table.setCellWidget(row, 2, combo)
            self.comboboxes[fm_name] = combo
            
        self._update_total_distribution()
        
    def _update_total_distribution(self):
        total = sum(spin.value() for spin in self.spinboxes.values())
        self.total_dist_label.setText(f"Total: {total:.1f}% (Must be 100%)")
        if abs(total - 100.0) < 0.01:
            self.total_dist_label.setStyleSheet("color: #198754; font-weight: bold;")
        else:
            self.total_dist_label.setStyleSheet("color: #dc3545; font-weight: bold;")
            
    def _on_add_clicked(self):
        if not self.selected_template:
            return
            
        designator = self.designator_input.text().strip()
        if not designator:
            shortcut = self.selected_template.shortcut or "Component"
            parent_tab = self.parent()
            count = 1
            if parent_tab and hasattr(parent_tab, 'unit') and parent_tab.unit:
                for c in parent_tab.unit.components:
                    if c.position.startswith(f"{shortcut} Instance"):
                        count += 1
            designator = f"{shortcut} Instance {count}"
            
        # Verify total percentages
        total = sum(spin.value() for spin in self.spinboxes.values())
        if abs(total - 100.0) > 0.01:
            reply = QMessageBox.question(
                self,
                "Distribution Warning",
                f"The failure mode distribution sum is {total:.1f}% (not 100%). Do you still want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
                
        # Build Failure Mode Assignments
        assignments = []
        failure_modes = {}
        for fm_name, spin in self.spinboxes.items():
            perc = spin.value()
            failure_modes[fm_name] = perc
            
            combo = self.comboboxes[fm_name]
            classif = combo.currentText()
            
            # Map UI classification strings to model values
            classif_map = {
                "Not Evaluated": "not_evaluated",
                "Safe Failure": "safe_failure",
                "Dangerous Failure": "dangerous_failure",
                "No Effect Failure": "no_effect_failure",
                "No Part Failure": "no_part_failure",
                "Diagnostic Function Failure": "diagnostic_function_failure"
            }
            classification_val = classif_map.get(classif, "not_evaluated")
            
            # Safe/Dangerous defaults
            dangerous_percentage = 100.0 if classif == "Dangerous Failure" else 0.0
            
            assignments.append(FailureModeAssignment(
                failure_mode_name=fm_name,
                failure_rate_percentage=perc,
                classification=classification_val,
                dangerous_failure_percentage=dangerous_percentage,
                deviation_id=None,
                diagnostic_measure_id=None,
                detection_percentage=0.0
            ))
            
        component_id = f"comp_{uuid.uuid4().hex[:8]}"
        self.created_component = Component(
            id=component_id,
            position=designator,
            name=self.value_input.text().strip() or self.selected_template.display_name,
            type=self.selected_template.material or "Unknown",
            value=self.value_input.text().strip() or None,
            failure_rate=self.fits_input.value(),
            failure_modes=failure_modes,
            failure_mode_assignments=assignments,
            notes=self.notes_input.toPlainText().strip() or None
        )
        
        self.component_selected.emit(self.created_component)
        self.accept()
