from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QTreeWidget, QTreeWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from typing import Optional, List, Dict, Any
import re

from fmeda_tool.models import Project
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.validation_service import ValidationService


class VerificationView(QWidget):
    """Page 3: Verification and validation results view"""
    
    # Signals
    back_requested = pyqtSignal()
    next_requested = pyqtSignal()
    re_verify_requested = pyqtSignal()
    alert_clicked = pyqtSignal(str, int)  # unit_id, row_index
    
    def __init__(self):
        super().__init__()
        self.project: Optional[Project] = None
        self._setup_ui()
        
    def _setup_ui(self):
        # Main layout is vertical
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Header Section
        self._create_header()
        main_layout.addWidget(self.header_frame)
        
        # 2. Scrollable Content Workspace
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(scroll_area)
        
        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)
        
        self.layout = QVBoxLayout(scroll_content)
        self.layout.setContentsMargins(30, 20, 30, 20)
        self.layout.setSpacing(15)
        
        # Grid section for target SIL vs achieved metrics (Highlighted Cards)
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(15)
        self.layout.addLayout(self.metrics_grid)
        
        # Secondary Summary Table Section
        table_lbl = QLabel("Detailed Scope Comparison Summary")
        table_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.layout.addWidget(table_lbl)
        
        self.secondary_table = QTableWidget()
        self.secondary_table.setColumnCount(3)
        self.secondary_table.setHorizontalHeaderLabels(["Parameter", "Gesamtgerät (Overall Device)", "Sicherheitskanal (Safety Channel)"])
        self.secondary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.secondary_table.setFixedHeight(280)
        self.secondary_table.setAlternatingRowColors(True)
        self.layout.addWidget(self.secondary_table)
        
        # Validation collapsible tree section
        tree_lbl = QLabel("Validation Reports (Errors, Warnings & Info Grouped by Component)")
        tree_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.layout.addWidget(tree_lbl)
        
        self.validation_tree = QTreeWidget()
        self.validation_tree.setColumnCount(3)
        self.validation_tree.setHeaderLabels(["Finding / Description", "Severity", "Action / Location"])
        self.validation_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.validation_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.validation_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.validation_tree.setColumnWidth(1, 150)
        self.validation_tree.setColumnWidth(2, 220)
        self.validation_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.layout.addWidget(self.validation_tree)
        
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
        
        self.reverify_btn = QPushButton("🔄 Re-Verify Project")
        self.reverify_btn.setStyleSheet("background-color: #6c757d; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.reverify_btn.clicked.connect(self._on_reverify)
        layout.addWidget(self.reverify_btn)
        
    def _create_navigation_bar(self, parent_layout):
        nav_frame = QFrame()
        nav_frame.setStyleSheet("background-color: #f8f9fa; border-top: 1px solid #dee2e6;")
        nav_frame.setFixedHeight(50)
        
        layout = QHBoxLayout(nav_frame)
        layout.setContentsMargins(30, 10, 30, 10)
        
        self.back_btn = QPushButton("Back to FMEDA Table")
        self.back_btn.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 6px 15px;")
        self.back_btn.clicked.connect(self._on_back)
        layout.addWidget(self.back_btn)
        
        layout.addStretch()
        
        self.next_btn = QPushButton("Next (Export Project)")
        self.next_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 20px;")
        self.next_btn.clicked.connect(self._on_next)
        layout.addWidget(self.next_btn)
        
        parent_layout.addWidget(nav_frame)
        
    def _on_back(self):
        self.back_requested.emit()
        
    def _on_reverify(self):
        self.re_verify_requested.emit()
        self.refresh_validation()
        
    def _on_next(self):
        # Check if there are blocking errors before going to export
        has_errors = False
        alerts = ValidationService.validate_project(self.project)
        for a in alerts:
            if a["severity"] == "Error":
                has_errors = True
                break
                
        if has_errors:
            QMessageBox.warning(
                self,
                "Validation Errors Present",
                "The project contains safety critical errors. You can still export, but the safety validation is not fully clean."
            )
            
        self.next_requested.emit()
        
    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        unit_id = item.data(0, Qt.ItemDataRole.UserRole)
        row_idx = item.data(1, Qt.ItemDataRole.UserRole)
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
        
        # Clear grids and tree
        for i in reversed(range(self.metrics_grid.count())):
            self.metrics_grid.itemAt(i).widget().setParent(None)
            
        self.secondary_table.setRowCount(0)
        self.validation_tree.clear()
        
        # 1. Highlight Metrics Cards
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
            
        # Highlight metrics cards (Sicherheitskanal scope)
        sff_sk = self.project.sff_sicherheitskanal or 0.0
        dc_sk = self.project.dc_sicherheitskanal or 0.0
        mttfd_sk = self.project.mttfd_sicherheitskanal or 0.0
        
        add_metric_card("Achieved SIL (Sicherheitskanal)", self.project.achieved_sil or "SIL 0", 0, 0, "#0dcaf0")
        add_metric_card("Target SIL", self.project.target_sil or "N/A", 0, 1, "#0d6efd")
        add_metric_card("SFF (Sicherheitskanal)", f"{sff_sk:.2f}%", 0, 2, "#198754")
        add_metric_card("DC (Sicherheitskanal)", f"{dc_sk:.2f}%", 0, 3, "#fd7e14")
        add_metric_card("MTTFd (Sicherheitskanal)", f"{mttfd_sk:.1f} years" if mttfd_sk > 0.0 else "N/A", 0, 4, "#6f42c1")
        
        # 2. Populate Secondary Comparison Table
        def add_summary_row(lbl, val_gg, val_sk):
            r_idx = self.secondary_table.rowCount()
            self.secondary_table.insertRow(r_idx)
            
            item_lbl = QTableWidgetItem(lbl)
            item_lbl.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            
            item_gg = QTableWidgetItem(val_gg)
            item_gg.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_gg.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            item_sk = QTableWidgetItem(val_sk)
            item_sk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_sk.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            self.secondary_table.setItem(r_idx, 0, item_lbl)
            self.secondary_table.setItem(r_idx, 1, item_gg)
            self.secondary_table.setItem(r_idx, 2, item_sk)
            
        gg_comp_count = 0
        gg_row_count = 0
        sk_comp_count = 0
        sk_row_count = 0
        
        for u in self.project.units:
            if u.included_in_safety_function:
                gg_comp_count += len(u.components)
                for comp in u.components:
                    gg_row_count += len(comp.failure_modes)
                    for assignment in comp.failure_mode_assignments:
                        if not getattr(assignment, "dont_care", False):
                            sk_row_count += 1
                    if any(not getattr(a, "dont_care", False) for a in comp.failure_mode_assignments):
                        sk_comp_count += 1

        add_summary_row("Total Failure Rate (λ total)", f"{self.project.lambda_total_gesamtgerat or 0.0:.4f} FIT", f"{self.project.lambda_total_sicherheitskanal or 0.0:.4f} FIT")
        add_summary_row("Safe Failure Rate (λ safe)", f"{self.project.lambda_safe_gesamtgerat or 0.0:.4f} FIT", f"{self.project.lambda_safe_sicherheitskanal or 0.0:.4f} FIT")
        add_summary_row("Dangerous Failure Rate (λ dangerous)", f"{self.project.lambda_dangerous_gesamtgerat or 0.0:.4f} FIT", f"{self.project.lambda_dangerous_sicherheitskanal or 0.0:.4f} FIT")
        add_summary_row("Safe Detected λsd", f"{self.project.lambda_sd_gesamtgerat or 0.0:.4f} FIT", f"{self.project.lambda_sd_sicherheitskanal or 0.0:.4f} FIT")
        add_summary_row("Safe Undetected λsu", f"{self.project.lambda_su_gesamtgerat or 0.0:.4f} FIT", f"{self.project.lambda_su_sicherheitskanal or 0.0:.4f} FIT")
        add_summary_row("Dangerous Detected λdd", f"{self.project.lambda_dd_gesamtgerat or 0.0:.4f} FIT", f"{self.project.lambda_dd_sicherheitskanal or 0.0:.4f} FIT")
        add_summary_row("Dangerous Undetected λdu", f"{self.project.lambda_du_gesamtgerat or 0.0:.4f} FIT", f"{self.project.lambda_du_sicherheitskanal or 0.0:.4f} FIT")
        
        add_summary_row("Average PFD (PFDavg)", "N/A", f"{self.project.pfd_avg or 0.0:.6e}")
        add_summary_row("Maximum PFD (PFHd)", "N/A", f"{self.project.pfd_max or 0.0:.6e} /h")
        add_summary_row("MTTFd (years)", "N/A", f"{self.project.mttfd_sicherheitskanal or 0.0:.1f} years")
        
        add_summary_row("Proof Test Interval", f"{self.project.test_interval or 8760.0:.1f} hours", f"{self.project.test_interval or 8760.0:.1f} hours")
        add_summary_row("Diagnostic Test Interval", f"{self.project.diagnostic_test_interval or 8.0:.1f} hours", f"{self.project.diagnostic_test_interval or 8.0:.1f} hours")
        add_summary_row("Component Count", str(gg_comp_count), str(sk_comp_count))
        add_summary_row("FMEDA Row Count", str(gg_row_count), str(sk_row_count))
        
        # 3. Populate Collapsible Tree Grouped by Component
        alerts = ValidationService.validate_project(self.project)
        
        # Group alerts by (unit_name, component_designator)
        grouped_alerts = {}
        for alert in alerts:
            unit_id = alert["unit_id"]
            unit = next((u for u in self.project.units if u.id == unit_id), None) if unit_id else None
            unit_name = unit.name if unit else "Global"
            
            comp_pos = "Group Level"
            if alert["scope"] == "Global":
                unit_name = "Global"
                comp_pos = "Global Issues"
            elif alert["scope"] == "Functional Group" and "BOM Component" not in alert["message"]:
                comp_pos = "Group Level"
            else:
                # Component or BOM component unmapped issue
                if unit:
                    for c in unit.components:
                        if alert["item"].startswith(c.position):
                            comp_pos = c.position
                            break
                    if comp_pos == "Group Level":
                        for b in getattr(unit, "bom_components", []) or []:
                            if alert["item"].startswith(b.designator):
                                comp_pos = b.designator
                                break
                if comp_pos == "Group Level" and alert["scope"] == "Component":
                    match = re.match(r"^([A-Za-z0-9_]+)", alert["item"])
                    if match:
                        comp_pos = match.group(1)
            
            key = (unit_name, comp_pos)
            if key not in grouped_alerts:
                grouped_alerts[key] = []
            grouped_alerts[key].append(alert)
            
        # Populate the tree
        # Sort keys placing Global first, then alphabetically by unit name, then by component
        sorted_keys = sorted(
            grouped_alerts.keys(),
            key=lambda k: (k[0] != "Global", k[0], k[1] == "Group Level", k[1])
        )
        
        for key in sorted_keys:
            unit_name, comp_pos = key
            group_alerts = grouped_alerts[key]
            
            errs = sum(1 for a in group_alerts if a["severity"] == "Error")
            warns = sum(1 for a in group_alerts if a["severity"] == "Warning")
            infos = sum(1 for a in group_alerts if a["severity"] == "Info")
            
            # Construct parent block label
            if unit_name == "Global":
                title_lbl = "Global Project Issues"
            elif comp_pos == "Group Level":
                title_lbl = f"[{unit_name}] Functional Group-Level Issues"
            else:
                title_lbl = f"[{unit_name}] Component {comp_pos}"
                
            counts_lbl = f"{errs} Errors, {warns} Warnings, {infos} Info"
            
            parent_item = QTreeWidgetItem(self.validation_tree)
            parent_item.setText(0, title_lbl)
            parent_item.setText(1, counts_lbl)
            parent_item.setText(2, "")
            
            # Apply styling to parent node
            parent_item.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))
            parent_item.setFont(1, QFont("Arial", 10, QFont.Weight.Bold))
            
            parent_color = QColor("#212529")
            if errs > 0:
                parent_color = QColor("#dc3545")  # Red
            elif warns > 0:
                parent_color = QColor("#ffc107")  # Yellow
            elif infos > 0:
                parent_color = QColor("#0dcaf0")  # Cyan/Blue
            parent_item.setForeground(0, parent_color)
            parent_item.setForeground(1, parent_color)
            
            # Add child findings under the parent
            for alert in group_alerts:
                child_item = QTreeWidgetItem(parent_item)
                
                # Format child finding label
                item_prefix = f"[{alert['item']}] " if alert['item'] and alert['item'] != comp_pos else ""
                child_item.setText(0, f"{item_prefix}{alert['message']}")
                
                sev = alert["severity"]
                sev_label = f"{sev} 🔴" if sev == "Error" else f"{sev} 🟡" if sev == "Warning" else f"{sev} 🔵"
                child_item.setText(1, sev_label)
                
                action_lbl = ""
                if alert["unit_id"] and alert["row_index"] is not None:
                    action_lbl = "Double-click to navigate"
                    child_item.setData(0, Qt.ItemDataRole.UserRole, alert["unit_id"])
                    child_item.setData(1, Qt.ItemDataRole.UserRole, alert["row_index"])
                else:
                    action_lbl = "Manual navigation"
                child_item.setText(2, action_lbl)
                
                # Apply child coloring
                if sev == "Error":
                    child_item.setForeground(1, QColor("#dc3545"))
                elif sev == "Warning":
                    child_item.setForeground(1, QColor("#ff9800"))
                else:
                    child_item.setForeground(1, QColor("#00bcd4"))
                    
        # Expand tree all by default to show reports
        self.validation_tree.expandAll()
