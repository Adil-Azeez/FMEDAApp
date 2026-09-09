import re
import uuid
from typing import List, Dict, Tuple, Optional, Set, Any
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QComboBox,
    QCheckBox, QHeaderView, QMessageBox, QWidget, QFrame,
    QLineEdit, QSplitter, QGroupBox, QInputDialog, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from fmeda_tool.models import Unit, BOMComponent, ComponentDB, ComponentMapping, Component, FailureModeAssignment
from fmeda_tool.services.import_service import format_value_description


def parse_range_expression(expr: str, available_designators: List[str]) -> List[str]:
    """
    Parses range expressions like 'C3-C15', 'C101-C160', 'R1-R10, R15', 'C3, C4, C5-C10'.
    Returns a list of matching designators found in available_designators (preserving order).
    """
    if not expr or not expr.strip():
        return []
        
    matched: Set[str] = set()
    tokens = [t.strip() for t in expr.replace(";", ",").split(",") if t.strip()]
    
    # Pre-parse available designators into (prefix, number, original)
    parsed_avail = []
    for des in available_designators:
        m = re.match(r"^([a-zA-Z_]+)(\d+)$", des.strip())
        if m:
            parsed_avail.append((m.group(1).upper(), int(m.group(2)), des))
        else:
            parsed_avail.append((des.strip().upper(), None, des))
            
    for tok in tokens:
        # Check range pattern like C3-C15 or C3..C15 or C3:C15
        range_match = re.match(r"^([a-zA-Z_]+)(\d+)\s*(?:-|–|\.\.|:)\s*([a-zA-Z_]+)?(\d+)$", tok)
        if range_match:
            pfx1 = range_match.group(1).upper()
            num1 = int(range_match.group(2))
            pfx2 = (range_match.group(3) or pfx1).upper()
            num2 = int(range_match.group(4))
            
            if pfx1 == pfx2:
                start_num = min(num1, num2)
                end_num = max(num1, num2)
                for pfx, num, orig in parsed_avail:
                    if pfx == pfx1 and num is not None and start_num <= num <= end_num:
                        matched.add(orig)
            continue
            
        # Exact token match
        tok_upper = tok.upper()
        for pfx, num, orig in parsed_avail:
            if orig.upper() == tok_upper:
                matched.add(orig)
                
    # Return in original available_designators order
    return [d for d in available_designators if d in matched]


def format_position_ranges(positions: List[str]) -> str:
    """
    Formats a list of positions into concise range notation where possible, e.g.:
    ['C3', 'C4', 'C5', 'C6', 'C7'] -> 'C3-C7'
    """
    if not positions:
        return "None"
    if len(positions) <= 3:
        return ", ".join(positions)
        
    # Group by prefix
    grouped: Dict[str, List[int]] = {}
    non_numeric: List[str] = []
    for pos in positions:
        m = re.match(r"^([a-zA-Z_]+)(\d+)$", pos.strip())
        if m:
            pfx = m.group(1)
            num = int(m.group(2))
            grouped.setdefault(pfx, []).append(num)
        else:
            non_numeric.append(pos)
            
    formatted_parts = []
    for pfx, nums in grouped.items():
        nums.sort()
        # Find consecutive sub-sequences
        i = 0
        while i < len(nums):
            start = nums[i]
            end = start
            while i + 1 < len(nums) and nums[i + 1] == end + 1:
                end = nums[i + 1]
                i += 1
            if end - start >= 2:
                formatted_parts.append(f"{pfx}{start}-{pfx}{end}")
            elif end - start == 1:
                formatted_parts.append(f"{pfx}{start}, {pfx}{end}")
            else:
                formatted_parts.append(f"{pfx}{start}")
            i += 1
            
    formatted_parts.extend(non_numeric)
    return ", ".join(formatted_parts)


class ComponentMappingDialog(QDialog):
    """
    Dialog to batch assign multiple BOM positions to component types already added
    to the current functional group.
    """
    
    def __init__(self, unit: Unit, project_profile: str = "Profile 1", parent=None):
        super().__init__(parent)
        self.project_profile = project_profile or "Profile 1"
        self.setWindowTitle(f"Map BOM Components - {unit.name} ({self.project_profile})")
        self.setMinimumSize(1180, 720)
        self.resize(1220, 760)
        
        self.unit = unit
        
        # Collect available component types (added templates + unique existing types)
        self.available_templates: List[ComponentDB] = self._collect_available_templates()
        self.db_templates: List[ComponentDB] = self.available_templates  # Compatibility alias
        
        # Staged mappings: maps BOM designator.upper() -> ComponentDB template
        self.staged_mappings: Dict[str, ComponentDB] = {}
        self.mappings: List[ComponentMapping] = list(self.unit.component_mappings or [])
        
        # UI controls references
        self.target_rows_map: Dict[str, int] = {}  # template_id -> row_idx in targets table
        self.bom_checkboxes: Dict[str, QCheckBox] = {}  # designator.upper() -> QCheckBox
        self.selected_target_id: Optional[str] = None
        
        # Initialize staged mappings from existing unit data
        self._init_staged_mappings_from_unit()
        
        self._setup_ui()
        self._populate_targets_table()
        self._populate_bom_table()
        self._update_selection_summary()
        
    def _collect_available_templates(self) -> List[ComponentDB]:
        """
        Collects only component types already added to the current functional group.
        Does NOT query the entire SQLite or Legacy database.
        """
        templates: List[ComponentDB] = []
        seen_ids: Set[str] = set()
        
        # 1. From unit.component_templates
        for t in getattr(self.unit, "component_templates", []) or []:
            t_id = t.id or f"tmpl_{t.display_name}"
            if t_id not in seen_ids:
                templates.append(t)
                seen_ids.add(t_id)
                
        # 2. From existing physical/template components in unit.components
        for comp in getattr(self.unit, "components", []) or []:
            c_id = comp.library_component_id or comp.id
            if c_id not in seen_ids and comp.position not in ("Mapping Template", "Template"):
                tmpl = ComponentDB(
                    id=c_id,
                    display_name=comp.type or comp.name,
                    shortcut=comp.failure_rate_id or "",
                    material=comp.type,
                    fits=comp.failure_rate,
                    database=comp.source_type or "exida",
                    failure_modes=comp.failure_modes or {},
                    library_component_id=comp.library_component_id,
                    failure_rate_id=comp.failure_rate_id,
                    item_no=comp.item_no,
                    component_subtype=comp.component_subtype,
                    component_use_category=comp.component_use_category,
                    selected_profile=comp.selected_profile or self.project_profile,
                    source_type=comp.source_type or "exida",
                    snapshot=comp.snapshot
                )
                templates.append(tmpl)
                seen_ids.add(c_id)
                
        return templates

    def _init_staged_mappings_from_unit(self):
        """Initializes staged mappings from existing unit.components or unit.component_mappings."""
        template_map = {t.id: t for t in self.available_templates}
        
        # From existing components
        for comp in getattr(self.unit, "components", []) or []:
            if comp.position in ("Mapping Template", "Template"):
                continue
            t_id = comp.library_component_id or comp.id
            matched_tmpl = template_map.get(t_id)
            if not matched_tmpl:
                # Match by display name / type
                matched_tmpl = next((t for t in self.available_templates if t.display_name == comp.type or t.display_name == comp.name), None)
            if matched_tmpl:
                self.staged_mappings[comp.position.upper()] = matched_tmpl
                
        # From existing component_mappings
        bom_by_id = {b.id: b for b in getattr(self.unit, "bom_components", []) or []}
        for m in getattr(self.unit, "component_mappings", []) or []:
            if m.is_confirmed and m.bom_component_id in bom_by_id:
                bom = bom_by_id[m.bom_component_id]
                matched_tmpl = template_map.get(m.component_db_id)
                if matched_tmpl:
                    self.staged_mappings[bom.designator.upper()] = matched_tmpl

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)
        
        # Header banner
        header = QHBoxLayout()
        title_lbl = QLabel(f"<b>Batch BOM Position Mapping</b> — Functional Group: <b>{self.unit.name}</b>")
        title_lbl.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        header.addWidget(title_lbl)
        
        header.addStretch()
        
        prof_badge = QLabel(f"Profile: <b>{self.project_profile}</b>")
        prof_badge.setStyleSheet("background-color: #f1f3f5; border: 1px solid #ced4da; padding: 4px 10px; border-radius: 4px;")
        header.addWidget(prof_badge)
        main_layout.addLayout(header)
        
        # 4-Step Workflow Instruction Cards
        inst_frame = QFrame()
        inst_frame.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 4px;")
        inst_lay = QHBoxLayout(inst_frame)
        inst_lay.setContentsMargins(6, 4, 6, 4)
        inst_lay.setSpacing(6)
        
        steps = [
            ("Step 1", "Select one added component type."),
            ("Step 2", "Select one or more BOM positions."),
            ("Step 3", "Click Apply Selection to assign the positions."),
            ("Step 4", "Click Save Mappings to create the FMEDA components.")
        ]
        
        for i, (title, desc) in enumerate(steps):
            card = QFrame()
            card.setStyleSheet("background-color: #ffffff; border: 1px solid #ced4da; border-radius: 4px; padding: 4px 6px;")
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(4, 2, 4, 2)
            card_lay.setSpacing(1)
            
            title_lbl = QLabel(f"<b>{title}</b>")
            title_lbl.setStyleSheet("color: #1f497d; font-size: 11px;")
            title_lbl.setWordWrap(True)
            card_lay.addWidget(title_lbl)
            
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: #495057; font-size: 10px;")
            desc_lbl.setWordWrap(True)
            card_lay.addWidget(desc_lbl)
            
            inst_lay.addWidget(card, stretch=1)
            
            if i < len(steps) - 1:
                arrow_lbl = QLabel("→")
                arrow_lbl.setStyleSheet("color: #6c757d; font-size: 14px; font-weight: bold;")
                arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                inst_lay.addWidget(arrow_lbl, stretch=0)
                
        main_layout.addWidget(inst_frame)
        
        # Main Splitter (Left: Added Types / Right: BOM Positions)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        
        # ==========================================
        # LEFT PANEL: Added Component Types
        # ==========================================
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        target_hdr = QHBoxLayout()
        target_title = QLabel("<b>1. Added Component Types</b>")
        target_hdr.addWidget(target_title)
        target_hdr.addStretch()
        self.targets_count_lbl = QLabel(f"{len(self.available_templates)} types")
        self.targets_count_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
        target_hdr.addWidget(self.targets_count_lbl)
        left_layout.addLayout(target_hdr)
        
        self.targets_table = QTableWidget()
        self.targets_table.setColumnCount(4)
        self.targets_table.setHorizontalHeaderLabels(["Component Type", "Failure Rate ID", "FIT", "Assigned"])
        self.targets_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.targets_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.targets_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.targets_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.targets_table.verticalHeader().setVisible(False)
        self.targets_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.targets_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.targets_table.itemSelectionChanged.connect(self._on_target_selection_changed)
        left_layout.addWidget(self.targets_table)
        
        # Target details card
        self.target_details_box = QGroupBox("Selected Component Type Details")
        self.target_details_lay = QVBoxLayout(self.target_details_box)
        self.target_details_lay.setContentsMargins(10, 8, 10, 8)
        self.target_details_lbl = QLabel("No component type selected.")
        self.target_details_lbl.setWordWrap(True)
        self.target_details_lay.addWidget(self.target_details_lbl)
        left_layout.addWidget(self.target_details_box)
        
        splitter.addWidget(left_widget)
        
        # ==========================================
        # RIGHT PANEL: BOM Positions (Multi-Select)
        # ==========================================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        
        right_hdr = QHBoxLayout()
        right_title = QLabel("<b>2. BOM Positions</b>")
        right_hdr.addWidget(right_title)
        right_hdr.addStretch()
        self.bom_count_lbl = QLabel(f"{len(self.unit.bom_components)} positions")
        self.bom_count_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
        right_hdr.addWidget(self.bom_count_lbl)
        right_layout.addLayout(right_hdr)
        
        # Filter & Search bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search Pos, MN, Benennung, Wert, Beschreibung...")
        self.search_input.textChanged.connect(self._apply_bom_filters)
        filter_bar.addWidget(self.search_input, stretch=2)
        
        self.prefix_combo = QComboBox()
        self.prefix_combo.addItems(["All Prefixes", "C (Capacitor)", "R (Resistor)", "V/D (Diode/Trans)", "U/IC (IC)", "L (Inductor)", "X (Connector)", "Other"])
        self.prefix_combo.currentIndexChanged.connect(self._apply_bom_filters)
        filter_bar.addWidget(self.prefix_combo)
        
        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems(["All Positions", "Unmapped Only", "Mapped Only", "Not Fitted Only"])
        self.status_filter_combo.currentIndexChanged.connect(self._apply_bom_filters)
        filter_bar.addWidget(self.status_filter_combo)
        
        right_layout.addLayout(filter_bar)
        
        # Quick selection buttons row
        quick_bar = QHBoxLayout()
        quick_bar.setSpacing(6)
        
        select_all_btn = QPushButton("☑️ Select All Visible")
        select_all_btn.clicked.connect(self._select_all_visible)
        quick_bar.addWidget(select_all_btn)
        
        clear_sel_btn = QPushButton("⬜ Clear Selection")
        clear_sel_btn.clicked.connect(self._clear_selection)
        quick_bar.addWidget(clear_sel_btn)
        
        range_btn = QPushButton("🔢 Select Range (e.g. C3-C15)...")
        range_btn.setStyleSheet("font-weight: bold; background-color: #e7f1ff; border: 1px solid #b6d4fe;")
        range_btn.clicked.connect(self._prompt_range_selection)
        quick_bar.addWidget(range_btn)
        
        quick_bar.addStretch()
        right_layout.addLayout(quick_bar)
        
        # BOM Table (9 columns)
        self.bom_table = QTableWidget()
        self.bom_table.setColumnCount(9)
        self.bom_table.setHorizontalHeaderLabels([
            "Select", "Pos", "MN", "Benennung", "Wert",
            "Beschreibung", "Bemerkung", "Lage", "Current Mapping"
        ])
        self.bom_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.bom_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.verticalHeader().setVisible(False)
        self.bom_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        right_layout.addWidget(self.bom_table)
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter)
        
        # ==========================================
        # BOTTOM PANEL: Selection Summary & Actions
        # ==========================================
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; border-radius: 4px; padding: 10px;")
        bottom_lay = QVBoxLayout(bottom_frame)
        bottom_lay.setContentsMargins(10, 8, 10, 8)
        bottom_lay.setSpacing(8)
        
        # Header
        summary_title = QLabel("<b>3. Mapping Summary</b>")
        summary_title.setStyleSheet("font-size: 11px; color: #212529;")
        bottom_lay.addWidget(summary_title)
        
        # Summary row
        self.summary_target_lbl = QLabel("<b>Target Component Type:</b> None selected")
        self.summary_pos_lbl = QLabel("<b>Selected BOM Positions:</b> 0 positions (None)")
        bottom_lay.addWidget(self.summary_target_lbl)
        bottom_lay.addWidget(self.summary_pos_lbl)
        
        # Action buttons row
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        
        self.apply_btn = QPushButton("➕ Apply Selection to Component Type")
        self.apply_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 7px 16px; border-radius: 4px;")
        self.apply_btn.clicked.connect(self._on_apply_selection)
        act_row.addWidget(self.apply_btn)
        
        self.unmap_btn = QPushButton("➖ Unmap Selected")
        self.unmap_btn.setStyleSheet("background-color: #6c757d; color: white; padding: 7px 14px; border-radius: 4px;")
        self.unmap_btn.clicked.connect(self._on_unmap_selected)
        act_row.addWidget(self.unmap_btn)
        
        act_row.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 7px 16px;")
        cancel_btn.clicked.connect(self.reject)
        act_row.addWidget(cancel_btn)
        
        save_btn = QPushButton("💾 Save Mappings")
        save_btn.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 7px 20px; border-radius: 4px;")
        save_btn.clicked.connect(self._on_save_clicked)
        act_row.addWidget(save_btn)
        
        bottom_lay.addLayout(act_row)
        main_layout.addWidget(bottom_frame)

    def _populate_targets_table(self):
        self.targets_table.setRowCount(0)
        self.target_rows_map.clear()
        
        if not self.available_templates:
            self.targets_table.setRowCount(1)
            item = QTableWidgetItem("No component types added yet. Use 'Add Component Type' first.")
            item.setForeground(QColor("#dc3545"))
            self.targets_table.setItem(0, 0, item)
            self.targets_table.setSpan(0, 0, 1, 4)
            return
            
        for row, tmpl in enumerate(self.available_templates):
            self.targets_table.insertRow(row)
            self.target_rows_map[tmpl.id] = row
            
            # Count assigned positions in staged mappings
            assigned_count = sum(1 for target in self.staged_mappings.values() if target.id == tmpl.id)
            
            name_item = QTableWidgetItem(tmpl.display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, tmpl.id)
            self.targets_table.setItem(row, 0, name_item)
            
            fr_id = tmpl.shortcut or tmpl.failure_rate_id or "—"
            self.targets_table.setItem(row, 1, QTableWidgetItem(fr_id))
            
            fits_str = f"{tmpl.fits:.4f}" if tmpl.fits is not None else "0.0000"
            self.targets_table.setItem(row, 2, QTableWidgetItem(fits_str))
            
            cnt_item = QTableWidgetItem(f"{assigned_count} Pos")
            cnt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if assigned_count > 0:
                cnt_item.setForeground(QColor("#198754"))
                cnt_item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            self.targets_table.setItem(row, 3, cnt_item)
            
        # Pre-select first target
        if self.targets_table.rowCount() > 0:
            self.targets_table.selectRow(0)

    def _on_target_selection_changed(self):
        selected_rows = self.targets_table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_target_id = None
            self.target_details_lbl.setText("No component type selected.")
            self._update_selection_summary()
            return
            
        row = selected_rows[0].row()
        item = self.targets_table.item(row, 0)
        if not item:
            return
        t_id = item.data(Qt.ItemDataRole.UserRole)
        self.selected_target_id = t_id
        
        tmpl = next((t for t in self.available_templates if t.id == t_id), None)
        if tmpl:
            fm_summary = ", ".join(f"{k} ({v:.1f}%)" for k, v in tmpl.failure_modes.items()) if tmpl.failure_modes else "None"
            src = tmpl.database or tmpl.source_type or "exida"
            assigned_count = sum(1 for target in self.staged_mappings.values() if target.id == tmpl.id)
            
            self.target_details_lbl.setText(
                f"<b>Name:</b> {tmpl.display_name}<br>"
                f"<b>Failure Rate ID:</b> {tmpl.shortcut or tmpl.failure_rate_id or 'N/A'} &nbsp;|&nbsp; "
                f"<b>FIT:</b> {tmpl.fits or 0.0:.4f} &nbsp;|&nbsp; "
                f"<b>Source:</b> {src.capitalize()}<br>"
                f"<b>Subtype / Category:</b> {tmpl.component_subtype or 'Standard'} / {tmpl.component_use_category or 'Standard'}<br>"
                f"<b>Failure Modes:</b> {fm_summary}<br>"
                f"<b>Currently Assigned:</b> <b>{assigned_count} BOM positions</b>"
            )
        self._update_selection_summary()

    def _populate_bom_table(self):
        self.bom_table.setRowCount(0)
        self.bom_checkboxes.clear()
        
        for row, bom in enumerate(self.unit.bom_components):
            self.bom_table.insertRow(row)
            des_upper = bom.designator.upper()
            
            # Col 0: Checkbox
            cb = QCheckBox()
            cb.stateChanged.connect(self._on_bom_checkbox_changed)
            cb_widget = QWidget()
            cb_lay = QHBoxLayout(cb_widget)
            cb_lay.addWidget(cb)
            cb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_lay.setContentsMargins(0, 0, 0, 0)
            self.bom_table.setCellWidget(row, 0, cb_widget)
            self.bom_checkboxes[des_upper] = cb
            
            # Col 1: Pos
            pos_item = QTableWidgetItem(bom.designator)
            pos_item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            pos_item.setData(Qt.ItemDataRole.UserRole, bom)
            self.bom_table.setItem(row, 1, pos_item)
            
            # Col 2: MN
            mn_val = bom.internal_part_number or bom.part_number or ""
            self.bom_table.setItem(row, 2, QTableWidgetItem(mn_val))
            
            # Col 3: Benennung
            ben_val = bom.benennung or bom.function or ""
            self.bom_table.setItem(row, 3, QTableWidgetItem(ben_val))
            
            # Col 4: Wert
            self.bom_table.setItem(row, 4, QTableWidgetItem(bom.value or ""))
            
            # Col 5: Beschreibung
            self.bom_table.setItem(row, 5, QTableWidgetItem(bom.description or ""))
            
            # Col 6: Bemerkung
            bem_val = bom.notes or ""
            bem_item = QTableWidgetItem(bem_val)
            is_not_fitted = not bom.is_fitted or any(kw in bem_val.lower() for kw in ["nicht bestueckt", "nicht bestückt", "not fitted", "dnp"])
            if is_not_fitted:
                bem_item.setForeground(QColor("#856404"))
                bem_item.setBackground(QColor("#fff3cd"))
            self.bom_table.setItem(row, 6, bem_item)
            
            # Col 7: Lage
            self.bom_table.setItem(row, 7, QTableWidgetItem(bom.layer or "TOP"))
            
            # Col 8: Current Mapping
            self._update_bom_row_mapping_display(row, des_upper)

    def _update_bom_row_mapping_display(self, row: int, des_upper: str):
        target = self.staged_mappings.get(des_upper)
        if target:
            map_item = QTableWidgetItem(f"✓ {target.display_name}")
            map_item.setForeground(QColor("#198754"))
            map_item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        else:
            map_item = QTableWidgetItem("— Unmapped —")
            map_item.setForeground(QColor("#6c757d"))
        self.bom_table.setItem(row, 8, map_item)

    def _on_bom_checkbox_changed(self):
        self._update_selection_summary()

    def _get_selected_designators(self) -> List[str]:
        selected = []
        for bom in self.unit.bom_components:
            des_upper = bom.designator.upper()
            cb = self.bom_checkboxes.get(des_upper)
            if cb and cb.isChecked():
                selected.append(bom.designator)
        return selected

    def _update_selection_summary(self):
        selected_target = next((t for t in self.available_templates if t.id == self.selected_target_id), None)
        if selected_target:
            self.summary_target_lbl.setText(
                f"<b>Target Component Type:</b> <span style='color:#0d6efd;'>{selected_target.display_name}</span> "
                f"({selected_target.fits or 0.0:.4f} FIT)"
            )
        else:
            self.summary_target_lbl.setText("<b>Target Component Type:</b> <span style='color:#dc3545;'>None selected</span>")
            
        selected_positions = self._get_selected_designators()
        count = len(selected_positions)
        ranges_str = format_position_ranges(selected_positions)
        
        # Check if any selected positions are Not Fitted
        not_fitted_count = 0
        for pos in selected_positions:
            bom = next((b for b in self.unit.bom_components if b.designator.upper() == pos.upper()), None)
            if bom and (not bom.is_fitted or any(kw in (bom.notes or "").lower() for kw in ["nicht bestueckt", "nicht bestückt", "not fitted", "dnp"])):
                not_fitted_count += 1
                
        warn_text = f" &nbsp;⚠️ <span style='color:#856404;'>({not_fitted_count} Not Fitted)</span>" if not_fitted_count > 0 else ""
        
        self.summary_pos_lbl.setText(
            f"<b>Selected BOM Positions:</b> <b>{count} positions</b> — {ranges_str}{warn_text}"
        )

    def _apply_bom_filters(self):
        search_txt = self.search_input.text().strip().lower()
        pfx_filter = self.prefix_combo.currentText()
        status_filter = self.status_filter_combo.currentText()
        
        for row in range(self.bom_table.rowCount()):
            pos_item = self.bom_table.item(row, 1)
            if not pos_item:
                continue
            bom: BOMComponent = pos_item.data(Qt.ItemDataRole.UserRole)
            des_upper = bom.designator.upper()
            
            # Text search filter
            combined = f"{bom.designator} {bom.part_number or ''} {bom.internal_part_number or ''} {bom.benennung or ''} {bom.value or ''} {bom.description or ''}".lower()
            match_search = not search_txt or search_txt in combined
            
            # Prefix filter
            match_prefix = True
            if pfx_filter.startswith("C "):
                match_prefix = des_upper.startswith("C")
            elif pfx_filter.startswith("R "):
                match_prefix = des_upper.startswith("R")
            elif pfx_filter.startswith("V/D"):
                match_prefix = des_upper.startswith(("V", "D", "Q", "T"))
            elif pfx_filter.startswith("U/IC"):
                match_prefix = des_upper.startswith(("U", "IC", "N"))
            elif pfx_filter.startswith("L "):
                match_prefix = des_upper.startswith("L")
            elif pfx_filter.startswith("X "):
                match_prefix = des_upper.startswith(("X", "J", "K", "W"))
            elif pfx_filter == "Other":
                match_prefix = not des_upper.startswith(("C", "R", "V", "D", "Q", "T", "U", "IC", "N", "L", "X", "J", "K", "W"))
                
            # Status filter
            match_status = True
            is_mapped = des_upper in self.staged_mappings
            is_not_fitted = not bom.is_fitted or any(kw in (bom.notes or "").lower() for kw in ["nicht bestueckt", "nicht bestückt", "not fitted", "dnp"])
            if status_filter == "Unmapped Only":
                match_status = not is_mapped
            elif status_filter == "Mapped Only":
                match_status = is_mapped
            elif status_filter == "Not Fitted Only":
                match_status = is_not_fitted
                
            visible = match_search and match_prefix and match_status
            self.bom_table.setRowHidden(row, not visible)

    def _select_all_visible(self):
        for row in range(self.bom_table.rowCount()):
            if not self.bom_table.isRowHidden(row):
                pos_item = self.bom_table.item(row, 1)
                if pos_item:
                    des_upper = pos_item.text().strip().upper()
                    cb = self.bom_checkboxes.get(des_upper)
                    if cb:
                        cb.setChecked(True)
        self._update_selection_summary()

    def _clear_selection(self):
        for cb in self.bom_checkboxes.values():
            cb.setChecked(False)
        self._update_selection_summary()

    def _prompt_range_selection(self):
        available = [b.designator for b in self.unit.bom_components]
        text, ok = QInputDialog.getText(
            self, "Select Position Range",
            "Enter position range or list (e.g. C3-C15, C101-C160, R1-R10):\n"
            "Example: C3-C15 or C3, C4, C5-C10",
            QLineEdit.EchoMode.Normal, ""
        )
        if not ok or not text.strip():
            return
            
        matched = parse_range_expression(text.strip(), available)
        if not matched:
            QMessageBox.information(self, "Range Selection", f"No BOM positions matched the expression '{text}'.")
            return
            
        for pos in matched:
            cb = self.bom_checkboxes.get(pos.upper())
            if cb:
                cb.setChecked(True)
        self._update_selection_summary()
        QMessageBox.information(self, "Range Selected", f"Selected {len(matched)} matching BOM positions: {format_position_ranges(matched)}")

    def _on_apply_selection(self):
        selected_target = next((t for t in self.available_templates if t.id == self.selected_target_id), None)
        if not selected_target:
            QMessageBox.warning(self, "Target Required", "Please select a Component Type on the left before applying selection.")
            return
            
        selected_positions = self._get_selected_designators()
        if not selected_positions:
            QMessageBox.warning(self, "Positions Required", "Please select one or more BOM positions on the right using checkboxes.")
            return
            
        # Apply assignment to staged_mappings
        for pos in selected_positions:
            self.staged_mappings[pos.upper()] = selected_target
            
        # Refresh BOM table display for all rows
        for row in range(self.bom_table.rowCount()):
            pos_item = self.bom_table.item(row, 1)
            if pos_item:
                self._update_bom_row_mapping_display(row, pos_item.text().strip().upper())
                
        # Refresh targets table assigned counts
        self._populate_targets_table()
        # Reselect target
        if selected_target.id in self.target_rows_map:
            self.targets_table.selectRow(self.target_rows_map[selected_target.id])
            
        # Clear checkboxes after successful apply
        self._clear_selection()
        
        QMessageBox.information(
            self, "Selection Applied",
            f"Assigned {len(selected_positions)} BOM positions ({format_position_ranges(selected_positions)}) "
            f"to component type '{selected_target.display_name}'.\n\n"
            "Click 'Save Mappings' when ready to commit to the functional group."
        )

    def _on_unmap_selected(self):
        selected_positions = self._get_selected_designators()
        if not selected_positions:
            QMessageBox.warning(self, "Selection Required", "Please select one or more BOM positions to unmap.")
            return
            
        unmapped_count = 0
        for pos in selected_positions:
            if pos.upper() in self.staged_mappings:
                del self.staged_mappings[pos.upper()]
                unmapped_count += 1
                
        # Refresh BOM table display
        for row in range(self.bom_table.rowCount()):
            pos_item = self.bom_table.item(row, 1)
            if pos_item:
                self._update_bom_row_mapping_display(row, pos_item.text().strip().upper())
                
        # Refresh targets table
        self._populate_targets_table()
        self._clear_selection()
        
        QMessageBox.information(self, "Unmapped", f"Unmapped {unmapped_count} BOM positions.")

    def _on_save_clicked(self):
        if not self.staged_mappings:
            QMessageBox.warning(self, "No Mappings", "No BOM positions are currently mapped. Please assign at least one position before saving.")
            return
            
        # Group staged mappings by target template
        grouped: Dict[str, Tuple[ComponentDB, List[str]]] = {}
        for des, tmpl in self.staged_mappings.items():
            if tmpl.id not in grouped:
                grouped[tmpl.id] = (tmpl, [])
            grouped[tmpl.id][1].append(des)
            
        # Build Confirmation Breakdown
        summary_lines = []
        total_comps = 0
        for tmpl_id, (tmpl, pos_list) in grouped.items():
            total_comps += len(pos_list)
            fits_str = f"{tmpl.fits:.4f} FIT" if tmpl.fits is not None else "0.0 FIT"
            summary_lines.append(
                f"• <b>{tmpl.display_name}</b> ({fits_str}):<br>"
                f"  <b>{len(pos_list)} positions:</b> {format_position_ranges(pos_list)}"
            )
            
        confirm_msg = (
            f"<h3>Confirm BOM Mappings</h3>"
            f"<p>The following <b>{total_comps} component instances</b> will be created/updated in <b>{self.unit.name}</b>:</p>"
            f"{'<br><br>'.join(summary_lines)}<br><br>"
            f"<i>Any unmapped temporary templates will be cleanly removed.</i><br>"
            f"Do you want to proceed and save these mappings?"
        )
        
        reply = QMessageBox.question(
            self, "Confirm Save Mappings", confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        self._commit_mappings()
        self.accept()

    def _commit_mappings(self):
        """
        Commits all staged mappings into self.unit.components and self.unit.component_mappings.
        Removes any unmapped templates, creates single Component instances with grouped
        failure modes, sets Not Fitted status, and supports remapping idempotently.
        """
        bom_by_des = {b.designator.upper(): b for b in getattr(self.unit, "bom_components", []) or []}
        
        # 1. Clean up existing components:
        # Keep non-BOM manual components; remove temporary mapping templates
        new_components_list: List[Component] = []
        existing_comp_by_des: Dict[str, Component] = {}
        for comp in getattr(self.unit, "components", []) or []:
            if comp.position in ("Mapping Template", "Template") or getattr(comp, "is_template", False):
                continue
            if comp.position.upper() not in bom_by_des:
                new_components_list.append(comp)
            else:
                existing_comp_by_des[comp.position.upper()] = comp
                
        # 2. Process all staged mappings
        new_mappings: List[ComponentMapping] = []
        
        for des_upper, template in self.staged_mappings.items():
            bom = bom_by_des.get(des_upper)
            if not bom:
                continue
                
            value_desc = format_value_description(bom.value, bom.description)
            part_num = bom.internal_part_number or bom.part_number
            
            is_not_fitted = not bom.is_fitted or any(
                kw in (bom.notes or "").lower() for kw in ["nicht bestueckt", "nicht bestückt", "not fitted", "dnp"]
            )
            fitted_status = "Not Fitted" if is_not_fitted else "Fitted"
            
            # Construct Failure Mode Assignments from template
            assignments = []
            for fm_name, fm_percentage in template.failure_modes.items():
                assignments.append(FailureModeAssignment(
                    failure_mode_name=fm_name,
                    failure_rate_percentage=fm_percentage,
                    classification="dangerous_failure" if "short" in fm_name.lower() or "open" in fm_name.lower() or len(template.failure_modes) == 1 else "not_evaluated",
                    dangerous_failure_percentage=100.0 if "short" in fm_name.lower() or "open" in fm_name.lower() or len(template.failure_modes) == 1 else 0.0,
                    detection_percentage=0.0
                ))
                
            existing_comp = existing_comp_by_des.get(des_upper)
            if existing_comp:
                # REMAP existing instance
                existing_comp.name = bom.benennung or template.display_name
                existing_comp.type = template.material or template.display_name
                existing_comp.failure_rate = template.fits
                existing_comp.failure_modes = dict(template.failure_modes)
                existing_comp.failure_mode_assignments = assignments
                existing_comp.part_number = part_num
                existing_comp.internal_pn = part_num
                existing_comp.value = value_desc or existing_comp.value
                existing_comp.layer = bom.layer or existing_comp.layer
                existing_comp.notes = bom.notes or existing_comp.notes
                existing_comp.fitted_status = fitted_status
                existing_comp.library_component_id = template.id
                existing_comp.failure_rate_id = template.shortcut or template.failure_rate_id
                existing_comp.selected_profile = template.selected_profile or self.project_profile
                existing_comp.source_type = template.database or template.source_type or "exida"
                existing_comp.snapshot = template.snapshot
                new_components_list.append(existing_comp)
            else:
                # CREATE new single Component instance
                comp_id = f"comp_{uuid.uuid4().hex[:8]}"
                new_comp = Component(
                    id=comp_id,
                    position=bom.designator,
                    name=bom.benennung or template.display_name,
                    type=template.material or template.display_name,
                    failure_rate=template.fits,
                    failure_modes=dict(template.failure_modes),
                    failure_mode_assignments=assignments,
                    part_number=part_num,
                    fitted_status=fitted_status,
                    value=value_desc or None,
                    internal_pn=part_num or None,
                    layer=bom.layer or "TOP",
                    notes=bom.notes or None,
                    library_component_id=template.id,
                    failure_rate_id=template.shortcut or template.failure_rate_id,
                    item_no=template.item_no,
                    component_subtype=template.component_subtype,
                    component_use_category=template.component_use_category,
                    selected_profile=template.selected_profile or self.project_profile,
                    source_type=template.database or template.source_type or "exida",
                    snapshot=template.snapshot
                )
                new_components_list.append(new_comp)
                
            new_mappings.append(ComponentMapping(
                bom_component_id=bom.id,
                component_db_id=template.id,
                confidence=1.0,
                is_confirmed=True
            ))
            
        self.unit.components = new_components_list
        self.unit.component_mappings = new_mappings
        self.mappings = new_mappings

    def _generate_fmeda_rows(self):
        """
        Headless / programmatic entry point for mapping execution (used in automated tests).
        Uses staged_mappings if present, or reconstructs from self.mappings and self.db_templates.
        """
        if not self.staged_mappings and self.mappings:
            db_map = {t.id: t for t in (self.available_templates + getattr(self, "db_templates", []))}
            bom_by_id = {b.id: b for b in getattr(self.unit, "bom_components", []) or []}
            for m in self.mappings:
                if m.is_confirmed and m.bom_component_id in bom_by_id and m.component_db_id in db_map:
                    bom = bom_by_id[m.bom_component_id]
                    self.staged_mappings[bom.designator.upper()] = db_map[m.component_db_id]
                    
        self._commit_mappings()
