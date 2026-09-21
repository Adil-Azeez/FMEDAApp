"""
Component Picker Dialog for copying from existing Exida or Legacy components.
Supports searching across display name, component type, subtype, failure rate ID,
item number, legacy shortcut, and material.
"""

from typing import Optional, Dict, Any, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QButtonGroup, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame,
    QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from fmeda_tool.services.component_library_service import ComponentLibraryService


class ComponentPickerDialog(QDialog):
    """Searchable component picker for copying data from Exida or Legacy components."""

    def __init__(self, selected_profile: str = "Profile 1", parent=None):
        super().__init__(parent)
        self.selected_profile = selected_profile or "Profile 1"
        self.selected_snapshot: Optional[Dict[str, Any]] = None
        self._current_results: List[Dict[str, Any]] = []

        self.setWindowTitle("Copy From Existing Component")
        self.setMinimumWidth(820)
        self.resize(880, 560)

        self._setup_ui()
        self._load_components()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header Title & Description
        hdr_lay = QVBoxLayout()
        hdr_lay.setSpacing(2)
        title_lbl = QLabel("<b>Copy From Existing Component</b>")
        title_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        hdr_lay.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Select an Exida or Legacy component to copy its component type, FIT, "
            "and failure-mode distribution into a new custom component draft."
        )
        desc_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
        desc_lbl.setWordWrap(True)
        hdr_lay.addWidget(desc_lbl)
        layout.addLayout(hdr_lay)

        # Controls Bar: Source Radios, Profile Badge, Search Input
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;")
        ctrl_lay = QVBoxLayout(ctrl_frame)
        ctrl_lay.setContentsMargins(10, 8, 10, 8)
        ctrl_lay.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        src_lbl = QLabel("<b>Source Catalog:</b>")
        top_row.addWidget(src_lbl)

        self.exida_radio = QRadioButton("Exida Components")
        self.exida_radio.setChecked(True)
        self.legacy_radio = QRadioButton("Legacy Unmapped Components")

        self.source_group = QButtonGroup(self)
        self.source_group.addButton(self.exida_radio)
        self.source_group.addButton(self.legacy_radio)

        self.exida_radio.toggled.connect(self._on_source_toggled)
        self.legacy_radio.toggled.connect(self._on_source_toggled)

        top_row.addWidget(self.exida_radio)
        top_row.addWidget(self.legacy_radio)
        top_row.addStretch()

        self.prof_badge = QLabel(f"Profile: <b>{self.selected_profile}</b>")
        self.prof_badge.setStyleSheet("background-color: #e7f1ff; border: 1px solid #b6d4fe; color: #084298; padding: 2px 8px; border-radius: 4px; font-size: 11px;")
        top_row.addWidget(self.prof_badge)

        ctrl_lay.addLayout(top_row)

        # Search Bar
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        search_lbl = QLabel("Search:")
        search_row.addWidget(search_lbl)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search display name, type, subtype, FR-ID, item no, shortcut, material...")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_input, stretch=1)

        ctrl_lay.addLayout(search_row)
        layout.addWidget(ctrl_frame)

        # Components Table
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(lambda _: self._on_select_clicked())
        layout.addWidget(self.table, stretch=1)

        # Status & Preview Footer
        self.preview_lbl = QLabel("Select a component above to copy its properties.")
        self.preview_lbl.setStyleSheet("color: #495057; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(self.preview_lbl)

        # Bottom Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.count_lbl = QLabel("0 components found")
        self.count_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
        btn_row.addWidget(self.count_lbl)

        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 6px 14px;")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self.select_btn = QPushButton("📋 Copy Component Data")
        self.select_btn.setEnabled(False)
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                font-weight: bold;
                padding: 6px 18px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover { background-color: #0b5ed7; }
            QPushButton:disabled { background-color: #6c757d; color: #ced4da; }
        """)
        self.select_btn.clicked.connect(self._on_select_clicked)
        btn_row.addWidget(self.select_btn)

        layout.addLayout(btn_row)

    def _on_source_toggled(self):
        is_exida = self.exida_radio.isChecked()
        self.prof_badge.setVisible(is_exida)
        self._load_components()

    def _on_search_changed(self):
        self._load_components()

    def _load_components(self):
        query = self.search_input.text().strip()
        is_exida = self.exida_radio.isChecked()

        self.table.setRowCount(0)
        self.selected_snapshot = None
        self.select_btn.setEnabled(False)
        self.preview_lbl.setText("Select a component above to copy its properties.")

        if is_exida:
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderLabels([
                "Display Label", "Component Type", "Subtype",
                "Failure Rate ID", "Item No", f"FIT ({self.selected_profile})", "Failure Modes"
            ])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

            results = ComponentLibraryService.search_exida_components(
                query=query,
                profile=self.selected_profile,
                include_retired=False
            )
            self._current_results = results

            for comp in results:
                row = self.table.rowCount()
                self.table.insertRow(row)

                # 0. Display Label
                lbl_item = QTableWidgetItem(comp.get("display_label") or comp.get("display_name") or comp.get("component_type") or "")
                lbl_item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                lbl_item.setData(Qt.ItemDataRole.UserRole, comp["id"])
                self.table.setItem(row, 0, lbl_item)

                # 1. Type
                self.table.setItem(row, 1, QTableWidgetItem(comp.get("component_type") or ""))

                # 2. Subtype
                self.table.setItem(row, 2, QTableWidgetItem(comp.get("component_subtype") or ""))

                # 3. FR-ID
                self.table.setItem(row, 3, QTableWidgetItem(comp.get("failure_rate_id") or ""))

                # 4. Item No
                self.table.setItem(row, 4, QTableWidgetItem(str(comp.get("item_no") or "")))

                # 5. FIT
                fit_val = comp.get("failure_rate")
                fit_str = f"{fit_val:.4f}" if fit_val is not None else "N/A"
                self.table.setItem(row, 5, QTableWidgetItem(fit_str))

                # 6. Failure Modes count
                fm_count = len(comp.get("failure_modes", {}))
                self.table.setItem(row, 6, QTableWidgetItem(f"{fm_count} modes"))

            self.count_lbl.setText(f"Showing {len(results)} Exida components")

        else:
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels([
                "Display Name", "Shortcut", "Material", "Legacy FIT", "Failure Modes"
            ])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

            results = ComponentLibraryService.search_legacy_components(
                query=query,
                include_retired=False
            )
            self._current_results = results

            for comp in results:
                row = self.table.rowCount()
                self.table.insertRow(row)

                # 0. Display Name
                dname_item = QTableWidgetItem(comp.get("display_name") or "")
                dname_item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                dname_item.setData(Qt.ItemDataRole.UserRole, comp["id"])
                self.table.setItem(row, 0, dname_item)

                # 1. Shortcut
                self.table.setItem(row, 1, QTableWidgetItem(comp.get("shortcut") or ""))

                # 2. Material
                self.table.setItem(row, 2, QTableWidgetItem(comp.get("material") or ""))

                # 3. FIT
                fit_val = comp.get("fits")
                fit_str = f"{fit_val:.4f}" if fit_val is not None else "N/A"
                self.table.setItem(row, 3, QTableWidgetItem(fit_str))

                # 4. Failure modes
                fm_count = len(comp.get("failure_modes", {}))
                self.table.setItem(row, 4, QTableWidgetItem(f"{fm_count} modes"))

            self.count_lbl.setText(f"Showing {len(results)} Legacy components")

    def _on_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_snapshot = None
            self.select_btn.setEnabled(False)
            self.preview_lbl.setText("Select a component above to copy its properties.")
            return

        row = selected_rows[0].row()
        item0 = self.table.item(row, 0)
        if not item0:
            return

        comp_id = item0.data(Qt.ItemDataRole.UserRole)
        is_exida = self.exida_radio.isChecked()

        if is_exida:
            snap = ComponentLibraryService.get_exida_component_snapshot(comp_id, profile=self.selected_profile)
        else:
            snap = ComponentLibraryService.get_legacy_component_snapshot(comp_id)

        if not snap:
            self.selected_snapshot = None
            self.select_btn.setEnabled(False)
            return

        self.selected_snapshot = snap
        self.select_btn.setEnabled(True)

        lbl = snap.get("displayed_label") or snap.get("display_name") or snap.get("component_type") or "Component"
        fit_val = snap.get("failure_rate")
        fit_str = f"{fit_val:.4f} FIT" if fit_val is not None else "0.0000 FIT"
        fm_count = len(snap.get("failure_modes", {}))
        src_name = "Exida" if is_exida else "Legacy"

        self.preview_lbl.setText(
            f"<b>Selected {src_name}:</b> {lbl} | <b>FIT:</b> {fit_str} | <b>Failure Modes:</b> {fm_count} | <i>Ready to copy</i>"
        )

    def _on_select_clicked(self):
        if not self.selected_snapshot:
            selected_rows = self.table.selectionModel().selectedRows()
            if selected_rows:
                self._on_selection_changed()

        if not self.selected_snapshot:
            QMessageBox.information(self, "No Selection", "Please select a component from the list first.")
            return

        self.accept()
