"""
Component Picker Dialog providing Exida and Legacy component selection tabs,
multi-criteria search, profile-specific failure rates, and safety warnings.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QLineEdit, QComboBox,
    QHeaderView, QMessageBox, QGroupBox, QFrame, QSplitter,
    QWidget, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from typing import Optional, Dict, Any, List

from fmeda_tool.services.component_library_service import ComponentLibraryService


class ComponentPickerDialog(QDialog):
    """
    Component Picker Dialog with dual Exida and Legacy tabs.
    Returns a normalized project-level component snapshot.
    """
    
    component_selected = pyqtSignal(dict)  # Emits snapshot dictionary
    
    def __init__(self, project_profile: str = "Profile 1", parent=None):
        super().__init__(parent)
        self.project_profile = project_profile or "Profile 1"
        self.selected_snapshot: Optional[Dict[str, Any]] = None
        
        self.setWindowTitle(f"Component Library Picker - ({self.project_profile})")
        self.setMinimumWidth(1100)
        self.setMinimumHeight(700)
        
        self._setup_ui()
        self._load_exida_data()
        self._load_legacy_data()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)
        
        # Header Info
        header_layout = QHBoxLayout()
        title_lbl = QLabel("Component Library")
        title_lbl.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title_lbl)
        
        header_layout.addStretch()
        
        prof_badge = QLabel(f"Active Project Profile: <b>{self.project_profile}</b>")
        prof_badge.setStyleSheet("background-color: #e9ecef; border: 1px solid #ced4da; padding: 4px 10px; border-radius: 4px;")
        header_layout.addWidget(prof_badge)
        
        main_layout.addLayout(header_layout)
        
        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { font-weight: bold; padding: 8px 20px; }
            QTabBar::tab:selected { background-color: #0d6efd; color: white; }
        """)
        
        # Tab A: Exida Components (Default)
        self.exida_tab = QWidget()
        self._setup_exida_tab(self.exida_tab)
        self.tabs.addTab(self.exida_tab, "Exida Components (Recommended)")
        
        # Tab B: Legacy Components
        self.legacy_tab = QWidget()
        self._setup_legacy_tab(self.legacy_tab)
        self.tabs.addTab(self.legacy_tab, "Legacy Components (Unmapped)")
        
        main_layout.addWidget(self.tabs, stretch=1)
        
        # Bottom Actions Bar
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)
        
        self.select_btn = QPushButton("Select Component")
        self.select_btn.setMinimumWidth(140)
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                font-weight: bold;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #0b5ed7; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.select_btn.setEnabled(False)
        self.select_btn.clicked.connect(self._on_select_clicked)
        bottom_layout.addWidget(self.select_btn)
        
        main_layout.addLayout(bottom_layout)
        
    def _setup_exida_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Search and Filters Box
        filter_box = QGroupBox("Search & Filters")
        filter_layout = QVBoxLayout(filter_box)
        filter_layout.setSpacing(8)
        
        # Search Bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.exida_search = QLineEdit()
        self.exida_search.setPlaceholderText("Search display name, aliases, type, subtype, category, FR ID (e.g. FR-000001), item no...")
        self.exida_search.textChanged.connect(self._on_exida_filter_changed)
        search_layout.addWidget(self.exida_search)
        filter_layout.addLayout(search_layout)
        
        # Filter Dropdowns
        combos_layout = QHBoxLayout()
        
        # Type filter
        combos_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("All")
        self.type_combo.currentTextChanged.connect(self._on_exida_filter_changed)
        combos_layout.addWidget(self.type_combo)
        
        # Subtype filter
        combos_layout.addWidget(QLabel("Subtype:"))
        self.subtype_combo = QComboBox()
        self.subtype_combo.addItem("All")
        self.subtype_combo.currentTextChanged.connect(self._on_exida_filter_changed)
        combos_layout.addWidget(self.subtype_combo)
        
        # Category filter
        combos_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItem("All")
        self.category_combo.currentTextChanged.connect(self._on_exida_filter_changed)
        combos_layout.addWidget(self.category_combo)
        
        # Mapping status filter
        combos_layout.addWidget(QLabel("Mapping:"))
        self.map_status_combo = QComboBox()
        self.map_status_combo.addItems(["All", "mapped_high_confidence", "unmapped"])
        self.map_status_combo.currentTextChanged.connect(self._on_exida_filter_changed)
        combos_layout.addWidget(self.map_status_combo)
        
        # Reset filters button
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset_exida_filters)
        combos_layout.addWidget(reset_btn)
        
        filter_layout.addLayout(combos_layout)
        layout.addWidget(filter_box)
        
        # Splitter: Table on left, Preview on right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Results Table
        self.exida_table = QTableWidget()
        self.exida_table.setColumnCount(8)
        self.exida_table.setHorizontalHeaderLabels([
            "Display Label", "Component Type", "Subtype", "Use Category",
            "Failure Rate ID", "Item No", f"FIT ({self.project_profile})", "Mapping"
        ])
        self.exida_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.exida_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.exida_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.exida_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.exida_table.itemSelectionChanged.connect(self._on_exida_selection_changed)
        self.exida_table.doubleClicked.connect(self._on_select_clicked)
        splitter.addWidget(self.exida_table)
        
        # Detail Preview Box
        self.exida_preview_box = QGroupBox("Selected Component Details")
        preview_layout = QVBoxLayout(self.exida_preview_box)
        
        self.exida_detail_lbl = QLabel("Select a component to view details.")
        self.exida_detail_lbl.setWordWrap(True)
        preview_layout.addWidget(self.exida_detail_lbl)
        
        preview_layout.addWidget(QLabel("<b>Failure Modes & Percentages:</b>"))
        self.exida_fm_table = QTableWidget()
        self.exida_fm_table.setColumnCount(2)
        self.exida_fm_table.setHorizontalHeaderLabels(["Failure Mode", "Percentage %"])
        self.exida_fm_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.exida_fm_table.setAlternatingRowColors(True)
        preview_layout.addWidget(self.exida_fm_table)
        
        splitter.addWidget(self.exida_preview_box)
        splitter.setSizes([650, 400])
        
        layout.addWidget(splitter, stretch=1)
        
    def _setup_legacy_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Non-blocking Legacy Warning Banner
        warning_frame = QFrame()
        warning_frame.setStyleSheet("background-color: #fff3cd; border: 1px solid #ffeeba; border-radius: 4px; padding: 8px;")
        warn_layout = QHBoxLayout(warning_frame)
        warn_lbl = QLabel("⚠️ <b>Legacy component model:</b> No approved normalized Exida mapping is available for these records.")
        warn_lbl.setStyleSheet("color: #856404; font-size: 12px;")
        warn_layout.addWidget(warn_lbl)
        layout.addWidget(warning_frame)
        
        # Search Bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search Legacy:"))
        self.legacy_search = QLineEdit()
        self.legacy_search.setPlaceholderText("Search legacy name, shortcut, material/description...")
        self.legacy_search.textChanged.connect(self._on_legacy_search_changed)
        search_layout.addWidget(self.legacy_search)
        layout.addLayout(search_layout)
        
        # Splitter: Table on left, Preview on right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.legacy_table = QTableWidget()
        self.legacy_table.setColumnCount(6)
        self.legacy_table.setHorizontalHeaderLabels([
            "Legacy Display Name", "Shortcut", "Material / Description", "Legacy FIT", "Status", "Source"
        ])
        self.legacy_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.legacy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.legacy_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.legacy_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.legacy_table.itemSelectionChanged.connect(self._on_legacy_selection_changed)
        self.legacy_table.doubleClicked.connect(self._on_select_clicked)
        splitter.addWidget(self.legacy_table)
        
        # Detail Preview Box
        self.legacy_preview_box = QGroupBox("Legacy Component Details")
        preview_layout = QVBoxLayout(self.legacy_preview_box)
        
        self.legacy_detail_lbl = QLabel("Select a legacy component to view details.")
        self.legacy_detail_lbl.setWordWrap(True)
        preview_layout.addWidget(self.legacy_detail_lbl)
        
        preview_layout.addWidget(QLabel("<b>Legacy Failure Modes:</b>"))
        self.legacy_fm_table = QTableWidget()
        self.legacy_fm_table.setColumnCount(2)
        self.legacy_fm_table.setHorizontalHeaderLabels(["Failure Mode", "Percentage %"])
        self.legacy_fm_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.legacy_fm_table.setAlternatingRowColors(True)
        preview_layout.addWidget(self.legacy_fm_table)
        
        splitter.addWidget(self.legacy_preview_box)
        splitter.setSizes([650, 400])
        
        layout.addWidget(splitter, stretch=1)
        
    def _populate_filter_dropdowns(self):
        filters = ComponentLibraryService.get_distinct_filter_values()
        
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("All")
        self.type_combo.addItems(filters["component_types"])
        self.type_combo.blockSignals(False)
        
        self.subtype_combo.blockSignals(True)
        self.subtype_combo.clear()
        self.subtype_combo.addItem("All")
        self.subtype_combo.addItems(filters["component_subtypes"])
        self.subtype_combo.blockSignals(False)
        
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("All")
        self.category_combo.addItems(filters["component_use_categories"])
        self.category_combo.blockSignals(False)
        
    def _load_exida_data(self):
        self._populate_filter_dropdowns()
        self._on_exida_filter_changed()
        
    def _load_legacy_data(self):
        self._on_legacy_search_changed()
        
    def _reset_exida_filters(self):
        self.exida_search.clear()
        self.type_combo.setCurrentIndex(0)
        self.subtype_combo.setCurrentIndex(0)
        self.category_combo.setCurrentIndex(0)
        self.map_status_combo.setCurrentIndex(0)
        self._on_exida_filter_changed()
        
    def _on_exida_filter_changed(self):
        query = self.exida_search.text().strip()
        comp_type = self.type_combo.currentText()
        comp_subtype = self.subtype_combo.currentText()
        comp_cat = self.category_combo.currentText()
        map_stat = self.map_status_combo.currentText()
        
        results = ComponentLibraryService.search_exida_components(
            query=query,
            component_type=comp_type if comp_type != "All" else None,
            component_subtype=comp_subtype if comp_subtype != "All" else None,
            component_use_category=comp_cat if comp_cat != "All" else None,
            mapping_status=map_stat if map_stat != "All" else None,
            profile=self.project_profile
        )
        
        self.exida_table.setRowCount(0)
        for item in results:
            row = self.exida_table.rowCount()
            self.exida_table.insertRow(row)
            
            lbl_item = QTableWidgetItem(item["display_label"])
            lbl_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            self.exida_table.setItem(row, 0, lbl_item)
            
            self.exida_table.setItem(row, 1, QTableWidgetItem(item["component_type"] or ""))
            self.exida_table.setItem(row, 2, QTableWidgetItem(item["component_subtype"] or ""))
            self.exida_table.setItem(row, 3, QTableWidgetItem(item["component_use_category"] or ""))
            self.exida_table.setItem(row, 4, QTableWidgetItem(item["failure_rate_id"] or ""))
            self.exida_table.setItem(row, 5, QTableWidgetItem(item["item_no"] or ""))
            
            fit_val = item["fit"]
            fit_str = f"{fit_val:.4f}" if fit_val is not None else "NULL (No Data)"
            fit_item = QTableWidgetItem(fit_str)
            if fit_val is None:
                fit_item.setForeground(QColor("#dc3545"))
            self.exida_table.setItem(row, 6, fit_item)
            
            self.exida_table.setItem(row, 7, QTableWidgetItem(item["mapping_status"] or "unmapped"))
            
        if self.exida_table.rowCount() > 0:
            self.exida_table.selectRow(0)
        else:
            self.exida_detail_lbl.setText("No Exida components matched the search filters.")
            self.exida_fm_table.setRowCount(0)
            self.select_btn.setEnabled(False)
            
    def _on_exida_selection_changed(self):
        selected_rows = self.exida_table.selectionModel().selectedRows()
        if not selected_rows:
            self.select_btn.setEnabled(False)
            return
            
        row = selected_rows[0].row()
        item0 = self.exida_table.item(row, 0)
        if not item0:
            return
            
        comp_id = item0.data(Qt.ItemDataRole.UserRole)
        snapshot = ComponentLibraryService.get_exida_component_snapshot(comp_id, self.project_profile)
        if not snapshot:
            return
            
        self.selected_snapshot = snapshot
        self.select_btn.setEnabled(True)
        
        # Populate details
        fit_val = snapshot["failure_rate"]
        fit_display = f"<b>{fit_val:.4f} FIT</b>" if fit_val is not None else "<b style='color:#dc3545;'>NULL (Undefined for this profile)</b>"
        
        detail_html = f"""
            <b>Display Label:</b> {snapshot['displayed_label']}<br>
            <b>Component Type:</b> {snapshot['component_type']}<br>
            <b>Subtype:</b> {snapshot.get('component_subtype') or 'N/A'}<br>
            <b>Use Category:</b> {snapshot.get('component_use_category') or 'N/A'}<br>
            <b>Failure Rate ID:</b> {snapshot['failure_rate_id']}&nbsp;&nbsp;|&nbsp;&nbsp;<b>Item No:</b> {snapshot.get('item_no') or 'N/A'}<br>
            <b>Selected Profile:</b> {snapshot['selected_profile']}&nbsp;&nbsp;|&nbsp;&nbsp;<b>Base FIT:</b> {fit_display}<br>
            <b>Source:</b> {snapshot.get('source_name') or 'exida Reliability Handbook'}
        """
        self.exida_detail_lbl.setText(detail_html)
        
        # Populate Failure Modes
        fms = snapshot.get("failure_modes", {})
        self.exida_fm_table.setRowCount(0)
        for fm_name, fm_pct in fms.items():
            r = self.exida_fm_table.rowCount()
            self.exida_fm_table.insertRow(r)
            self.exida_fm_table.setItem(r, 0, QTableWidgetItem(fm_name))
            self.exida_fm_table.setItem(r, 1, QTableWidgetItem(f"{fm_pct:.1f}%"))
            
    def _on_legacy_search_changed(self):
        query = self.legacy_search.text().strip()
        results = ComponentLibraryService.search_legacy_components(query=query)
        
        self.legacy_table.setRowCount(0)
        for item in results:
            row = self.legacy_table.rowCount()
            self.legacy_table.insertRow(row)
            
            lbl_item = QTableWidgetItem(item["display_name"])
            lbl_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            self.legacy_table.setItem(row, 0, lbl_item)
            
            self.legacy_table.setItem(row, 1, QTableWidgetItem(item["shortcut"] or ""))
            self.legacy_table.setItem(row, 2, QTableWidgetItem(item["material"] or ""))
            
            fit_val = item["fits"]
            fit_str = f"{fit_val:.4f}" if fit_val is not None else "0.0000"
            self.legacy_table.setItem(row, 3, QTableWidgetItem(fit_str))
            
            self.legacy_table.setItem(row, 4, QTableWidgetItem(item["status"] or "active"))
            
            badge_item = QTableWidgetItem("LEGACY ⚠️")
            badge_item.setForeground(QColor("#d39e00"))
            self.legacy_table.setItem(row, 5, badge_item)
            
        if self.legacy_table.rowCount() > 0:
            self.legacy_table.selectRow(0)
        else:
            self.legacy_detail_lbl.setText("No legacy components matched the search.")
            self.legacy_fm_table.setRowCount(0)
            
    def _on_legacy_selection_changed(self):
        selected_rows = self.legacy_table.selectionModel().selectedRows()
        if not selected_rows:
            return
            
        row = selected_rows[0].row()
        item0 = self.legacy_table.item(row, 0)
        if not item0:
            return
            
        leg_id = item0.data(Qt.ItemDataRole.UserRole)
        snapshot = ComponentLibraryService.get_legacy_component_snapshot(leg_id)
        if not snapshot:
            return
            
        self.selected_snapshot = snapshot
        self.select_btn.setEnabled(True)
        
        # Populate details
        fit_val = snapshot["failure_rate"]
        fit_display = f"{fit_val:.4f} FIT" if fit_val is not None else "N/A"
        
        detail_html = f"""
            <b>Legacy Name:</b> {snapshot['display_name']}<br>
            <b>Shortcut:</b> {snapshot.get('shortcut') or 'N/A'}<br>
            <b>Material:</b> {snapshot.get('material') or 'N/A'}<br>
            <b>Database:</b> {snapshot.get('database') or 'Legacy FMEDA'}<br>
            <b>Base FIT:</b> {fit_display}<br>
            <span style='color: #856404;'><b>Notice:</b> Legacy component without approved normalized Exida mapping.</span>
        """
        self.legacy_detail_lbl.setText(detail_html)
        
        # Populate Failure Modes
        fms = snapshot.get("failure_modes", {})
        self.legacy_fm_table.setRowCount(0)
        for fm_name, fm_pct in fms.items():
            r = self.legacy_fm_table.rowCount()
            self.legacy_fm_table.insertRow(r)
            self.legacy_fm_table.setItem(r, 0, QTableWidgetItem(fm_name))
            self.legacy_fm_table.setItem(r, 1, QTableWidgetItem(f"{fm_pct:.1f}%"))
            
    def _on_select_clicked(self):
        # Determine active tab
        active_idx = self.tabs.currentIndex()
        if active_idx == 0:
            self._on_exida_selection_changed()
        else:
            self._on_legacy_selection_changed()
            
        if not self.selected_snapshot:
            QMessageBox.warning(self, "No Selection", "Please select a component from the list.")
            return
            
        # Check null FIT for Exida components
        if self.selected_snapshot.get("source_type") == "exida":
            fit_val = self.selected_snapshot.get("failure_rate")
            if fit_val is None:
                QMessageBox.warning(
                    self,
                    "Undefined Failure Rate (Null FIT)",
                    f"The selected component '{self.selected_snapshot['displayed_label']}' has no defined failure rate (FIT is NULL) in {self.project_profile}.\n\n"
                    "The system will not convert this missing value to zero. Please select a different component or profile, or edit the failure rate manually."
                )
                
        self.component_selected.emit(self.selected_snapshot)
        self.accept()
        
    def get_selected_snapshot(self) -> Optional[Dict[str, Any]]:
        return self.selected_snapshot
