import re
import uuid
from typing import List, Dict, Tuple, Optional, Set, Any
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QComboBox,
    QCheckBox, QHeaderView, QMessageBox, QWidget, QFrame,
    QLineEdit, QSplitter, QGroupBox, QInputDialog, QAbstractItemView,
    QRadioButton, QButtonGroup, QScrollArea, QFormLayout, QToolTip,
    QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from fmeda_tool.models import (
    Unit, BOMComponent, ComponentDB, ComponentMapping,
    Component, FailureModeAssignment, Project
)
from fmeda_tool.services.import_service import format_value_description
from fmeda_tool.services.component_library_service import ComponentLibraryService
from fmeda_tool.ui.dialogs.bom_import_dialog import BOMImportDialog
from fmeda_tool.ui.dialogs.custom_component_dialog import CustomComponentDialog


def parse_range_expression(expr: str, available_designators: List[str]) -> List[str]:
    """
    Parses range expressions like 'C3-C15', 'C101-C160', 'R1-R10, R15', 'C3, C4, C5-C10'.
    Returns a list of matching designators found in available_designators (preserving order).
    """
    if not expr or not expr.strip():
        return []
        
    matched: Set[str] = set()
    tokens = [t.strip() for t in expr.replace(";", ",").split(",") if t.strip()]
    
    parsed_avail = []
    for des in available_designators:
        m = re.match(r"^([a-zA-Z_]+)(\d+)$", des.strip())
        if m:
            parsed_avail.append((m.group(1).upper(), int(m.group(2)), des))
        else:
            parsed_avail.append((des.strip().upper(), None, des))
            
    for tok in tokens:
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
            
        tok_upper = tok.upper()
        for pfx, num, orig in parsed_avail:
            if orig.upper() == tok_upper:
                matched.add(orig)
                
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
    Integrated Component & BOM Mapping Workspace.
    Provides in-workspace Component Library browsing (Exida & Legacy),
    in-workspace BOM TXT import, multi-position selection / range mapping,
    read-only reliability metadata, and atomic commit to FMEDA.
    """
    
    def __init__(self, unit: Unit, project_profile: str = "Profile 1", project: Optional[Project] = None, parent=None):
        super().__init__(parent)
        self.unit = unit
        self.project_profile = project_profile or "Profile 1"
        self.project = project
        
        self.setWindowTitle(f"Component & BOM Mapping - {unit.name} ({self.project_profile})")
        self.setMinimumSize(950, 580)
        self.resize(1420, 880)
        
        # Staged mappings: BOM designator.upper() -> ComponentDB template
        self.staged_mappings: Dict[str, ComponentDB] = {}
        self.mappings: List[ComponentMapping] = list(self.unit.component_mappings or [])
        self._custom_templates: Optional[List[ComponentDB]] = None
        
        # Currently selected library template & snapshot
        self.selected_template: Optional[ComponentDB] = None
        self.selected_snapshot: Optional[Dict[str, Any]] = None
        
        # UI controls references
        self.bom_checkboxes: Dict[str, QCheckBox] = {}
        
        # Initialize staged mappings from existing unit data
        self._init_staged_mappings_from_unit()
        
        self._setup_ui()
        self._populate_category_filter()
        self._on_library_search()
        self._populate_bom_table()
        self._update_selection_summary()
        
    @property
    def available_templates(self) -> List[ComponentDB]:
        """Provides compatibility with existing test suites."""
        if self._custom_templates is not None:
            return list(self._custom_templates)
        if getattr(self.unit, "component_templates", None):
            return list(self.unit.component_templates)
        templates = []
        seen = set()
        for t in self.staged_mappings.values():
            if t.id not in seen:
                templates.append(t)
                seen.add(t.id)
        if self.selected_template and self.selected_template.id not in seen:
            templates.append(self.selected_template)
            seen.add(self.selected_template.id)
        return templates

    @available_templates.setter
    def available_templates(self, value: List[ComponentDB]):
        self._custom_templates = list(value)

    @property
    def db_templates(self) -> List[ComponentDB]:
        """Alias for available_templates."""
        return self.available_templates

    @db_templates.setter
    def db_templates(self, value: List[ComponentDB]):
        self._custom_templates = list(value)

    def _init_staged_mappings_from_unit(self):
        """Initializes staged mappings from existing unit components."""
        for comp in getattr(self.unit, "components", []) or []:
            if comp.position in ("Mapping Template", "Template") or getattr(comp, "is_template", False):
                continue

            disp_label = None
            if comp.snapshot and isinstance(comp.snapshot, dict):
                disp_label = comp.snapshot.get("displayed_label") or comp.snapshot.get("display_name")
            if not disp_label and comp.library_component_id:
                try:
                    if comp.source_type == "legacy" or getattr(comp, "database", "") == "legacy":
                        snap = ComponentLibraryService.get_legacy_component_snapshot(comp.library_component_id)
                    else:
                        snap = ComponentLibraryService.get_exida_component_snapshot(comp.library_component_id, comp.selected_profile or self.project_profile)
                    if snap:
                        disp_label = snap.get("displayed_label") or snap.get("display_name")
                except Exception:
                    pass
            if not disp_label:
                disp_label = comp.name or comp.type

            tmpl = ComponentDB(
                id=comp.library_component_id or comp.id,
                display_name=disp_label,
                shortcut=comp.failure_rate_id or "",
                material=comp.type,
                fits=comp.failure_rate,
                database=comp.source_type or "exida",
                failure_modes=dict(comp.failure_modes or {}),
                library_component_id=comp.library_component_id,
                failure_rate_id=comp.failure_rate_id,
                item_no=comp.item_no,
                component_subtype=comp.component_subtype,
                component_use_category=comp.component_use_category,
                selected_profile=comp.selected_profile or self.project_profile,
                source_type=comp.source_type or "exida",
                snapshot=comp.snapshot
            )
            self.staged_mappings[comp.position.upper()] = tmpl

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(6)
        
        # 1. Compact Top Header Bar
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        
        title_lbl = QLabel(f"<b>Component & BOM Mapping</b> — Functional Group: <span style='color: #0d6efd; font-weight: bold;'>{self.unit.name}</span>")
        title_lbl.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        header.addWidget(title_lbl)
        
        header.addStretch()
        
        prof_badge = QLabel(f"Profile: <b>{self.project_profile}</b>")
        prof_badge.setStyleSheet("background-color: #f1f3f5; border: 1px solid #ced4da; padding: 3px 10px; border-radius: 4px; font-size: 11px;")
        header.addWidget(prof_badge)
        
        help_btn = QPushButton("ℹ️ Workflow Help")
        help_btn.setStyleSheet("background-color: #e7f1ff; border: 1px solid #b6d4fe; color: #0d6efd; font-weight: bold; padding: 3px 12px; border-radius: 4px; font-size: 11px;")
        help_btn.setToolTip(
            "Workflow Help:\n"
            "1. Import BOM — Click 'Import BOM TXT' on the right if positions are not loaded.\n"
            "2. Select Component — Browse and select a component from the library on the left.\n"
            "3. Select BOM Positions — Check one or more BOM positions on the right.\n"
            "4. Apply Selection — Click 'Apply Selection' to assign the component.\n"
            "5. Save Mappings — Click 'Save Mappings' to create FMEDA components."
        )
        help_btn.clicked.connect(self._show_workflow_help)
        header.addWidget(help_btn)
        
        main_layout.addLayout(header)
        
        # 2. Main Horizontal Splitter (Left: Library & Config / Right: BOM Positions)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        
        # ==========================================
        # LEFT PANEL: Component Library & Config
        # ==========================================
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_splitter.setChildrenCollapsible(False)
        
        # Top half: Component Library Browser
        lib_widget = QWidget()
        lib_layout = QVBoxLayout(lib_widget)
        lib_layout.setContentsMargins(0, 0, 0, 0)
        lib_layout.setSpacing(4)
        
        lib_hdr = QHBoxLayout()
        lib_hdr.setSpacing(6)
        lib_title = QLabel("<b>1. Component Library</b>")
        lib_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        lib_hdr.addWidget(lib_title)
        lib_hdr.addStretch()
        
        # Catalog selector radio buttons
        self.exida_radio = QRadioButton("Exida Components")
        self.exida_radio.setChecked(True)
        self.legacy_radio = QRadioButton("Legacy Unmapped")
        self.custom_radio = QRadioButton("Custom Components")
        self.source_group = QButtonGroup(self)
        self.source_group.addButton(self.exida_radio)
        self.source_group.addButton(self.legacy_radio)
        self.source_group.addButton(self.custom_radio)
        self.exida_radio.toggled.connect(self._on_library_search)
        self.legacy_radio.toggled.connect(self._on_library_search)
        self.custom_radio.toggled.connect(self._on_library_search)
        lib_hdr.addWidget(self.exida_radio)
        lib_hdr.addWidget(self.legacy_radio)
        lib_hdr.addWidget(self.custom_radio)
        
        self.new_custom_btn = QPushButton("➕ New Custom")
        self.new_custom_btn.setStyleSheet("padding: 2px 8px; font-size: 11px; font-weight: bold;")
        self.new_custom_btn.clicked.connect(self._on_new_custom_clicked)
        lib_hdr.addWidget(self.new_custom_btn)
        
        lib_layout.addLayout(lib_hdr)
        
        # Search & Filter bar
        lib_filter_bar = QHBoxLayout()
        lib_filter_bar.setSpacing(6)
        
        self.lib_search_input = QLineEdit()
        self.lib_search_input.setPlaceholderText("Search name, type, alias, FR-ID, item no...")
        self.lib_search_input.textChanged.connect(self._on_library_search)
        lib_filter_bar.addWidget(self.lib_search_input, stretch=2)
        
        self.lib_category_combo = QComboBox()
        self.lib_category_combo.addItem("All Categories")
        self.lib_category_combo.currentIndexChanged.connect(self._on_library_search)
        lib_filter_bar.addWidget(self.lib_category_combo, stretch=1)
        lib_layout.addLayout(lib_filter_bar)
        
        # Library Table
        self.lib_table = QTableWidget()
        self.lib_table.setColumnCount(4)
        self.lib_table.setHorizontalHeaderLabels(["Display Label", "Type / Subtype", "FR-ID / Item No", f"FIT ({self.project_profile})"])
        self.lib_table.horizontalHeader().setMinimumSectionSize(75)
        self.lib_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.lib_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.lib_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.lib_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.lib_table.setColumnWidth(0, 200)
        self.lib_table.setColumnWidth(2, 125)
        self.lib_table.setColumnWidth(3, 85)
        self.lib_table.verticalHeader().setVisible(False)
        self.lib_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lib_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lib_table.itemSelectionChanged.connect(self._on_lib_table_selection_changed)
        lib_layout.addWidget(self.lib_table, stretch=1)
        
        self.left_splitter.addWidget(lib_widget)
        
        # Bottom half: Selected Component Configuration & Failure Modes
        cfg_box = QGroupBox("Selected Component Configuration & Failure Modes")
        cfg_lay = QVBoxLayout(cfg_box)
        cfg_lay.setContentsMargins(8, 6, 8, 6)
        cfg_lay.setSpacing(4)
        
        # Compact 2x2 Grid Layout for inputs
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 2)
        
        lbl_des = QLabel("Label / Shortcut:")
        lbl_des.setStyleSheet("font-size: 11px;")
        grid.addWidget(lbl_des, 0, 0)
        self.cfg_label_input = QLineEdit()
        self.cfg_label_input.setPlaceholderText("e.g. C_CERAMIC, R_METAL_FILM...")
        grid.addWidget(self.cfg_label_input, 0, 1)
        
        lbl_type = QLabel("Component Type:")
        lbl_type.setStyleSheet("font-size: 11px;")
        grid.addWidget(lbl_type, 0, 2)
        self.cfg_type_input = QLineEdit()
        self.cfg_type_input.setReadOnly(True)
        self.cfg_type_input.setStyleSheet("background-color: #e9ecef; color: #495057;")
        grid.addWidget(self.cfg_type_input, 0, 3)
        
        lbl_val = QLabel("Value / Desc:")
        lbl_val.setStyleSheet("font-size: 11px;")
        grid.addWidget(lbl_val, 1, 0)
        self.cfg_value_input = QLineEdit()
        self.cfg_value_input.setPlaceholderText("e.g. 100nF, 10k, TPS5430...")
        grid.addWidget(self.cfg_value_input, 1, 1)
        
        lbl_fit = QLabel("Failure Rate (FIT):")
        lbl_fit.setStyleSheet("font-size: 11px;")
        grid.addWidget(lbl_fit, 1, 2)
        self.cfg_fit_input = QLineEdit()
        self.cfg_fit_input.setReadOnly(True)
        self.cfg_fit_input.setStyleSheet("background-color: #e9ecef; color: #495057;")
        grid.addWidget(self.cfg_fit_input, 1, 3)
        
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        cfg_lay.addLayout(grid)
        
        # Failure Modes Table (Read-Only from Library)
        fm_hdr = QHBoxLayout()
        fm_hdr.setContentsMargins(0, 2, 0, 2)
        fm_title = QLabel("<b>Failure Mode Distribution (Read-Only from Library):</b>")
        fm_title.setStyleSheet("font-size: 11px;")
        fm_hdr.addWidget(fm_title)
        fm_hdr.addStretch()
        self.cfg_fm_total_lbl = QLabel("Total: 0.0%")
        self.cfg_fm_total_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
        fm_hdr.addWidget(self.cfg_fm_total_lbl)
        cfg_lay.addLayout(fm_hdr)
        
        self.cfg_fm_table = QTableWidget()
        self.cfg_fm_table.setColumnCount(3)
        self.cfg_fm_table.setHorizontalHeaderLabels(["Failure Mode", "Distribution %", "Classification"])
        self.cfg_fm_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cfg_fm_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.cfg_fm_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.cfg_fm_table.verticalHeader().setVisible(False)
        self.cfg_fm_table.setMinimumHeight(120)
        cfg_lay.addWidget(self.cfg_fm_table, stretch=1)
        
        self.left_splitter.addWidget(cfg_box)
        self.left_splitter.setStretchFactor(0, 55)
        self.left_splitter.setStretchFactor(1, 45)
        self.left_splitter.setSizes([430, 370])
        
        self.main_splitter.addWidget(self.left_splitter)
        
        # ==========================================
        # RIGHT PANEL: BOM Positions & In-Workspace Import
        # ==========================================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        
        right_hdr = QHBoxLayout()
        right_title = QLabel("<b>2. BOM Positions</b>")
        right_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        right_hdr.addWidget(right_title)
        
        self.bom_count_lbl = QLabel(f"{len(self.unit.bom_components)} positions")
        self.bom_count_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
        right_hdr.addWidget(self.bom_count_lbl)
        right_hdr.addStretch()
        
        # In-workspace Import BOM TXT Button
        self.import_bom_btn = QPushButton("📥 Import BOM TXT")
        self.import_bom_btn.setStyleSheet("background-color: #e7f1ff; border: 1px solid #b6d4fe; color: #0d6efd; font-weight: bold; padding: 3px 12px; border-radius: 4px; font-size: 11px;")
        self.import_bom_btn.clicked.connect(self._on_in_dialog_import_bom_txt)
        right_hdr.addWidget(self.import_bom_btn)
        right_layout.addLayout(right_hdr)
        
        # Filter & Search bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)
        
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
        range_btn.setStyleSheet("font-weight: bold; background-color: #f8f9fa; border: 1px solid #ced4da;")
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
        right_layout.addWidget(self.bom_table, stretch=1)
        
        self.main_splitter.addWidget(right_widget)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([690, 710])
        main_layout.addWidget(self.main_splitter, stretch=1)
        
        # ==========================================
        # BOTTOM PANEL: Selection Summary & Actions
        # ==========================================
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; border-radius: 4px;")
        bottom_lay = QVBoxLayout(bottom_frame)
        bottom_lay.setContentsMargins(10, 6, 10, 6)
        bottom_lay.setSpacing(4)
        
        summary_title = QLabel("<b>3. Mapping Summary</b>")
        summary_title.setStyleSheet("font-size: 11px; color: #212529;")
        bottom_lay.addWidget(summary_title)
        
        # Summary row
        summary_row = QHBoxLayout()
        self.summary_target_lbl = QLabel("<b>Selected Component:</b> None selected")
        self.summary_pos_lbl = QLabel("<b>Selected Positions:</b> 0 positions (None) &nbsp;|&nbsp; <b>Total Selected:</b> 0")
        summary_row.addWidget(self.summary_target_lbl)
        summary_row.addSpacing(20)
        summary_row.addWidget(self.summary_pos_lbl)
        summary_row.addStretch()
        bottom_lay.addLayout(summary_row)
        
        # Action buttons row
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        
        self.apply_btn = QPushButton("➕ Apply Selection")
        self.apply_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px;")
        self.apply_btn.clicked.connect(self._on_apply_selection)
        act_row.addWidget(self.apply_btn)
        
        self.unmap_btn = QPushButton("➖ Unmap Selected")
        self.unmap_btn.setStyleSheet("background-color: #6c757d; color: white; padding: 6px 14px; border-radius: 4px;")
        self.unmap_btn.clicked.connect(self._on_unmap_selected)
        act_row.addWidget(self.unmap_btn)
        
        act_row.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 6px 16px;")
        cancel_btn.clicked.connect(self.reject)
        act_row.addWidget(cancel_btn)
        
        self.save_btn = QPushButton("💾 Save Mappings")
        self.save_btn.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 6px 22px; border-radius: 4px;")
        self.save_btn.clicked.connect(self._on_save_clicked)
        act_row.addWidget(self.save_btn)
        
        bottom_lay.addLayout(act_row)
        main_layout.addWidget(bottom_frame)

    def _show_workflow_help(self):
        """Displays workflow help dialog."""
        msg = (
            "<h3>Component & BOM Mapping Workflow</h3>"
            "<ol>"
            "<li><b>Import BOM TXT</b>: Click <code>📥 Import BOM TXT</code> on the right if BOM positions are not yet loaded.</li>"
            "<li><b>Select Component</b>: Browse and select a component type from the library on the left.</li>"
            "<li><b>Select BOM Positions</b>: Check one or more BOM positions on the right (use filters or range selection like <code>C3-C15</code>).</li>"
            "<li><b>Apply Selection</b>: Click <code>➕ Apply Selection</code> to assign the positions to the selected component.</li>"
            "<li><b>Save Mappings</b>: Click <code>💾 Save Mappings</code> to generate the FMEDA rows in the functional group.</li>"
            "</ol>"
        )
        QMessageBox.information(self, "Workflow Help", msg)

    def _populate_category_filter(self):
        """Populates category filter dropdown with distinct component types."""
        try:
            curr = self.lib_category_combo.currentText()
            self.lib_category_combo.blockSignals(True)
            self.lib_category_combo.clear()
            self.lib_category_combo.addItem("All Categories")
            filters = ComponentLibraryService.get_distinct_filter_values()
            types = filters.get("component_types", [])
            for t in types:
                if t:
                    self.lib_category_combo.addItem(t)
            self.lib_category_combo.setCurrentText(curr if curr in types else "All Categories")
            self.lib_category_combo.blockSignals(False)
        except Exception:
            pass

    def _on_new_custom_clicked(self):
        dlg = CustomComponentDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._populate_category_filter()
            self.custom_radio.setChecked(True)
            self._on_library_search()

    def _on_library_search(self):
        query = self.lib_search_input.text().strip()
        cat_filter = self.lib_category_combo.currentText()
        comp_type = None if cat_filter == "All Categories" else cat_filter
        
        # Save existing column widths before rebuilding
        saved_widths = [self.lib_table.columnWidth(i) for i in range(self.lib_table.columnCount())]
        
        self.lib_table.setRowCount(0)
        if self.exida_radio.isChecked():
            self.lib_table.setColumnCount(4)
            self.lib_table.setHorizontalHeaderLabels(["Display Label", "Type / Subtype", "FR-ID / Item No", f"FIT ({self.project_profile})"])
            results = ComponentLibraryService.search_exida_components(
                query=query, component_type=comp_type, profile=self.project_profile
            )
            for item in results:
                row = self.lib_table.rowCount()
                self.lib_table.insertRow(row)
                
                lbl_item = QTableWidgetItem(item["display_label"])
                lbl_item.setData(Qt.ItemDataRole.UserRole, item["id"])
                lbl_item.setData(Qt.ItemDataRole.UserRole + 1, "exida")
                self.lib_table.setItem(row, 0, lbl_item)
                
                sub_txt = item["component_type"]
                if item.get("component_subtype"):
                    sub_txt += f" ({item['component_subtype']})"
                self.lib_table.setItem(row, 1, QTableWidgetItem(sub_txt))
                
                fr_txt = item.get("failure_rate_id") or ""
                if item.get("item_no"):
                    fr_txt += f" [{item['item_no']}]"
                self.lib_table.setItem(row, 2, QTableWidgetItem(fr_txt))
                
                fit_val = item.get("fit")
                fit_str = f"{fit_val:.4f}" if fit_val is not None else "NULL"
                fit_item = QTableWidgetItem(fit_str)
                if fit_val is None:
                    fit_item.setForeground(QColor("#dc3545"))
                self.lib_table.setItem(row, 3, fit_item)
        elif self.legacy_radio.isChecked():
            self.lib_table.setColumnCount(4)
            self.lib_table.setHorizontalHeaderLabels(["Display Name", "Material", "Shortcut", "Legacy FIT"])
            results = ComponentLibraryService.search_legacy_components(query=query)
            for item in results:
                row = self.lib_table.rowCount()
                self.lib_table.insertRow(row)
                
                lbl_item = QTableWidgetItem(item["display_name"])
                lbl_item.setData(Qt.ItemDataRole.UserRole, item["id"])
                lbl_item.setData(Qt.ItemDataRole.UserRole + 1, "legacy")
                self.lib_table.setItem(row, 0, lbl_item)
                
                self.lib_table.setItem(row, 1, QTableWidgetItem(item.get("material") or ""))
                self.lib_table.setItem(row, 2, QTableWidgetItem(item.get("shortcut") or ""))
                
                fit_val = item.get("fits")
                fit_str = f"{fit_val:.4f}" if fit_val is not None else "0.0000"
                self.lib_table.setItem(row, 3, QTableWidgetItem(fit_str))
        else:
            self.lib_table.setColumnCount(4)
            self.lib_table.setHorizontalHeaderLabels(["Display Label", "Component Type", "Failure Modes", "Failure Rate (FIT)"])
            results = ComponentLibraryService.search_custom_components(query=query, component_type=comp_type)
            for item in results:
                row = self.lib_table.rowCount()
                self.lib_table.insertRow(row)
                
                lbl_item = QTableWidgetItem(item["display_label"])
                lbl_item.setData(Qt.ItemDataRole.UserRole, item["id"])
                lbl_item.setData(Qt.ItemDataRole.UserRole + 1, "custom")
                self.lib_table.setItem(row, 0, lbl_item)
                
                self.lib_table.setItem(row, 1, QTableWidgetItem(item.get("component_type") or ""))
                fm_count = len(item.get("failure_modes", []))
                self.lib_table.setItem(row, 2, QTableWidgetItem(f"{fm_count} modes"))
                
                fit_val = item.get("fits", 0.0)
                self.lib_table.setItem(row, 3, QTableWidgetItem(f"{fit_val:.4f}"))
                
        # Re-apply header resize modes & restore widths
        header = self.lib_table.horizontalHeader()
        header.setMinimumSectionSize(75)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        
        if len(saved_widths) == 4 and saved_widths[0] > 0:
            self.lib_table.setColumnWidth(0, saved_widths[0])
            self.lib_table.setColumnWidth(2, saved_widths[2])
            self.lib_table.setColumnWidth(3, saved_widths[3])
        else:
            self.lib_table.setColumnWidth(0, 200)
            self.lib_table.setColumnWidth(2, 125)
            self.lib_table.setColumnWidth(3, 85)

        if self.lib_table.rowCount() > 0:
            self.lib_table.selectRow(0)
        else:
            self.selected_snapshot = None
            self.selected_template = None
            self._clear_configuration_panel()

    def _clear_configuration_panel(self):
        self.cfg_label_input.clear()
        self.cfg_value_input.clear()
        self.cfg_type_input.clear()
        self.cfg_fit_input.clear()
        self.cfg_fm_table.setRowCount(0)
        self.cfg_fm_total_lbl.setText("Total: 0.0%")
        self.cfg_fm_total_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")

    def _on_lib_table_selection_changed(self):
        selected_rows = self.lib_table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_snapshot = None
            self.selected_template = None
            self._clear_configuration_panel()
            self._update_selection_summary()
            return
            
        row = selected_rows[0].row()
        item0 = self.lib_table.item(row, 0)
        if not item0:
            return
            
        c_id = item0.data(Qt.ItemDataRole.UserRole)
        source_type = item0.data(Qt.ItemDataRole.UserRole + 1)
        
        if source_type == "exida":
            snapshot = ComponentLibraryService.get_exida_component_snapshot(c_id, self.project_profile)
        elif source_type == "legacy":
            snapshot = ComponentLibraryService.get_legacy_component_snapshot(c_id)
        else:
            snapshot = ComponentLibraryService.get_custom_component_snapshot(c_id)
            
        if not snapshot:
            return
            
        self.selected_snapshot = snapshot
        disp_label = snapshot.get("displayed_label") or snapshot.get("display_name")
        shortcut = snapshot.get("shortcut") or snapshot.get("failure_rate_id") or ""
        mat = snapshot.get("component_type") or snapshot.get("material") or disp_label
        fit_val = snapshot.get("failure_rate") if "failure_rate" in snapshot else snapshot.get("fits", 0.0)
        
        self.selected_template = ComponentDB(
            id=snapshot.get("library_component_id") or str(c_id),
            display_name=disp_label,
            shortcut=shortcut,
            material=mat,
            fits=fit_val,
            database=source_type,
            failure_modes=dict(snapshot.get("failure_modes", {})),
            library_component_id=snapshot.get("library_component_id"),
            failure_rate_id=snapshot.get("failure_rate_id"),
            item_no=snapshot.get("item_no"),
            component_subtype=snapshot.get("component_subtype"),
            component_use_category=snapshot.get("component_use_category"),
            selected_profile=self.project_profile,
            source_type=source_type,
            snapshot=snapshot
        )
        
        # Populate configuration panel
        self.cfg_label_input.setText(shortcut or disp_label)
        self.cfg_value_input.setText(disp_label)
        sub_type = snapshot.get("component_subtype")
        self.cfg_type_input.setText(f"{mat} ({sub_type})" if sub_type else mat)
        self.cfg_fit_input.setText(f"{fit_val:.4f}" if fit_val is not None else "0.0000")
        
        # Load failure modes (read-only)
        self._load_failure_modes(snapshot.get("failure_modes", {}))
        self._update_selection_summary()

    def _load_failure_modes(self, failure_modes: Dict[str, float]):
        self.cfg_fm_table.setRowCount(0)
        total_pct = 0.0
        for fm_name, fm_pct in failure_modes.items():
            r = self.cfg_fm_table.rowCount()
            self.cfg_fm_table.insertRow(r)
            
            it_name = QTableWidgetItem(fm_name)
            it_name.setFlags(it_name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.cfg_fm_table.setItem(r, 0, it_name)
            
            it_pct = QTableWidgetItem(f"{fm_pct:.1f}%")
            it_pct.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_pct.setFlags(it_pct.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.cfg_fm_table.setItem(r, 1, it_pct)
            
            is_dang = "short" in fm_name.lower() or "open" in fm_name.lower() or len(failure_modes) == 1
            classif_str = "Dangerous" if is_dang else "Not Evaluated"
            it_class = QTableWidgetItem(classif_str)
            it_class.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_class.setFlags(it_class.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.cfg_fm_table.setItem(r, 2, it_class)
            
            total_pct += fm_pct
            
        self.cfg_fm_total_lbl.setText(f"Total: {total_pct:.1f}%")
        if abs(total_pct - 100.0) < 0.1:
            self.cfg_fm_total_lbl.setStyleSheet("color: #198754; font-weight: bold;")
        else:
            self.cfg_fm_total_lbl.setStyleSheet("color: #dc3545; font-weight: bold;")

    def _on_in_dialog_import_bom_txt(self):
        """Allows importing BOM TXT directly from inside the mapping workspace."""
        existing_designators = [b.designator for b in self.unit.bom_components]
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select BOM TXT File", "", "BOM Text Files (*.txt)"
        )
        if not filepath:
            return
            
        dialog = BOMImportDialog(existing_designators, filepath=filepath, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            imported = dialog.imported_components
            duplicates = []
            new_imports = []
            for comp in imported:
                if any(b.designator.upper() == comp.designator.upper() for b in self.unit.bom_components):
                    duplicates.append(comp.designator)
                else:
                    new_imports.append(comp)
            
            if duplicates:
                QMessageBox.warning(
                    self, "Duplicate Designators Ignored",
                    f"The following {len(duplicates)} designators are already present in the BOM and were skipped:\n"
                    f"{', '.join(duplicates)}"
                )
                
            if not new_imports:
                QMessageBox.information(
                    self, "No New Components",
                    "No new BOM components were added (all selected designators were duplicates)."
                )
                return
                
            self.unit.bom_components.extend(new_imports)
            self.bom_count_lbl.setText(f"{len(self.unit.bom_components)} positions")
            self._populate_bom_table()
            self._update_selection_summary()
            
            QMessageBox.information(
                self, "BOM Imported",
                f"Successfully added {len(new_imports)} BOM positions to '{self.unit.name}'.\n"
                "You can now select positions and map them to component types."
            )

    def _populate_bom_table(self):
        self.bom_table.setRowCount(0)
        self.bom_checkboxes.clear()
        
        bom_list = getattr(self.unit, "bom_components", []) or []
        self.bom_count_lbl.setText(f"{len(bom_list)} positions")
        
        if not bom_list:
            self.bom_table.setRowCount(1)
            item = QTableWidgetItem("No BOM components loaded. Click '📥 Import BOM TXT' above to load a BOM file.")
            item.setForeground(QColor("#6c757d"))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bom_table.setItem(0, 0, item)
            self.bom_table.setSpan(0, 0, 1, 9)
            return
            
        for row, bom in enumerate(bom_list):
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
        for bom in getattr(self.unit, "bom_components", []) or []:
            des_upper = bom.designator.upper()
            cb = self.bom_checkboxes.get(des_upper)
            if cb and cb.isChecked():
                selected.append(bom.designator)
        return selected

    def _update_selection_summary(self):
        if self.selected_template:
            fits_str = f"{self.selected_template.fits:.4f} FIT" if self.selected_template.fits is not None else "0.0000 FIT"
            self.summary_target_lbl.setText(
                f"<b>Selected Component:</b> <span style='color:#0d6efd;'>{self.selected_template.display_name}</span> "
                f"({fits_str})"
            )
        else:
            self.summary_target_lbl.setText("<b>Selected Component:</b> <span style='color:#dc3545;'>None selected</span>")
            
        selected_positions = self._get_selected_designators()
        count = len(selected_positions)
        ranges_str = format_position_ranges(selected_positions)
        
        not_fitted_count = 0
        for pos in selected_positions:
            bom = next((b for b in getattr(self.unit, "bom_components", []) or [] if b.designator.upper() == pos.upper()), None)
            if bom and (not bom.is_fitted or any(kw in (bom.notes or "").lower() for kw in ["nicht bestueckt", "nicht bestückt", "not fitted", "dnp"])):
                not_fitted_count += 1
                
        warn_text = f" &nbsp;⚠️ <span style='color:#856404;'>({not_fitted_count} Not Fitted)</span>" if not_fitted_count > 0 else ""
        
        self.summary_pos_lbl.setText(
            f"<b>Selected Positions:</b> <b>{ranges_str}</b> &nbsp;|&nbsp; <b>Total Selected:</b> <b>{count}</b>{warn_text}"
        )

    def _apply_bom_filters(self):
        search_txt = self.search_input.text().strip().lower()
        pfx_filter = self.prefix_combo.currentText()
        status_filter = self.status_filter_combo.currentText()
        
        bom_list = getattr(self.unit, "bom_components", []) or []
        if not bom_list:
            return
            
        for row in range(self.bom_table.rowCount()):
            pos_item = self.bom_table.item(row, 1)
            if not pos_item:
                continue
            bom: BOMComponent = pos_item.data(Qt.ItemDataRole.UserRole)
            if not bom:
                continue
            des_upper = bom.designator.upper()
            
            combined = f"{bom.designator} {bom.part_number or ''} {bom.internal_part_number or ''} {bom.benennung or ''} {bom.value or ''} {bom.description or ''}".lower()
            match_search = not search_txt or search_txt in combined
            
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
        available = [b.designator for b in getattr(self.unit, "bom_components", []) or []]
        if not available:
            QMessageBox.information(self, "No BOM", "Please import a BOM TXT file first.")
            return
            
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
        if not self.selected_template:
            QMessageBox.warning(self, "Component Required", "Please select a Component from the library on the left before applying selection.")
            return
            
        selected_positions = self._get_selected_designators()
        if not selected_positions:
            QMessageBox.warning(self, "Positions Required", "Please select one or more BOM positions on the right using checkboxes.")
            return
            
        # Create a copy of template with user-configured label/shortcut if specified
        target_template = self.selected_template.model_copy()
        custom_lbl = self.cfg_label_input.text().strip()
        if custom_lbl:
            target_template.shortcut = custom_lbl
            
        for pos in selected_positions:
            self.staged_mappings[pos.upper()] = target_template
            
        for row in range(self.bom_table.rowCount()):
            pos_item = self.bom_table.item(row, 1)
            if pos_item:
                self._update_bom_row_mapping_display(row, pos_item.text().strip().upper())
                
        self._clear_selection()
        self._update_selection_summary()
        
        QMessageBox.information(
            self, "Selection Applied",
            f"Assigned {len(selected_positions)} BOM positions ({format_position_ranges(selected_positions)}) "
            f"to '{target_template.display_name}'.\n\n"
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
                
        for row in range(self.bom_table.rowCount()):
            pos_item = self.bom_table.item(row, 1)
            if pos_item:
                self._update_bom_row_mapping_display(row, pos_item.text().strip().upper())
                
        self._clear_selection()
        self._update_selection_summary()
        QMessageBox.information(self, "Unmapped", f"Unmapped {unmapped_count} BOM positions.")

    def _on_save_clicked(self):
        if not self.staged_mappings:
            QMessageBox.warning(self, "No Mappings", "No BOM positions are currently mapped. Please assign at least one position before saving.")
            return
            
        grouped: Dict[str, Tuple[ComponentDB, List[str]]] = {}
        for des, tmpl in self.staged_mappings.items():
            if tmpl.id not in grouped:
                grouped[tmpl.id] = (tmpl, [])
            grouped[tmpl.id][1].append(des)
            
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
            f"<h3>Confirm Component & BOM Mappings</h3>"
            f"<p>The following <b>{total_comps} component instances</b> will be created/updated in <b>{self.unit.name}</b>:</p>"
            f"{'<br><br>'.join(summary_lines)}<br><br>"
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
        Creates single Component instances with attached failure modes, sets Not Fitted status,
        and replaces temporary templates cleanly.
        """
        bom_by_des = {b.designator.upper(): b for b in getattr(self.unit, "bom_components", []) or []}
        
        new_components_list: List[Component] = []
        existing_comp_by_des: Dict[str, Component] = {}
        for comp in getattr(self.unit, "components", []) or []:
            if comp.position in ("Mapping Template", "Template") or getattr(comp, "is_template", False):
                continue
            if comp.position.upper() not in bom_by_des:
                new_components_list.append(comp)
            else:
                existing_comp_by_des[comp.position.upper()] = comp
                
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
                existing_comp.name = template.display_name
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
                existing_comp.item_no = template.item_no or existing_comp.item_no
                existing_comp.component_subtype = template.component_subtype or existing_comp.component_subtype
                existing_comp.component_use_category = template.component_use_category or existing_comp.component_use_category
                existing_comp.selected_profile = template.selected_profile or self.project_profile
                existing_comp.source_type = template.database or template.source_type or "exida"
                existing_comp.snapshot = template.snapshot
                new_components_list.append(existing_comp)
            else:
                comp_id = f"comp_{uuid.uuid4().hex[:8]}"
                new_comp = Component(
                    id=comp_id,
                    position=bom.designator,
                    name=template.display_name,
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
        """Programmatic entry point for automated tests."""
        if not self.staged_mappings and self.mappings:
            db_map = {t.id: t for t in (self.available_templates + getattr(self, "db_templates", []))}
            bom_by_id = {b.id: b for b in getattr(self.unit, "bom_components", []) or []}
            for m in self.mappings:
                if m.is_confirmed and m.bom_component_id in bom_by_id and m.component_db_id in db_map:
                    bom = bom_by_id[m.bom_component_id]
                    self.staged_mappings[bom.designator.upper()] = db_map[m.component_db_id]
                    
        self._commit_mappings()
