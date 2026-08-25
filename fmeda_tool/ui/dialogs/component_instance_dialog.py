

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QHeaderView, QWidget, QSpinBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, List

from fmeda_tool.models import (
    Component, FailureModeAssignment, Deviation, DiagnosticMeasure, Project
)


class ComponentInstanceDialog(QDialog):
    """Dialog for editing a component instance with failure mode assignments"""
    
    component_updated = pyqtSignal(Component)
    secondary_failure_requested = pyqtSignal(str)  # Failure mode name for secondary failure selection
    
    def __init__(self, component: Component, project: Project, parent=None):
        super().__init__(parent)
        self.component = component
        self.project = project
        self.failure_mode_rows = {}  # Map failure mode name to row index
        
        self.setWindowTitle(f"Edit Component: {component.name}")
        self.setMinimumWidth(625)
        self.setMinimumHeight(320)
        self.resize(625, 320)
        
        # Set window flags for floating dialog
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Component info section
        self._create_component_info(layout)
        
        # Failure modes table
        self._create_failure_modes_table(layout)
        
        # Buttons
        self._create_buttons(layout)
    
    def _create_component_info(self, parent_layout):
        """Create component information section"""
        info_widget = QWidget()
        info_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        info_layout = QVBoxLayout(info_widget)
        
        # Title
        title_label = QLabel("Component Information")
        title_font = QFont()
        title_font.setPointSize(9)
        title_font.setBold(True)
        title_label.setFont(title_font)
        info_layout.addWidget(title_label)
        
        # Name and shortcut
        name_layout = QHBoxLayout()
        
        name_lbl = QLabel("Name:")
        name_lbl.setStyleSheet("font-size: 8pt;")
        name_layout.addWidget(name_lbl)
        self.name_label = QLabel(self.component.name)
        self.name_label.setStyleSheet("font-weight: bold; color: #212529; font-size: 8pt;")
        name_layout.addWidget(self.name_label)
        name_layout.addStretch()
        
        shortcut_lbl = QLabel("Shortcut:")
        shortcut_lbl.setStyleSheet("font-size: 8pt;")
        name_layout.addWidget(shortcut_lbl)
        self.shortcut_label = QLabel(self.component.position)
        self.shortcut_label.setStyleSheet("font-weight: bold; color: #495057; font-size: 8pt;")
        name_layout.addWidget(self.shortcut_label)
        name_layout.addStretch()
        
        info_layout.addLayout(name_layout)
        
        parent_layout.addWidget(info_widget)
    
    def _create_failure_modes_table(self, parent_layout):
        """Create failure modes configuration table"""
        # Section title
        title_label = QLabel("Failure Modes Configuration")
        title_font = QFont()
        title_font.setPointSize(9)
        title_font.setBold(True)
        title_label.setFont(title_font)
        parent_layout.addWidget(title_label)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Failure Mode",
            "Rate %",
            "Deviation",
            "Diagnostic Measure",
            "Detection %",
            "Dangerous %",
            "Secondary Failure"
        ])
        
        # Style the table
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                gridline-color: #dee2e6;
                font-size: 8pt;
            }
            QTableWidget::item {
                padding: 2px;
                border-bottom: 1px solid #f1f3f5;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 4px 4px;
                border: none;
                border-bottom: 2px solid #dee2e6;
                border-right: 1px solid #dee2e6;
                font-weight: bold;
                font-size: 8pt;
                color: #495057;
            }
        """)
        
        # Set vertical header (row numbers) width smaller
        self.table.verticalHeader().setDefaultSectionSize(20)
        
        # Set column widths - enable independent column resizing
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.table.setColumnWidth(0, 150)  # Failure Mode
        self.table.setColumnWidth(1, 50)   # Rate %
        self.table.setColumnWidth(2, 100)  # Deviation
        self.table.setColumnWidth(3, 100)  # Diagnostic
        self.table.setColumnWidth(4, 70)   # Detection %
        self.table.setColumnWidth(5, 75)   # Dangerous %
        self.table.setColumnWidth(6, 120)  # Secondary Failure
        
        # Enable horizontal scrollbar if columns exceed table width
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        parent_layout.addWidget(self.table)
    
    def _create_buttons(self, parent_layout):
        """Create dialog buttons"""
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(70)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setMinimumWidth(70)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
        """)
        save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(save_btn)
        
        parent_layout.addLayout(button_layout)
    
    def _load_data(self):
        """Load failure modes and existing assignments"""
        self.table.setRowCount(0)
        self.failure_mode_rows.clear()
        
        # Create a map of existing assignments
        assignments_map = {
            assignment.failure_mode_name: assignment
            for assignment in self.component.failure_mode_assignments
        }
        
        # Add row for each failure mode
        for failure_mode_name, percentage in self.component.failure_modes.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.failure_mode_rows[failure_mode_name] = row
            
            # Get existing assignment if any
            assignment = assignments_map.get(failure_mode_name)
            
            # Failure mode name
            name_item = QTableWidgetItem(failure_mode_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            
            # Rate percentage
            rate_item = QTableWidgetItem(f"{percentage:.1f}")
            rate_item.setFlags(rate_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            rate_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, rate_item)
            
            # Deviation dropdown
            deviation_combo = QComboBox()
            deviation_combo.setStyleSheet("font-size: 8pt;")
            deviation_combo.addItem("-- None --", None)
            for deviation in self.project.deviations:
                deviation_combo.addItem(deviation.name, deviation.id)
            
            # Set selected deviation if exists
            if assignment and assignment.deviation_id:
                index = deviation_combo.findData(assignment.deviation_id)
                if index >= 0:
                    deviation_combo.setCurrentIndex(index)
            
            self.table.setCellWidget(row, 2, deviation_combo)
            
            # Diagnostic measure dropdown
            dm_combo = QComboBox()
            dm_combo.setStyleSheet("font-size: 8pt;")
            dm_combo.addItem("-- None --", None)
            for dm in self.project.diagnostic_measures:
                dm_combo.addItem(f"{dm.description} ({dm.dc}%)", dm.id)
            
            # Set selected diagnostic measure if exists
            if assignment and assignment.diagnostic_measure_id:
                index = dm_combo.findData(assignment.diagnostic_measure_id)
                if index >= 0:
                    dm_combo.setCurrentIndex(index)
            
            self.table.setCellWidget(row, 3, dm_combo)
            
            # Detection percentage spinbox
            detection_spin = QSpinBox()
            detection_spin.setStyleSheet("font-size: 8pt;")
            detection_spin.setRange(0, 100)
            detection_spin.setSuffix("%")
            detection_spin.setValue(
                int(assignment.detection_percentage) if assignment and assignment.detection_percentage else 0
            )
            self.table.setCellWidget(row, 4, detection_spin)
            
            # Dangerous failure percentage spinbox
            dangerous_spin = QSpinBox()
            dangerous_spin.setStyleSheet("font-size: 8pt;")
            dangerous_spin.setRange(0, 100)
            dangerous_spin.setSuffix("%")
            dangerous_spin.setValue(
                int(assignment.dangerous_failure_percentage) if assignment and assignment.dangerous_failure_percentage else 0
            )
            self.table.setCellWidget(row, 5, dangerous_spin)
            
            # Secondary failure button
            sf_btn = QPushButton("Select")
            sf_btn.setStyleSheet("""
                QPushButton {
                    background-color: #6c757d;
                    color: white;
                    border: none;
                    padding: 3px 6px;
                    border-radius: 2px;
                    font-size: 7pt;
                }
                QPushButton:hover {
                    background-color: #5a6268;
                }
            """)
            sf_btn.clicked.connect(
                lambda checked, fm=failure_mode_name: self._on_select_secondary_failure(fm)
            )
            
            # If there's an existing secondary failure, show component name
            if assignment and assignment.secondary_failure_component_id:
                # Find the component name
                comp_name = self._get_component_name(assignment.secondary_failure_component_id)
                if comp_name:
                    sf_btn.setText(f"✓ {comp_name[:10]}")
                    sf_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #198754;
                            color: white;
                            border: none;
                            padding: 3px 6px;
                            border-radius: 2px;
                            font-size: 7pt;
                        }
                        QPushButton:hover {
                            background-color: #157347;
                        }
                    """)
            
            self.table.setCellWidget(row, 6, sf_btn)
    
    def _get_component_name(self, component_id: str) -> Optional[str]:
        """Get component name by ID from current unit"""
        for unit in self.project.units:
            for comp in unit.components:
                if comp.id == component_id:
                    return comp.name
        return None
    
    def _on_select_secondary_failure(self, failure_mode_name: str):
        """Handle secondary failure selection"""
        # Emit signal and let the parent handle component selection from canvas
        self.secondary_failure_requested.emit(failure_mode_name)
        QMessageBox.information(
            self,
            "Select Component",
            f"Click on another component in the canvas to assign it as the secondary failure location for '{failure_mode_name}'.\n\nNote: This functionality will be fully implemented in the next update."
        )
    
    def _on_save(self):
        """Save failure mode assignments"""
        try:
            # Clear existing assignments
            self.component.failure_mode_assignments.clear()
            
            # Create new assignments from table
            for failure_mode_name, row in self.failure_mode_rows.items():
                percentage = self.component.failure_modes[failure_mode_name]
                
                # Get values from widgets
                deviation_combo = self.table.cellWidget(row, 2)
                dm_combo = self.table.cellWidget(row, 3)
                detection_spin = self.table.cellWidget(row, 4)
                dangerous_spin = self.table.cellWidget(row, 5)
                
                deviation_id = deviation_combo.currentData()
                dm_id = dm_combo.currentData()
                detection_pct = float(detection_spin.value())
                dangerous_pct = float(dangerous_spin.value())
                
                # Create assignment
                assignment = FailureModeAssignment(
                    failure_mode_name=failure_mode_name,
                    failure_rate_percentage=percentage,
                    deviation_id=deviation_id,
                    diagnostic_measure_id=dm_id,
                    detection_percentage=detection_pct if detection_pct > 0 else None,
                    dangerous_failure_percentage=dangerous_pct if dangerous_pct > 0 else None,
                    secondary_failure_component_id=None  # TODO: Implement secondary failure selection
                )
                
                self.component.failure_mode_assignments.append(assignment)
            
            # Emit signal
            self.component_updated.emit(self.component)
            
            # Close dialog
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save component configuration:\n{str(e)}"
            )
