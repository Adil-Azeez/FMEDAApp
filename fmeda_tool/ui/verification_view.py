from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass
import re

from fmeda_tool.models import Project, Unit
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.ui.widgets import WorkflowPageHeader


@dataclass
class NormalizedAlert:
    """Standardized internal representation of a validation alert"""
    severity: str             # "Error", "Warning", "Info"
    message: str              # Description
    scope: str                # "Global", "Functional Group", "Component"
    item: str                 # Item/field name
    unit_id: Optional[str]    # Functional group ID
    row_index: Optional[int]  # FMEDA table row index (0-indexed)
    location_str: str         # Text to display in Action / Location column
    can_navigate: bool        # True only if valid unit_id and row_index


def normalize_alert(raw_alert: Any, project: Optional[Project] = None) -> NormalizedAlert:
    """
    Safely normalizes any alert into a consistent NormalizedAlert structure.
    Handles:
    - Dictionary with unit_id and row_index
    - Explicit location field (dict, tuple, list, string, or None)
    - Missing or null location
    - Non-dict / malformed objects
    """
    if not isinstance(raw_alert, dict):
        raw_alert = {
            "message": str(raw_alert) if raw_alert is not None else "Unknown validation finding",
            "severity": "Info",
            "scope": "Global"
        }

    # 1. Severity extraction & normalization
    sev_raw = str(
        raw_alert.get("severity") or raw_alert.get("level") or raw_alert.get("type") or "Warning"
    ).strip().title()
    if sev_raw.startswith("Err"):
        severity = "Error"
    elif sev_raw.startswith("Warn"):
        severity = "Warning"
    else:
        severity = "Info"

    # 2. Message extraction
    message = str(
        raw_alert.get("message") or raw_alert.get("msg") or raw_alert.get("description") or
        raw_alert.get("text") or "Validation Alert"
    ).strip()

    # 3. Item extraction
    item = str(raw_alert.get("item") or raw_alert.get("name") or raw_alert.get("field") or "").strip()

    # 4. Scope extraction
    scope = str(raw_alert.get("scope") or "").strip()

    # 5. Location extraction
    unit_id: Optional[str] = raw_alert.get("unit_id") if "unit_id" in raw_alert else None
    row_index: Optional[int] = raw_alert.get("row_index") if "row_index" in raw_alert else None
    raw_loc = raw_alert.get("location") if "location" in raw_alert else raw_alert.get("loc")

    explicit_loc_str: Optional[str] = None

    if isinstance(raw_loc, dict):
        if not unit_id:
            for k in ("unit_id", "unit", "functional_group", "fg_id", "fg"):
                if k in raw_loc and raw_loc[k] is not None:
                    unit_id = raw_loc[k]
                    break
        if row_index is None:
            for k in ("row_index", "row", "index"):
                if k in raw_loc and raw_loc[k] is not None:
                    row_index = raw_loc[k]
                    break
    elif isinstance(raw_loc, (tuple, list)):
        if len(raw_loc) >= 1 and not unit_id and raw_loc[0] is not None:
            unit_id = raw_loc[0]
        if len(raw_loc) >= 2 and row_index is None and raw_loc[1] is not None:
            row_index = raw_loc[1]
    elif isinstance(raw_loc, str) and raw_loc.strip():
        explicit_loc_str = raw_loc.strip()
        # Try to parse unit_id / row from string if not set
        if not unit_id and project and project.units:
            for u in project.units:
                if u.name in explicit_loc_str or u.id in explicit_loc_str:
                    unit_id = u.id
                    break
        if row_index is None:
            match = re.search(r"Row\s*(\d+)", explicit_loc_str, re.IGNORECASE)
            if match:
                try:
                    row_index = max(0, int(match.group(1)) - 1)
                except ValueError:
                    pass

    # Normalize unit_id string
    if unit_id is not None:
        unit_id = str(unit_id).strip()
        if unit_id.lower() in ("", "none", "null", "global"):
            unit_id = None

    # Normalize row_index integer
    if row_index is not None:
        try:
            row_index = int(row_index)
        except (ValueError, TypeError):
            row_index = None

    # Find matching unit in project
    unit = None
    if project and unit_id:
        unit = next((u for u in project.units if u.id == unit_id or u.name == unit_id), None)
        if unit:
            unit_id = unit.id

    # Infer scope if missing
    if not scope:
        if unit_id is None:
            scope = "Global"
        elif row_index is not None:
            scope = "Component"
        else:
            scope = "Functional Group"

    # Construct human-readable location string
    if explicit_loc_str and not unit:
        location_str = explicit_loc_str
    elif unit and row_index is not None:
        location_str = f"{unit.name} (Row {row_index + 1})"
    elif unit:
        location_str = f"{unit.name} (Group Level)"
    elif unit_id:
        location_str = f"{unit_id}" + (f" (Row {row_index + 1})" if row_index is not None else " (Group Level)")
    else:
        location_str = "Project-Level"

    # Navigation capability
    can_navigate = bool(unit is not None and row_index is not None)

    return NormalizedAlert(
        severity=severity,
        message=message,
        scope=scope,
        item=item,
        unit_id=unit_id,
        row_index=row_index,
        location_str=location_str,
        can_navigate=can_navigate
    )


class VerificationView(QWidget):
    """Page 3: Verification and validation results view with scoped comparison filtering"""
    
    # Signals
    back_requested = pyqtSignal()
    next_requested = pyqtSignal()
    re_verify_requested = pyqtSignal()
    alert_clicked = pyqtSignal(str, int)  # unit_id, row_index
    
    def __init__(self):
        super().__init__()
        self.project: Optional[Project] = None
        self.selected_unit_ids: Set[str] = set()
        self.unit_checkboxes: Dict[str, QCheckBox] = {}
        self._setup_ui()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Header Section with Page Title
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
        
        # Scope Header Label (Above Summary Cards)
        scope_card_header = QHBoxLayout()
        self.scope_indicator_label = QLabel("Scope: All Functional Groups")
        self.scope_indicator_label.setWordWrap(True)
        self.scope_indicator_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.scope_indicator_label.setStyleSheet("color: #0d6efd; padding-bottom: 2px;")
        scope_card_header.addWidget(self.scope_indicator_label, 1)
        self.layout.addLayout(scope_card_header)
        
        # Grid section for target SIL vs achieved metrics (Highlighted Cards)
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(15)
        
        def create_card(title: str, default_val: str, color_hex: str) -> Tuple[QFrame, QLabel]:
            f = QFrame()
            f.setStyleSheet(f"QFrame {{ background-color: #f8f9fa; border-left: 4px solid {color_hex}; border-radius: 4px; padding: 10px; }}")
            lay = QVBoxLayout(f)
            lbl = QLabel(title)
            lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
            val = QLabel(default_val)
            val.setStyleSheet(f"color: {color_hex}; font-size: 18px; font-weight: bold;")
            lay.addWidget(lbl)
            lay.addWidget(val)
            return f, val

        self.card_frame_sil, self.card_val_sil = create_card("Achieved SIL (Safety Channel)", "N/A", "#0dcaf0")
        self.card_frame_target, self.card_val_target = create_card("Project Target SIL", "N/A", "#0d6efd")
        self.card_frame_sff, self.card_val_sff = create_card("SFF (Safety Channel)", "N/A", "#198754")
        self.card_frame_dc, self.card_val_dc = create_card("DC (Safety Channel)", "N/A", "#fd7e14")
        self.card_frame_mttfd, self.card_val_mttfd = create_card("MTTFd (Safety Channel)", "N/A", "#6f42c1")

        self.metrics_grid.addWidget(self.card_frame_sil, 0, 0)
        self.metrics_grid.addWidget(self.card_frame_target, 0, 1)
        self.metrics_grid.addWidget(self.card_frame_sff, 0, 2)
        self.metrics_grid.addWidget(self.card_frame_dc, 0, 3)
        self.metrics_grid.addWidget(self.card_frame_mttfd, 0, 4)

        self.layout.addLayout(self.metrics_grid)
        
        # Secondary Summary Table Section with Scope Selector
        scope_header_lay = QHBoxLayout()
        table_lbl = QLabel("Independent Functional-Group Results")
        table_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        scope_header_lay.addWidget(table_lbl)
        scope_header_lay.addStretch()
        self.layout.addLayout(scope_header_lay)
        
        # Scope Selector Box
        self.scope_box = QFrame()
        self.scope_box.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 10px;")
        self.scope_layout = QVBoxLayout(self.scope_box)
        self.scope_layout.setSpacing(8)
        
        scope_top = QHBoxLayout()
        scope_lbl = QLabel("<b>Included Functional Groups for Comparison:</b>")
        scope_top.addWidget(scope_lbl)
        scope_top.addStretch()
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setStyleSheet("padding: 3px 8px; font-size: 11px;")
        self.select_all_btn.clicked.connect(self._select_all_groups)
        scope_top.addWidget(self.select_all_btn)
        
        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setStyleSheet("padding: 3px 8px; font-size: 11px;")
        self.clear_all_btn.clicked.connect(self._clear_all_groups)
        scope_top.addWidget(self.clear_all_btn)
        self.scope_layout.addLayout(scope_top)
        
        selector_scroll = QScrollArea()
        selector_scroll.setWidgetResizable(True)
        selector_scroll.setFixedHeight(75)
        selector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        selector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        selector_content = QWidget()
        self.scope_checkboxes_layout = QHBoxLayout(selector_content)
        self.scope_checkboxes_layout.setContentsMargins(0, 0, 0, 0)
        selector_scroll.setWidget(selector_content)
        self.scope_layout.addWidget(selector_scroll)
        self.layout.addWidget(self.scope_box)
        
        self.secondary_table = QTableWidget()
        self.secondary_table.setColumnCount(0)
        self.secondary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.secondary_table.horizontalHeader().setDefaultSectionSize(180)
        self.secondary_table.horizontalHeader().setMinimumSectionSize(140)
        self.secondary_table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.secondary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.secondary_table.setMinimumHeight(520)
        self.secondary_table.setAlternatingRowColors(True)
        self.layout.addWidget(self.secondary_table)
        
        # Validation collapsible tree section
        tree_lbl = QLabel("Validation Reports (Project-wide Findings Grouped by Component)")
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
        self.header_frame = WorkflowPageHeader("Page 3: Project Verification")
        
        self.project_name_label = QLabel("Untitled Project")
        self.project_name_label.setStyleSheet("color: #495057; font-weight: bold; font-size: 11px;")
        self.header_frame.left_layout.addWidget(self.project_name_label)
        
        self.reverify_btn = QPushButton("🔄 Re-Verify Project")
        self.reverify_btn.setStyleSheet("background-color: #6c757d; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.reverify_btn.clicked.connect(self._on_reverify)
        self.header_frame.right_layout.addWidget(self.reverify_btn)
        
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
        has_errors = False
        if self.project:
            raw_alerts = ValidationService.validate_project(self.project)
            for ra in raw_alerts:
                norm = normalize_alert(ra, self.project)
                if norm.severity == "Error":
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
        if unit_id is not None and row_idx is not None:
            try:
                self.alert_clicked.emit(str(unit_id), int(row_idx))
            except (ValueError, TypeError):
                pass
            
    def load_project(self, project: Project):
        self.project = project
        self.project_name_label.setText(project.name)
        if project and project.units:
            self.selected_unit_ids = {u.id for u in project.units}
        else:
            self.selected_unit_ids = set()
        self.refresh_validation()
        
    def _rebuild_scope_selectors(self):
        """Rebuilds scope checkboxes for current project units."""
        for i in reversed(range(self.scope_checkboxes_layout.count())):
            item = self.scope_checkboxes_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
                
        self.unit_checkboxes.clear()
        if not self.project or not self.project.units:
            return
            
        for u in self.project.units:
            cb = QCheckBox(u.name)
            cb.setChecked(u.id in self.selected_unit_ids)
            cb.stateChanged.connect(lambda state, uid=u.id: self._on_scope_checkbox_changed(uid, state))
            self.unit_checkboxes[u.id] = cb
            self.scope_checkboxes_layout.addWidget(cb)
            
        self.scope_checkboxes_layout.addStretch()

    def _on_scope_checkbox_changed(self, unit_id: str, state: int):
        if state == Qt.CheckState.Checked.value or state == Qt.CheckState.Checked:
            self.selected_unit_ids.add(unit_id)
        else:
            if len(self.selected_unit_ids) <= 1 and unit_id in self.selected_unit_ids:
                # Require at least one selected group
                QMessageBox.warning(self, "Selection Required", "At least one functional group must remain selected for scope comparison.")
                cb = self.unit_checkboxes.get(unit_id)
                if cb:
                    cb.blockSignals(True)
                    cb.setChecked(True)
                    cb.blockSignals(False)
                return
            self.selected_unit_ids.discard(unit_id)
            
        self._update_scope_results()

    def _select_all_groups(self):
        if not self.project:
            return
        self.selected_unit_ids = {u.id for u in self.project.units}
        for cb in self.unit_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self._update_scope_results()

    def _clear_all_groups(self):
        if not self.project or not self.project.units:
            return
        # Keep the first unit checked
        first_u = self.project.units[0]
        self.selected_unit_ids = {first_u.id}
        for uid, cb in self.unit_checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(uid == first_u.id)
            cb.blockSignals(False)
        self._update_scope_results()

    def _update_scope_results(self):
        units = [u for u in self.project.units if u.id in self.selected_unit_ids] if self.project else []
        self.scope_indicator_label.setText("Independent groups: " + (", ".join(u.name for u in units) or "None"))
        self.group_results = [CalculationService.calculate_group_result(u, self.project) for u in units]
        for frame in (self.card_frame_sil, self.card_frame_target, self.card_frame_sff,
                      self.card_frame_dc, self.card_frame_mttfd):
            frame.setVisible(len(units) == 1)
        result = self.group_results[0] if len(units) == 1 else {}
        self.card_val_sil.setText(str(result.get("achieved_sil", "N/A")))
        self.card_val_target.setText(self.project.target_sil or "N/A" if self.project else "N/A")
        self.card_val_sff.setText(self._format_metric(result.get("sff"), "pct"))
        self.card_val_dc.setText(self._format_metric(result.get("dc"), "pct"))
        self.card_val_mttfd.setText(self._format_metric(result.get("mttfd"), "years"))
        table = self.secondary_table
        previous_widths = {table.horizontalHeaderItem(c).data(Qt.ItemDataRole.UserRole): table.columnWidth(c)
                           for c in range(table.columnCount()) if table.horizontalHeaderItem(c)}
        table.clear()
        table.setRowCount(len(CalculationService.GROUP_METRICS))
        table.setColumnCount(len(units))
        table.setVerticalHeaderLabels([label for _, label, _ in CalculationService.GROUP_METRICS])
        for col, (unit, result) in enumerate(zip(units, self.group_results)):
            header = QTableWidgetItem(unit.name)
            header.setData(Qt.ItemDataRole.UserRole, unit.id)
            header.setToolTip(unit.name)
            table.setHorizontalHeaderItem(col, header)
            table.setColumnWidth(col, previous_widths.get(unit.id, max(180, table.fontMetrics().horizontalAdvance(unit.name) + 30)))
            for row, (key, label, style) in enumerate(CalculationService.GROUP_METRICS):
                item = QTableWidgetItem(self._format_metric(result[key], style))
                item.setData(Qt.ItemDataRole.UserRole, result[key])
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, col, item)

    @staticmethod
    def _format_metric(value, style):
        if value is None:
            return "N/A"
        if style == "text":
            return str(value)
        if style == "scientific":
            return f"{value:.6e}"
        if style == "pct":
            return f"{value:.2f}%"
        if style == "years":
            return f"{value:.1f} years"
        return f"{value:.4f} FIT"

    def _populate_secondary_table(self):
        self._update_scope_results()

    def refresh_validation(self):
        if not self.project:
            return
            
        self.validation_tree.clear()
        self._rebuild_scope_selectors()
        
        # Update cards, scope indicator, and secondary table
        self._update_scope_results()
        
        # Populate Collapsible Tree Grouped by Component
        raw_alerts = ValidationService.validate_project(self.project) if self.project else []
        normalized_alerts: List[NormalizedAlert] = []
        for ra in raw_alerts:
            try:
                norm = normalize_alert(ra, self.project)
                normalized_alerts.append(norm)
            except Exception as ex:
                # One malformed alert must never prevent remaining alerts from appearing
                normalized_alerts.append(NormalizedAlert(
                    severity="Warning",
                    message=f"Alert parse error: {ex}",
                    scope="Global",
                    item="Validation System",
                    unit_id=None,
                    row_index=None,
                    location_str="Project-Level",
                    can_navigate=False
                ))

        grouped_alerts: Dict[Tuple[str, str], List[NormalizedAlert]] = {}
        for alert in normalized_alerts:
            unit_name = "Global"
            if alert.unit_id and self.project:
                u_obj = next((u for u in self.project.units if u.id == alert.unit_id), None)
                if u_obj:
                    unit_name = u_obj.name
                    
            comp_pos = "Global Issues"
            if unit_name == "Global" or alert.scope == "Global":
                unit_name = "Global"
                comp_pos = "Global Issues"
            elif alert.scope == "Functional Group" and "BOM Component" not in alert.message:
                comp_pos = "Group Level"
            else:
                comp_pos = "Group Level"
                if self.project and alert.unit_id:
                    u_obj = next((u for u in self.project.units if u.id == alert.unit_id), None)
                    if u_obj:
                        for c in u_obj.components:
                            if alert.item.startswith(c.position):
                                comp_pos = c.position
                                break
                        if comp_pos == "Group Level":
                            for b in getattr(u_obj, "bom_components", []) or []:
                                if alert.item.startswith(b.designator):
                                    comp_pos = b.designator
                                    break
                if comp_pos == "Group Level" and alert.item:
                    match = re.match(r"^([A-Za-z0-9_]+)", alert.item)
                    if match:
                        comp_pos = match.group(1)
                if comp_pos == "Group Level" and alert.row_index is not None:
                    comp_pos = f"Row {alert.row_index + 1}"

            key = (unit_name, comp_pos)
            if key not in grouped_alerts:
                grouped_alerts[key] = []
            grouped_alerts[key].append(alert)

        sorted_keys = sorted(
            grouped_alerts.keys(),
            key=lambda x: (0 if x[0] == "Global" else 1, x[0], 0 if x[1] in ("Global Issues", "Group Level") else 1, x[1])
        )

        for unit_name, comp_pos in sorted_keys:
            items_list = grouped_alerts[(unit_name, comp_pos)]
            has_error = any(a.severity == "Error" for a in items_list)
            has_warning = any(a.severity == "Warning" for a in items_list)
            
            icon_str = "🔴" if has_error else ("🟡" if has_warning else "ℹ️")
            group_item = QTreeWidgetItem([f"{icon_str} {unit_name} — {comp_pos} ({len(items_list)} findings)", "", ""])
            group_item.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))
            
            for alert in items_list:
                sev_icon = "🔴 Error" if alert.severity == "Error" else ("🟡 Warning" if alert.severity == "Warning" else "ℹ️ Info")
                
                child = QTreeWidgetItem([alert.message, sev_icon, alert.location_str])
                child.setData(0, Qt.ItemDataRole.UserRole, alert.unit_id if alert.can_navigate else None)
                child.setData(1, Qt.ItemDataRole.UserRole, alert.row_index if alert.can_navigate else None)
                
                if alert.severity == "Error":
                    child.setForeground(1, QColor("#dc3545"))
                elif alert.severity == "Warning":
                    child.setForeground(1, QColor("#fd7e14"))
                else:
                    child.setForeground(1, QColor("#0d6efd"))
                    
                group_item.addChild(child)
                
            self.validation_tree.addTopLevelItem(group_item)
            group_item.setExpanded(True)

