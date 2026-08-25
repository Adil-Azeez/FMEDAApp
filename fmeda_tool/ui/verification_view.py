from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QFrame, QMessageBox, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from typing import Optional, List, Dict

from fmeda_tool.models import Project
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.services.calculation_service import CalculationService


class VerificationView(QWidget):
    """Page 3: Verification and validation checks view before export"""
    
    back_requested = pyqtSignal()
    next_requested = pyqtSignal()
    re_verify_requested = pyqtSignal()
    alert_clicked = pyqtSignal(str, int)  # Emits (unit_id, row_index)
    
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
        
        # Scroll Area for Verification Metrics
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(scroll)
        
        widget = QWidget()
        self.layout = QVBoxLayout(widget)
        self.layout.setContentsMargins(40, 20, 40, 20)
        self.layout.setSpacing(20)
        scroll.setWidget(widget)
        
        # Grid section for counts/summaries
        self.summary_grid = QGridLayout()
        self.summary_grid.setSpacing(15)
        self.layout.addLayout(self.summary_grid)
        
        # Grid section for target SIL vs achieved metrics
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(15)
        self.layout.addLayout(self.metrics_grid)
        
        # Validation table section
        table_lbl = QLabel("Validation Reports (Errors, Warnings & Info)")
        table_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.layout.addWidget(table_lbl)
        
        self.validation_table = QTableWidget()
        self.validation_table.setColumnCount(5)
        self.validation_table.setHorizontalHeaderLabels(["Severity", "Functional Group", "Item / Failure Mode", "Description", "Action"])
        self.validation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.validation_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.validation_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.layout.addWidget(self.validation_table)
        
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
        
        title_lbl = QLabel("Page 3: Verification & Validation")
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
        
        self.back_btn = QPushButton("Back to FMEDA Table")
        self.back_btn.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 6px 15px;")
        self.back_btn.clicked.connect(self._on_back)
        layout.addWidget(self.back_btn)
        
        layout.addStretch()
        
        self.reverify_btn = QPushButton("🔄 Re-Verify")
        self.reverify_btn.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 6px 20px;")
        self.reverify_btn.clicked.connect(self._on_reverify)
        layout.addWidget(self.reverify_btn)
        
        self.next_btn = QPushButton("Next to Export")
        self.next_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 25px;")
        self.next_btn.clicked.connect(self._on_next)
        layout.addWidget(self.next_btn)
        
        parent_layout.addWidget(nav_frame)
        
    def _on_back(self):
        self.back_requested.emit()
        
    def _on_reverify(self):
        self.re_verify_requested.emit()
        
    def _on_next(self):
        # Prevent export if errors exist
        errors_exist = False
        for r in range(self.validation_table.rowCount()):
            sev = self.validation_table.item(r, 0).text()
            if "Error" in sev:
                errors_exist = True
                break
        
        if errors_exist:
            QMessageBox.critical(
                self,
                "Export Blocked",
                "Validation errors were detected. You must resolve all validation errors before exporting."
            )
            return
            
        self.next_requested.emit()
        
    def _on_cell_double_clicked(self, row, column):
        unit_id_item = self.validation_table.item(row, 1)
        row_idx_item = self.validation_table.item(row, 4)
        if unit_id_item and row_idx_item:
            unit_id = unit_id_item.data(Qt.ItemDataRole.UserRole)
            row_idx = row_idx_item.data(Qt.ItemDataRole.UserRole)
            if unit_id and row_idx is not None:
                self.alert_clicked.emit(unit_id, row_idx)
                
    def load_project(self, project: Project):
        self.project = project
        self.project_name_label.setText(project.name)
        self.refresh_validation()
        
    def refresh_validation(self):
        if not self.project:
            return
            
        # Refresh calculations
        CalculationService.calculate_project(self.project)
        
        # Clear grids
        for i in reversed(range(self.summary_grid.count())):
            self.summary_grid.itemAt(i).widget().setParent(None)
        for i in reversed(range(self.metrics_grid.count())):
            self.metrics_grid.itemAt(i).widget().setParent(None)
            
        # 1. Populate summary counts
        def add_summary_box(label: str, value: str, r: int, c: int):
            f = QFrame()
            f.setStyleSheet("QFrame { background-color: #f8f9fa; border: 1px solid #ced4da; border-radius: 4px; padding: 10px; }")
            lay = QVBoxLayout(f)
            lay.setContentsMargins(5, 5, 5, 5)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
            val = QLabel(value)
            val.setStyleSheet("color: #212529; font-size: 16px; font-weight: bold;")
            lay.addWidget(lbl)
            lay.addWidget(val)
            self.summary_grid.addWidget(f, r, c)
            
        # Counts
        bom_components_count = 0
        mapped_count = 0
        unmapped_count = 0
        fmeda_rows_count = 0
        component_instances_count = 0
        
        for u in self.project.units:
            component_instances_count += len(u.components)
            if hasattr(u, 'bom_components') and u.bom_components:
                bom_components_count += len(u.bom_components)
                for comp in u.bom_components:
                    # check mapped
                    if getattr(comp, "part_number", None):
                        mapped_count += 1
                    else:
                        unmapped_count += 1
            # Row counts
            for comp in u.components:
                fmeda_rows_count += len(comp.failure_modes)
                
        add_summary_box("Functional Groups", str(len(self.project.units)), 0, 0)
        add_summary_box("Component Instances", str(component_instances_count), 0, 1)
        add_summary_box("BOM Components", str(bom_components_count), 0, 2)
        add_summary_box("Mapped Components", str(mapped_count), 0, 3)
        add_summary_box("Unmapped Components", str(unmapped_count), 0, 4)
        add_summary_box("Total FMEDA Rows", str(fmeda_rows_count), 0, 5)
        
        # 2. Populate safety metrics grid
        def add_metric_card(label: str, value: str, r: int, c: int, color_hex="#20c997"):
            f = QFrame()
            f.setStyleSheet(f"QFrame {{ background-color: #f8f9fa; border-left: 4px solid {color_hex}; border-radius: 4px; padding: 10px; }}")
            lay = QVBoxLayout(f)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
            val = QLabel(value)
            val.setStyleSheet(f"color: {color_hex}; font-size: 18px; font-weight: bold;")
            lay.addWidget(lbl)
            lay.addWidget(val)
            self.metrics_grid.addWidget(f, r, c)
            
        sff = self.project.sff or 0.0
        tot_dangerous = (self.project.dangerous_detected_rate or 0.0) + (self.project.dangerous_undetected_rate or 0.0)
        dc = (self.project.dangerous_detected_rate / tot_dangerous * 100.0) if tot_dangerous > 0.0 else 0.0
        
        # MTTFd calculation standard: MTTFd = 10^9 / (dangerous_FIT_rate * 8760)
        mttfd_val = 10**9 / (tot_dangerous * 8760.0) if tot_dangerous > 0.0 else 0.0
        
        add_metric_card("Achieved SIL", self.project.achieved_sil or "SIL 0", 0, 0, "#0dcaf0")
        add_metric_card("Target SIL", self.project.target_sil or "N/A", 0, 1, "#0d6efd")
        add_metric_card("Safe Failure Fraction (SFF)", f"{sff:.2f}%", 0, 2, "#198754")
        add_metric_card("Diagnostic Coverage (DC)", f"{dc:.2f}%", 0, 3, "#fd7e14")
        add_metric_card("MTTFd (years)", f"{mttfd_val:.1f} years" if mttfd_val > 0.0 else "N/A", 0, 4, "#6f42c1")
        
        # 3. Populate validation list
        self.validation_table.setRowCount(0)
        
        alerts = ValidationService.validate_project(self.project)
        for alert in alerts:
            self._add_alert_row(
                alert["severity"],
                alert["scope"] if alert["scope"] == "Global" else alert["scope"] + f" ({alert['item']})" if alert["row_index"] is None else alert["scope"],
                alert["item"],
                alert["message"],
                alert["unit_id"],
                alert["row_index"]
            )
            
        # Apply standard sorting / color highlight
        for r in range(self.validation_table.rowCount()):
            sev = self.validation_table.item(r, 0).text()
            if "Error" in sev:
                self.validation_table.item(r, 0).setForeground(QColor("#dc3545"))
            elif "Warning" in sev:
                self.validation_table.item(r, 0).setForeground(QColor("#ffc107"))
            else:
                self.validation_table.item(r, 0).setForeground(QColor("#0dcaf0"))
                
    def _add_alert_row(self, severity: str, group_name: str, item_name: str, desc: str, unit_id: Optional[str] = None, row_index: Optional[int] = None):
        row = self.validation_table.rowCount()
        self.validation_table.insertRow(row)
        
        sev_label = f"{severity} 🔴" if severity == "Error" else f"{severity} 🟡" if severity == "Warning" else f"{severity} 🔵"
        self.validation_table.setItem(row, 0, QTableWidgetItem(sev_label))
        
        group_item = QTableWidgetItem(group_name)
        if unit_id:
            group_item.setData(Qt.ItemDataRole.UserRole, unit_id)
        self.validation_table.setItem(row, 1, group_item)
        
        self.validation_table.setItem(row, 2, QTableWidgetItem(item_name))
        self.validation_table.setItem(row, 3, QTableWidgetItem(desc))
        
        action_item = QTableWidgetItem("Double-click to resolve" if unit_id and row_index is not None else "Manual navigation")
        action_item.setData(Qt.ItemDataRole.UserRole, row_index)
        self.validation_table.setItem(row, 4, action_item)
