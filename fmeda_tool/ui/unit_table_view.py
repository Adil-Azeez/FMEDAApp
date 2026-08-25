

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from typing import List

from fmeda_tool.models import Unit, Component


class UnitTableView(QDialog):
    """Table view showing detailed component and failure mode information"""
    
    def __init__(self, unit: Unit, project=None, parent=None):
        super().__init__(parent)
        self.unit = unit
        self.project = project
        
        self.setWindowTitle(f"Unit Table View: {unit.name}")
        self.setMinimumSize(1400, 600)
        self.resize(1400, 700)
        
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header_layout = QHBoxLayout()
        
        title_label = QLabel(f"Unit: {self.unit.name}")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        header_layout.addWidget(close_btn)
        
        layout.addLayout(header_layout)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(22)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Function",
            "Value",
            "Component",
            "Failure Mode",
            "FM %",
            "Basic Failure Rate",
            "Deviation",
            "Dangerous %",
            "Secondary Failure",
            "Discovery",
            "DC",
            "λ",
            "λ % Safe",
            "λ % Dangerous",
            "λ Safe",
            "λ Danger",
            "λ SD",
            "λ SU",
            "λ DD",
            "λ DU",
            "SFF"
        ])
        
        # Style
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                background-color: white;
                gridline-color: #dee2e6;
            }
            QTableWidget::item {
                padding: 5px;
                border: 1px solid #e0e0e0;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 8px;
                border: 1px solid #dee2e6;
                font-weight: bold;
            }
        """)
        
        # Enable sorting
        self.table.setSortingEnabled(False)
        
        # Set default row height
        self.table.verticalHeader().setDefaultSectionSize(35)
        
        # Set column widths - enable independent column resizing
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # Enable horizontal scrollbar if columns exceed table width
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        layout.addWidget(self.table)
    
    def _load_data(self):
        """Load component data into the table with merged rows for components"""
        self.table.setRowCount(0)
        
        # Iterate through all components in the unit
        for comp_idx, component in enumerate(self.unit.components):
            # Get basic component info
            comp_id = comp_idx + 1  # ID in editor (1-based)
            function = ""  # To be assigned later
            value = ""  # To be assigned later
            component_shortcut = component.position if component.position else component.name
            basic_failure_rate = component.failure_rate if component.failure_rate else 0.0
            
            # Determine number of failure modes (rows needed for this component)
            num_failure_modes = len(component.failure_modes) if component.failure_modes else 1
            
            # Get the starting row for this component
            start_row = self.table.rowCount()
            
            # Insert rows for all failure modes
            for _ in range(num_failure_modes):
                self.table.insertRow(self.table.rowCount())
            
            # Set component-level info with row spanning
            # These columns span all failure mode rows
            self._set_spanned_item(start_row, 0, num_failure_modes, str(comp_id))
            self._set_spanned_item(start_row, 1, num_failure_modes, function)
            self._set_spanned_item(start_row, 2, num_failure_modes, value)
            self._set_spanned_item(start_row, 3, num_failure_modes, component_shortcut)
            self._set_spanned_item(start_row, 6, num_failure_modes, f"{basic_failure_rate:.6f}")
            
            # Now fill in failure mode specific data for each row
            if component.failure_modes:
                for fm_idx, (fm_name, fm_percentage) in enumerate(component.failure_modes.items()):
                    row = start_row + fm_idx
                    
                    # Get assignment for this failure mode
                    assignment = None
                    for a in component.failure_mode_assignments:
                        if a.failure_mode_name == fm_name:
                            assignment = a
                            break
                    
                    # Failure mode name
                    self._set_item(row, 4, fm_name)
                    
                    # Failure mode percentage
                    self._set_item(row, 5, f"{fm_percentage:.2f}%")
                    
                    # Assignment info
                    if assignment:
                        # Deviation
                        deviation_name = ""
                        if assignment.deviation_id:
                            deviation_name = assignment.deviation_id
                            if hasattr(self, 'project') and self.project:
                                for dev in self.project.deviations:
                                    if dev.id == assignment.deviation_id:
                                        deviation_name = dev.name
                                        break
                        self._set_item(row, 7, deviation_name)
                        
                        # Dangerous failure percentage
                        dangerous_pct = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage else 0.0
                        self._set_item(row, 8, f"{dangerous_pct:.1f}%")
                        
                        # Secondary failure
                        secondary = assignment.secondary_failure_component_id if assignment.secondary_failure_component_id else "0"
                        self._set_item(row, 9, secondary)
                        
                        # Discovery (based on detection percentage)
                        detection = assignment.detection_percentage if assignment.detection_percentage else 0.0
                        discovery = "1" if detection > 0 else "0"
                        self._set_item(row, 10, discovery)
                        
                        # Calculate results
                        dc = detection / 100.0 if detection > 0 else 0.0
                        self._set_item(row, 11, f"{dc:.4f}")
                        
                        # λ = basic_failure_rate * (fm_percentage / 100)
                        lambda_val = basic_failure_rate * (fm_percentage / 100.0)
                        self._set_item(row, 12, f"{lambda_val:.6f}")
                        
                        # λ % Safe = 1 - (dangerous_pct / 100)
                        lambda_pct_safe = 1.0 - (dangerous_pct / 100.0)
                        self._set_item(row, 13, f"{lambda_pct_safe:.4f}")
                        
                        # λ % Dangerous = dangerous_pct / 100
                        lambda_pct_dangerous = dangerous_pct / 100.0
                        self._set_item(row, 14, f"{lambda_pct_dangerous:.4f}")
                        
                        # λ Safe = λ * λ % Safe
                        lambda_safe = lambda_val * lambda_pct_safe
                        self._set_item(row, 15, f"{lambda_safe:.6f}")
                        
                        # λ Danger = λ * λ % Dangerous
                        lambda_danger = lambda_val * lambda_pct_dangerous
                        self._set_item(row, 16, f"{lambda_danger:.6f}")
                        
                        # λ SD = DC * λ Safe
                        lambda_sd = dc * lambda_safe
                        self._set_item(row, 17, f"{lambda_sd:.6f}")
                        
                        # λ SU = (1 - DC) * λ Safe
                        lambda_su = (1.0 - dc) * lambda_safe
                        self._set_item(row, 18, f"{lambda_su:.6f}")
                        
                        # λ DD = DC * λ Danger
                        lambda_dd = dc * lambda_danger
                        self._set_item(row, 19, f"{lambda_dd:.6f}")
                        
                        # λ DU = (1 - DC) * λ Danger
                        lambda_du = (1.0 - dc) * lambda_danger
                        self._set_item(row, 20, f"{lambda_du:.6f}")
                        
                        # SFF = (λ SD + λ SU + λ DD) / (λ SD + λ SU + λ DD + λ DU)
                        total_lambda = lambda_sd + lambda_su + lambda_dd + lambda_du
                        sff = ((lambda_sd + lambda_su + lambda_dd) / total_lambda * 100.0) if total_lambda > 0 else 0.0
                        self._set_item(row, 21, f"{sff:.2f}%")
                    else:
                        # No assignment - fill with defaults
                        for col in range(7, 22):
                            self._set_item(row, col, "0" if col in [9, 10] else "-")
            else:
                # No failure modes - fill with empty values
                row = start_row
                for col in range(4, 22):
                    self._set_item(row, col, "-")
    
    def _set_spanned_item(self, row: int, col: int, row_span: int, text: str):
        """Helper to set a table item with row spanning"""
        # Set the span
        self.table.setSpan(row, col, row_span, 1)
        
        # Create and set the item
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        
        # Add background color to distinguish component-level cells
        item.setBackground(QColor("#f8f9fa"))
        
        self.table.setItem(row, col, item)
    
    def _set_item(self, row: int, col: int, text: str):
        """Helper to set a table item"""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        
        # Center align numeric columns
        if col >= 5:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.table.setItem(row, col, item)
