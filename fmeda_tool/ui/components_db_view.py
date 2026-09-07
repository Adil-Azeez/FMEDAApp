"""
Component Library and Display-Name Management View.
Provides comprehensive Exida, Legacy, Unassigned Display Names (batch assignment),
Audit Change Log, and Database Administration tabs.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QLabel, QLineEdit,
    QComboBox, QMessageBox, QFrame, QGroupBox, QDialog, QFormLayout,
    QTextEdit, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from typing import List, Dict, Any, Optional, Tuple

from fmeda_tool.services.component_library_service import ComponentLibraryService
from fmeda_tool.db.database import DatabaseService, get_database_path


class EditDisplayNameDialog(QDialog):
    """Dialog for assigning, editing, or removing an Exida component display name."""
    
    def __init__(self, comp: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.comp = comp
        self.is_new = not bool(comp.get("display_name"))
        
        title = "Assign Display Name" if self.is_new else f"Edit Display Name ({comp.get('display_name')})"
        self.setWindowTitle(title)
        self.setMinimumWidth(550)
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        form = QFormLayout()
        form.setSpacing(8)
        
        # Read-only attributes
        type_lbl = QLineEdit(self.comp.get("component_type") or "")
        type_lbl.setReadOnly(True)
        type_lbl.setStyleSheet("background-color: #e9ecef;")
        form.addRow("Component Type:", type_lbl)
        
        subtype_lbl = QLineEdit(self.comp.get("component_subtype") or "N/A")
        subtype_lbl.setReadOnly(True)
        subtype_lbl.setStyleSheet("background-color: #e9ecef;")
        form.addRow("Component Subtype:", subtype_lbl)
        
        cat_lbl = QLineEdit(self.comp.get("component_use_category") or "N/A")
        cat_lbl.setReadOnly(True)
        cat_lbl.setStyleSheet("background-color: #e9ecef;")
        form.addRow("Use Category:", cat_lbl)
        
        fr_lbl = QLineEdit(self.comp.get("failure_rate_id") or "")
        fr_lbl.setReadOnly(True)
        fr_lbl.setStyleSheet("background-color: #e9ecef;")
        form.addRow("Failure Rate ID:", fr_lbl)
        
        item_no_lbl = QLineEdit(self.comp.get("item_no") or "N/A")
        item_no_lbl.setReadOnly(True)
        item_no_lbl.setStyleSheet("background-color: #e9ecef;")
        form.addRow("Item Number:", item_no_lbl)
        
        curr_name_lbl = QLineEdit(self.comp.get("display_name") or "(None - null)")
        curr_name_lbl.setReadOnly(True)
        curr_name_lbl.setStyleSheet("background-color: #e9ecef;")
        form.addRow("Current Display Name:", curr_name_lbl)
        
        # Editable attributes
        self.new_name_input = QLineEdit()
        self.new_name_input.setText(self.comp.get("display_name") or "")
        self.new_name_input.setPlaceholderText("Enter unique display name (e.g. CEL, RES_10K)")
        form.addRow("Display Name*:", self.new_name_input)
        
        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Optional reason for change (e.g. Standardized naming)")
        form.addRow("Change Reason:", self.reason_input)
        
        layout.addLayout(form)
        
        # Validation notes
        if self.is_new:
            note_text = "<i>Note: Display names must be unique and non-empty.</i>"
        else:
            note_text = (
                "<i>Note: Display names must be unique and non-empty. "
                "Changing an existing display name preserves the previous name as an alias. "
                "Selecting 'Remove Display Name' resets the display name to NULL and uses the component type as label.</i>"
            )
        note_lbl = QLabel(note_text)
        note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(note_lbl)
        
        # Buttons
        btns = QHBoxLayout()
        
        if not self.is_new:
            remove_btn = QPushButton("Remove Display Name")
            remove_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    font-weight: bold;
                    padding: 6px 14px;
                    border-radius: 4px;
                    border: none;
                }
                QPushButton:hover { background-color: #bb2d3b; }
            """)
            remove_btn.clicked.connect(self._on_remove)
            btns.addWidget(remove_btn)
            
        btns.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        
        save_btn = QPushButton("Assign Name" if self.is_new else "Save Display Name")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #198754;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover { background-color: #157347; }
        """)
        save_btn.clicked.connect(self._on_save)
        btns.addWidget(save_btn)
        
        layout.addLayout(btns)
        
    def _on_save(self):
        new_name = self.new_name_input.text().strip()
        reason = self.reason_input.text().strip()
        
        success, msg = ComponentLibraryService.assign_display_name(
            component_id=self.comp["id"],
            new_name=new_name,
            change_reason=reason,
            user="admin"
        )
        
        if not success:
            QMessageBox.warning(self, "Validation / Save Error", msg)
            return
            
        QMessageBox.information(self, "Success", msg)
        self.accept()
        
    def _on_remove(self):
        old_name = self.comp.get("display_name")
        fr_id = self.comp.get("failure_rate_id", "")
        comp_type = self.comp.get("component_type", "")
        
        reply = QMessageBox.question(
            self,
            "Confirm Remove Display Name",
            f"Are you sure you want to remove the display name '{old_name}' for component {fr_id} ({comp_type})?\n\n"
            "Its display name will be restored to NULL and the component will use its component type as the active label.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        reason = self.reason_input.text().strip() or "Removed display name (restored to NULL)"
        success, msg = ComponentLibraryService.remove_display_name(
            component_id=self.comp["id"],
            change_reason=reason,
            user="admin"
        )
        if not success:
            QMessageBox.warning(self, "Error Removing Display Name", msg)
            return
            
        QMessageBox.information(self, "Success", msg)
        self.accept()


class ComponentsDBView(QWidget):
    """Comprehensive Component Library and Display-Name Management View"""
    
    back_to_menu_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._load_exida_tab()
        self._load_legacy_tab()
        self._load_unassigned_tab()
        self._load_changelog_tab()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header bar
        header = QFrame()
        header.setStyleSheet("background-color: #f8f9fa; border-bottom: 2px solid #dee2e6;")
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        
        title_lbl = QLabel("Component Library & Display Name Management")
        title_lbl.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        
        back_btn = QPushButton("← Back to Menu")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5c636a; }
        """)
        back_btn.clicked.connect(self.back_to_menu_requested.emit)
        header_layout.addWidget(back_btn)
        main_layout.addWidget(header)
        
        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ced4da; }
            QTabBar::tab {
                padding: 8px 16px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border-bottom: 2px solid #0d6efd;
            }
        """)
        
        # 1. Exida Components Tab
        self.exida_tab = QWidget()
        self._setup_exida_ui(self.exida_tab)
        self.tabs.addTab(self.exida_tab, "Exida Components (Master Catalog)")
        
        # 2. Legacy Components Tab
        self.legacy_tab = QWidget()
        self._setup_legacy_ui(self.legacy_tab)
        self.tabs.addTab(self.legacy_tab, "Legacy Unmapped Components")
        
        # 3. Unassigned Display Names Tab (Batch Editor)
        self.unassigned_tab = QWidget()
        self._setup_unassigned_ui(self.unassigned_tab)
        self.tabs.addTab(self.unassigned_tab, "Unassigned Display Names (Batch Edit)")
        
        # 4. Audit Change Log Tab
        self.changelog_tab = QWidget()
        self._setup_changelog_ui(self.changelog_tab)
        self.tabs.addTab(self.changelog_tab, "Audit Change Log")
        
        # 5. Database Administration Tab
        self.admin_tab = QWidget()
        self._setup_admin_ui(self.admin_tab)
        self.tabs.addTab(self.admin_tab, "Database Administration")
        
        main_layout.addWidget(self.tabs)

    # ---------------- 1. EXIDA COMPONENTS TAB ----------------
    def _setup_exida_ui(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Filter Bar
        filter_box = QGroupBox("Filter Catalog")
        filter_layout = QHBoxLayout(filter_box)
        filter_layout.setSpacing(10)
        
        filter_layout.addWidget(QLabel("Search:"))
        self.exida_search_input = QLineEdit()
        self.exida_search_input.setPlaceholderText("Search display name, type, alias, FR-ID, item no...")
        self.exida_search_input.textChanged.connect(self._load_exida_tab)
        filter_layout.addWidget(self.exida_search_input, stretch=2)
        
        filter_layout.addWidget(QLabel("Type:"))
        self.exida_type_combo = QComboBox()
        self.exida_type_combo.currentIndexChanged.connect(self._load_exida_tab)
        filter_layout.addWidget(self.exida_type_combo, stretch=1)
        
        filter_layout.addWidget(QLabel("Subtype:"))
        self.exida_subtype_combo = QComboBox()
        self.exida_subtype_combo.currentIndexChanged.connect(self._load_exida_tab)
        filter_layout.addWidget(self.exida_subtype_combo, stretch=1)
        
        filter_layout.addWidget(QLabel("Category:"))
        self.exida_cat_combo = QComboBox()
        self.exida_cat_combo.currentIndexChanged.connect(self._load_exida_tab)
        filter_layout.addWidget(self.exida_cat_combo, stretch=1)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_exida_tab)
        filter_layout.addWidget(refresh_btn)
        
        layout.addWidget(filter_box)
        
        # Master Table
        self.exida_table = QTableWidget()
        self.exida_table.setColumnCount(9)
        self.exida_table.setHorizontalHeaderLabels([
            "Display Name", "Display Label (Active)", "Component Type", "Subtype",
            "Category", "Failure Rate ID", "Item No", "Status", "Actions"
        ])
        self.exida_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.exida_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.exida_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.exida_table.verticalHeader().setVisible(False)
        layout.addWidget(self.exida_table)
        
        # Status footer
        self.exida_count_lbl = QLabel("0 components")
        layout.addWidget(self.exida_count_lbl)
        
    def _load_exida_tab(self):
        # Refresh dropdowns
        filters = ComponentLibraryService.get_distinct_filter_values()
        
        curr_t = self.exida_type_combo.currentText()
        self.exida_type_combo.blockSignals(True)
        self.exida_type_combo.clear()
        self.exida_type_combo.addItem("All")
        self.exida_type_combo.addItems(filters["component_types"])
        self.exida_type_combo.setCurrentText(curr_t if curr_t in filters["component_types"] else "All")
        self.exida_type_combo.blockSignals(False)
        
        curr_st = self.exida_subtype_combo.currentText()
        self.exida_subtype_combo.blockSignals(True)
        self.exida_subtype_combo.clear()
        self.exida_subtype_combo.addItem("All")
        self.exida_subtype_combo.addItems(filters["component_subtypes"])
        self.exida_subtype_combo.setCurrentText(curr_st if curr_st in filters["component_subtypes"] else "All")
        self.exida_subtype_combo.blockSignals(False)
        
        curr_c = self.exida_cat_combo.currentText()
        self.exida_cat_combo.blockSignals(True)
        self.exida_cat_combo.clear()
        self.exida_cat_combo.addItem("All")
        self.exida_cat_combo.addItems(filters["component_use_categories"])
        self.exida_cat_combo.setCurrentText(curr_c if curr_c in filters["component_use_categories"] else "All")
        self.exida_cat_combo.blockSignals(False)
        
        query = self.exida_search_input.text().strip()
        comp_type = self.exida_type_combo.currentText()
        comp_subtype = self.exida_subtype_combo.currentText()
        comp_cat = self.exida_cat_combo.currentText()
        
        results = ComponentLibraryService.search_exida_components(
            query=query,
            component_type=comp_type if comp_type != "All" else None,
            component_subtype=comp_subtype if comp_subtype != "All" else None,
            component_use_category=comp_cat if comp_cat != "All" else None,
            include_retired=True
        )
        
        self.exida_table.setRowCount(0)
        for comp in results:
            row = self.exida_table.rowCount()
            self.exida_table.insertRow(row)
            
            # 0. Raw display name
            dname = comp.get("display_name")
            item_dname = QTableWidgetItem(dname if dname else "")
            if not dname:
                item_dname.setForeground(QColor("#6c757d"))
            self.exida_table.setItem(row, 0, item_dname)
            
            # 1. Effective Display Label (Active)
            lbl_item = QTableWidgetItem(comp["display_label"])
            lbl_item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            self.exida_table.setItem(row, 1, lbl_item)
            
            self.exida_table.setItem(row, 2, QTableWidgetItem(comp["component_type"]))
            self.exida_table.setItem(row, 3, QTableWidgetItem(comp["component_subtype"] or ""))
            self.exida_table.setItem(row, 4, QTableWidgetItem(comp["component_use_category"] or ""))
            self.exida_table.setItem(row, 5, QTableWidgetItem(comp["failure_rate_id"]))
            self.exida_table.setItem(row, 6, QTableWidgetItem(str(comp.get("item_no") or "")))
            
            stat_item = QTableWidgetItem(comp["status"])
            stat_item.setForeground(QColor("#198754" if comp["status"] == "active" else "#dc3545"))
            self.exida_table.setItem(row, 7, stat_item)
            
            # Action Button: "+ Assign Name" if display_name is NULL, "Edit Name" if populated
            action_btn = QPushButton("Edit Name" if dname else "+ Assign Name")
            if dname:
                action_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            else:
                action_btn.setStyleSheet("padding: 2px 8px; font-size: 11px; font-weight: bold; color: #0d6efd;")
            action_btn.clicked.connect(lambda _, c=comp: self._open_edit_name_dialog(c))
            self.exida_table.setCellWidget(row, 8, action_btn)
            
        self.exida_count_lbl.setText(f"Showing {len(results)} Exida components")
        
    def _open_edit_name_dialog(self, comp: Dict[str, Any]):
        dialog = EditDisplayNameDialog(comp, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_exida_tab()
            self._load_unassigned_tab()
            self._load_changelog_tab()

    # ---------------- 2. LEGACY COMPONENTS TAB ----------------
    def _setup_legacy_ui(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Banner warning
        warn_lbl = QLabel(
            "<b>Legacy Components Notice:</b> The components listed here are legacy unmapped models. "
            "They are maintained for backward project compatibility."
        )
        warn_lbl.setStyleSheet("background-color: #fff3cd; color: #664d03; padding: 8px 12px; border-radius: 4px; border: 1px solid #ffecb5;")
        layout.addWidget(warn_lbl)
        
        # Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search Legacy:"))
        self.legacy_search_input = QLineEdit()
        self.legacy_search_input.setPlaceholderText("Search name, shortcut, material...")
        self.legacy_search_input.textChanged.connect(self._load_legacy_tab)
        search_layout.addWidget(self.legacy_search_input)
        layout.addLayout(search_layout)
        
        # Legacy Table
        self.legacy_table = QTableWidget()
        self.legacy_table.setColumnCount(7)
        self.legacy_table.setHorizontalHeaderLabels([
            "Display Name", "Shortcut", "Material", "Legacy FIT", "Mapping Status", "Status", "Actions"
        ])
        self.legacy_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.legacy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.legacy_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.legacy_table.verticalHeader().setVisible(False)
        layout.addWidget(self.legacy_table)
        
        self.legacy_count_lbl = QLabel("0 legacy components")
        layout.addWidget(self.legacy_count_lbl)
        
    def _load_legacy_tab(self):
        query = self.legacy_search_input.text().strip()
        results = ComponentLibraryService.search_legacy_components(query=query, include_retired=True)
        
        self.legacy_table.setRowCount(0)
        for comp in results:
            row = self.legacy_table.rowCount()
            self.legacy_table.insertRow(row)
            
            self.legacy_table.setItem(row, 0, QTableWidgetItem(comp["display_name"]))
            self.legacy_table.setItem(row, 1, QTableWidgetItem(comp["shortcut"] or ""))
            self.legacy_table.setItem(row, 2, QTableWidgetItem(comp["material"] or ""))
            
            fit_val = comp["fits"]
            fit_str = f"{fit_val:.4f}" if fit_val is not None else "0.0000"
            self.legacy_table.setItem(row, 3, QTableWidgetItem(fit_str))
            
            self.legacy_table.setItem(row, 4, QTableWidgetItem(comp["mapping_status"] or ""))
            
            stat_item = QTableWidgetItem(comp["status"])
            stat_item.setForeground(QColor("#198754" if comp["status"] == "active" else "#dc3545"))
            self.legacy_table.setItem(row, 5, stat_item)
            
            toggle_btn = QPushButton("Retire" if comp["status"] == "active" else "Reactivate")
            toggle_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            toggle_btn.clicked.connect(lambda _, c=comp: self._toggle_legacy_status(c))
            self.legacy_table.setCellWidget(row, 6, toggle_btn)
            
        self.legacy_count_lbl.setText(f"Showing {len(results)} legacy components")
        
    def _toggle_legacy_status(self, comp: Dict[str, Any]):
        new_status = "retired" if comp["status"] == "active" else "active"
        success, msg = ComponentLibraryService.set_component_status(
            component_id=comp["id"],
            new_status=new_status,
            reason=f"Admin toggled status to {new_status}"
        )
        if success:
            self._load_legacy_tab()
            self._load_changelog_tab()
        else:
            QMessageBox.warning(self, "Status Change Error", msg)

    # ---------------- 3. UNASSIGNED DISPLAY NAMES (BATCH EDIT) ----------------
    def _setup_unassigned_ui(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        info_lbl = QLabel(
            "<b>Batch Display Name Assignment:</b> Enter proposed display names below. "
            "Click <b>'Validate Batch'</b> to check rules or <b>'Save All Assignments'</b> to apply all atomically."
        )
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)
        
        top_bar = QHBoxLayout()
        self.unassigned_count_lbl = QLabel("0 unassigned components")
        self.unassigned_count_lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        top_bar.addWidget(self.unassigned_count_lbl)
        top_bar.addStretch()
        
        val_btn = QPushButton("Validate Batch")
        val_btn.clicked.connect(self._validate_unassigned_batch)
        top_bar.addWidget(val_btn)
        
        save_batch_btn = QPushButton("Save All Assignments")
        save_batch_btn.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 6px 14px;")
        save_batch_btn.clicked.connect(self._save_unassigned_batch)
        top_bar.addWidget(save_batch_btn)
        
        layout.addLayout(top_bar)
        
        self.unassigned_table = QTableWidget()
        self.unassigned_table.setColumnCount(7)
        self.unassigned_table.setHorizontalHeaderLabels([
            "Proposed Display Name (Editable)", "Component Type", "Subtype",
            "Category", "Failure Rate ID", "Item No", "Validation Status"
        ])
        self.unassigned_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.unassigned_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.unassigned_table.verticalHeader().setVisible(False)
        layout.addWidget(self.unassigned_table)
        
    def _load_unassigned_tab(self):
        records = ComponentLibraryService.get_unassigned_display_names()
        self.unassigned_table.setRowCount(0)
        
        for comp in records:
            row = self.unassigned_table.rowCount()
            self.unassigned_table.insertRow(row)
            
            edit_item = QTableWidgetItem("")
            edit_item.setData(Qt.ItemDataRole.UserRole, comp["id"])
            edit_item.setBackground(QColor("#f8f9fa"))
            self.unassigned_table.setItem(row, 0, edit_item)
            
            type_item = QTableWidgetItem(comp["component_type"])
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.unassigned_table.setItem(row, 1, type_item)
            
            sub_item = QTableWidgetItem(comp["component_subtype"] or "")
            sub_item.setFlags(sub_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.unassigned_table.setItem(row, 2, sub_item)
            
            cat_item = QTableWidgetItem(comp["component_use_category"] or "")
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.unassigned_table.setItem(row, 3, cat_item)
            
            fr_item = QTableWidgetItem(comp["failure_rate_id"])
            fr_item.setFlags(fr_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.unassigned_table.setItem(row, 4, fr_item)
            
            item_no = QTableWidgetItem(str(comp.get("item_no") or ""))
            item_no.setFlags(item_no.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.unassigned_table.setItem(row, 5, item_no)
            
            stat_item = QTableWidgetItem("Pending Input")
            stat_item.setForeground(QColor("#6c757d"))
            stat_item.setFlags(stat_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.unassigned_table.setItem(row, 6, stat_item)
            
        self.unassigned_count_lbl.setText(f"{len(records)} unassigned components")
        
    def _validate_unassigned_batch(self) -> Tuple[bool, List[Dict[str, str]]]:
        assignments: List[Dict[str, str]] = []
        proposed_seen: Dict[str, int] = {}
        all_valid = True
        
        for row in range(self.unassigned_table.rowCount()):
            item0 = self.unassigned_table.item(row, 0)
            comp_id = item0.data(Qt.ItemDataRole.UserRole)
            prop_name = item0.text().strip()
            stat_item = self.unassigned_table.item(row, 6)
            
            if not prop_name:
                stat_item.setText("Blank (Skipped)")
                stat_item.setForeground(QColor("#6c757d"))
                continue
                
            # Check duplicate in current table
            if prop_name in proposed_seen:
                stat_item.setText(f"Duplicate in batch (Row {proposed_seen[prop_name] + 1})")
                stat_item.setForeground(QColor("#dc3545"))
                all_valid = False
                continue
            proposed_seen[prop_name] = row
            
            # Check against database
            valid, msg = ComponentLibraryService.validate_display_name(prop_name, comp_id)
            if not valid:
                stat_item.setText(f"Invalid: {msg}")
                stat_item.setForeground(QColor("#dc3545"))
                all_valid = False
            else:
                stat_item.setText("Valid")
                stat_item.setForeground(QColor("#198754"))
                assignments.append({
                    "component_id": comp_id,
                    "proposed_display_name": prop_name,
                    "change_reason": "Batch display name assignment"
                })
                
        return all_valid, assignments

    def _save_unassigned_batch(self):
        all_valid, assignments = self._validate_unassigned_batch()
        if not assignments:
            QMessageBox.information(self, "Batch Empty", "No display names have been entered to save.")
            return
            
        if not all_valid:
            QMessageBox.warning(
                self,
                "Batch Validation Failed",
                "One or more proposed display names are invalid or duplicated. "
                "The batch cannot be saved until all errors are corrected."
            )
            return
            
        success, msg, errors = ComponentLibraryService.batch_assign_display_names(assignments, user="admin")
        if not success:
            QMessageBox.critical(self, "Batch Save Failed", f"Batch save transaction was rolled back:\n{msg}")
            return
            
        QMessageBox.information(self, "Batch Saved", msg)
        self._load_unassigned_tab()
        self._load_exida_tab()
        self._load_changelog_tab()

    # ---------------- 4. CHANGE LOG TAB ----------------
    def _setup_changelog_ui(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Audit Trail & Change History:</b>"))
        top_bar.addStretch()
        
        refresh_btn = QPushButton("Refresh Log")
        refresh_btn.clicked.connect(self._load_changelog_tab)
        top_bar.addWidget(refresh_btn)
        layout.addLayout(top_bar)
        
        self.changelog_table = QTableWidget()
        self.changelog_table.setColumnCount(8)
        self.changelog_table.setHorizontalHeaderLabels([
            "Timestamp", "Component ID", "Action", "Field",
            "Old Value", "New Value", "Reason", "User"
        ])
        self.changelog_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.changelog_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.changelog_table.verticalHeader().setVisible(False)
        layout.addWidget(self.changelog_table)
        
    def _load_changelog_tab(self):
        logs = ComponentLibraryService.get_change_logs(limit=200)
        self.changelog_table.setRowCount(0)
        
        for log in logs:
            row = self.changelog_table.rowCount()
            self.changelog_table.insertRow(row)
            
            ts_str = log["timestamp"][:19].replace("T", " ") if log["timestamp"] else ""
            self.changelog_table.setItem(row, 0, QTableWidgetItem(ts_str))
            self.changelog_table.setItem(row, 1, QTableWidgetItem(log["component_id"]))
            self.changelog_table.setItem(row, 2, QTableWidgetItem(log["action"]))
            self.changelog_table.setItem(row, 3, QTableWidgetItem(log["field_changed"] or ""))
            self.changelog_table.setItem(row, 4, QTableWidgetItem(str(log["old_value"]) if log["old_value"] is not None else "(null)"))
            self.changelog_table.setItem(row, 5, QTableWidgetItem(str(log["new_value"]) if log["new_value"] is not None else "(null)"))
            self.changelog_table.setItem(row, 6, QTableWidgetItem(log["change_reason"] or ""))
            self.changelog_table.setItem(row, 7, QTableWidgetItem(log["user"] or ""))

    # ---------------- 5. DATABASE ADMINISTRATION TAB ----------------
    def _setup_admin_ui(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        info_group = QGroupBox("Operational Database Information")
        info_layout = QFormLayout(info_group)
        
        db_path_lbl = QLineEdit(str(get_database_path().absolute()))
        db_path_lbl.setReadOnly(True)
        info_layout.addRow("Database Path:", db_path_lbl)
        
        self.schema_ver_lbl = QLineEdit("1.0")
        self.schema_ver_lbl.setReadOnly(True)
        info_layout.addRow("Schema Version:", self.schema_ver_lbl)
        
        self.db_status_lbl = QLineEdit("Active")
        self.db_status_lbl.setReadOnly(True)
        info_layout.addRow("Status:", self.db_status_lbl)
        
        layout.addWidget(info_group)
        
        # Danger zone / Rebuild
        danger_group = QGroupBox("Database Maintenance & Rebuild")
        danger_layout = QVBoxLayout(danger_group)
        
        danger_desc = QLabel(
            "<b>Warning:</b> Rebuilding the database will re-initialize all components, profiles, and failure modes "
            "from the seed JSON file (<code>Combined_Exida_Component_library_version2.json</code>). "
            "Any custom display names or modifications not in the seed will be reset."
        )
        danger_desc.setWordWrap(True)
        danger_layout.addWidget(danger_desc)
        
        rebuild_btn = QPushButton("Rebuild Database from Seed JSON")
        rebuild_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover { background-color: #bb2d3b; }
        """)
        rebuild_btn.clicked.connect(self._on_rebuild_database)
        danger_layout.addWidget(rebuild_btn)
        
        layout.addWidget(danger_group)
        layout.addStretch()
        
    def _on_rebuild_database(self):
        reply = QMessageBox.warning(
            self,
            "Confirm Database Rebuild",
            "Are you sure you want to completely rebuild the SQLite database from seed JSON?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = DatabaseService.initialize_from_seed(force_rebuild=True)
            if success:
                QMessageBox.information(self, "Rebuild Successful", msg)
                self._load_exida_tab()
                self._load_legacy_tab()
                self._load_unassigned_tab()
                self._load_changelog_tab()
            else:
                QMessageBox.critical(self, "Rebuild Failed", msg)
