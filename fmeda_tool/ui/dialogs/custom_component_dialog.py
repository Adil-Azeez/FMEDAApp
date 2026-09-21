"""
Custom Component Dialog for creating and editing SQLite-persisted custom components.
Enforces mandatory component type, mandatory FIT, at least 2 failure modes,
optional unique display name validation, and live running total percentage calculation.
"""

from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QLineEdit, QDoubleSpinBox,
    QMessageBox, QHeaderView, QWidget, QFrame, QAbstractItemView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from fmeda_tool.services.component_library_service import ComponentLibraryService
from fmeda_tool.ui.dialogs.component_picker_dialog import ComponentPickerDialog


class CustomComponentDialog(QDialog):
    """Dialog for creating and editing custom components in the SQLite library."""
    
    def __init__(
        self,
        component_id: Optional[Any] = None,
        custom_comp: Optional[Any] = None,
        parent=None,
        project: Optional[Any] = None
    ):
        super().__init__(parent)
        
        # Support component_id or custom_comp in any format (dict, str, object)
        target = custom_comp if custom_comp is not None else component_id
        if target is not None:
            if isinstance(target, dict):
                self.component_id = target.get("id") or target.get("library_component_id")
            elif isinstance(target, str):
                self.component_id = target
            else:
                self.component_id = getattr(target, "id", None) or getattr(target, "library_component_id", None) or str(target)
        else:
            self.component_id = None
            
        self.is_edit = bool(self.component_id)
        self.saved_snapshot: Optional[Dict[str, Any]] = None
        self.project = project
        
        # Traceability metadata for copied components
        self.copied_from_source_type: Optional[str] = None
        self.copied_from_component_id: Optional[str] = None
        self.copied_from_failure_rate_id: Optional[str] = None
        self.copied_at: Optional[str] = None
        
        title = "Edit Custom Component" if self.is_edit else "New Custom Component"
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        self.resize(700, 580)
        
        self._setup_ui()
        if self.is_edit:
            self._load_existing_data()
        else:
            self._init_default_failure_modes()
            
        self._update_total_percentage()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        
        # Header title and Copy button
        hdr_row = QHBoxLayout()
        title_lbl = QLabel("<b>Edit Custom Component</b>" if self.is_edit else "<b>Create New Custom Component</b>")
        title_lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        hdr_row.addWidget(title_lbl)
        hdr_row.addStretch()
        
        if not self.is_edit:
            self.copy_btn = QPushButton("📋 Copy From Existing Component")
            self.copy_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0d6efd;
                    color: white;
                    font-weight: bold;
                    padding: 5px 14px;
                    border-radius: 4px;
                    font-size: 11px;
                    border: none;
                }
                QPushButton:hover { background-color: #0b5ed7; }
            """)
            self.copy_btn.setToolTip("Copy properties, FIT, and failure modes from an existing Exida or Legacy component")
            self.copy_btn.clicked.connect(self._on_copy_from_existing_clicked)
            hdr_row.addWidget(self.copy_btn)
            
        layout.addLayout(hdr_row)
        
        # Info note
        info_lbl = QLabel(
            "Custom components are saved in the component library (SQLite) and become available "
            "across all projects and mapping workspaces."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(info_lbl)
        
        # Copied source banner (hidden by default)
        self.copied_info_lbl = QLabel("")
        self.copied_info_lbl.setWordWrap(True)
        self.copied_info_lbl.setStyleSheet("background-color: #e7f1ff; color: #084298; border: 1px solid #b6d4fe; padding: 6px 10px; border-radius: 4px; font-size: 11px;")
        self.copied_info_lbl.setVisible(False)
        layout.addWidget(self.copied_info_lbl)
        
        # Form
        form_frame = QFrame()
        form_frame.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;")
        form_lay = QFormLayout(form_frame)
        form_lay.setContentsMargins(12, 10, 12, 10)
        form_lay.setSpacing(8)
        
        self.type_input = QLineEdit()
        self.type_input.setPlaceholderText("e.g. Microcontroller, Custom Sensor, Power IC...")
        form_lay.addRow("<b>Component Type*:</b>", self.type_input)
        
        self.display_name_input = QLineEdit()
        self.display_name_input.setPlaceholderText("Optional unique label (e.g. MCU_STM32, SENS_OPTICAL)...")
        form_lay.addRow("<b>Display Name:</b>", self.display_name_input)
        
        self.fit_input = QDoubleSpinBox()
        self.fit_input.setRange(0.0, 1000000.0)
        self.fit_input.setDecimals(4)
        self.fit_input.setValue(10.0000)
        self.fit_input.setSuffix(" FIT")
        form_lay.addRow("<b>Failure Rate (FIT)*:</b>", self.fit_input)
        
        layout.addWidget(form_frame)
        
        # Failure Modes Section
        fm_header = QHBoxLayout()
        fm_title = QLabel("<b>Failure Mode Distribution (At least 2 required)*</b>")
        fm_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        fm_header.addWidget(fm_title)
        fm_header.addStretch()
        
        self.total_pct_lbl = QLabel("Total: 0.0%")
        self.total_pct_lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.total_pct_lbl.setStyleSheet("color: #0d6efd;")
        fm_header.addWidget(self.total_pct_lbl)
        layout.addLayout(fm_header)
        
        note_fm = QLabel("<i>Note: Failure-mode percentages do not have to total 100%. Any non-negative distribution is allowed.</i>")
        note_fm.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(note_fm)
        
        # Failure Modes Table
        self.fm_table = QTableWidget()
        self.fm_table.setColumnCount(3)
        self.fm_table.setHorizontalHeaderLabels(["Failure Mode Name*", "Percentage %*", "Action"])
        self.fm_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.fm_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.fm_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.fm_table.verticalHeader().setVisible(False)
        self.fm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.fm_table, stretch=1)
        
        # Add Mode Button
        add_btn_row = QHBoxLayout()
        self.add_fm_btn = QPushButton("➕ Add Failure Mode")
        self.add_fm_btn.setStyleSheet("padding: 4px 12px; font-weight: bold;")
        self.add_fm_btn.clicked.connect(lambda: self._add_failure_mode_row("", 0.0))
        add_btn_row.addWidget(self.add_fm_btn)
        add_btn_row.addStretch()
        layout.addLayout(add_btn_row)
        
        # Bottom Actions
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        
        if self.is_edit:
            self.delete_btn = QPushButton("🗑️ Delete Component")
            self.delete_btn.setStyleSheet("background-color: #dc3545; color: white; padding: 6px 14px; border-radius: 4px;")
            self.delete_btn.clicked.connect(self._on_delete_clicked)
            bottom_row.addWidget(self.delete_btn)
            
        bottom_row.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 6px 16px;")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)
        
        self.save_btn = QPushButton("💾 Save Component")
        self.save_btn.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 6px 22px; border-radius: 4px;")
        self.save_btn.clicked.connect(self._on_save_clicked)
        bottom_row.addWidget(self.save_btn)
        
        layout.addLayout(bottom_row)

    def _init_default_failure_modes(self):
        """Initializes default 2 failure mode rows for a new component."""
        self._add_failure_mode_row("Open Circuit", 50.0)
        self._add_failure_mode_row("Short Circuit", 50.0)

    def _add_failure_mode_row(self, name: str = "", pct: float = 0.0):
        row = self.fm_table.rowCount()
        self.fm_table.insertRow(row)
        
        # Col 0: Name QLineEdit
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("e.g. Open, Short, Drift, Value Change...")
        name_edit.textChanged.connect(self._on_fm_data_changed)
        self.fm_table.setCellWidget(row, 0, name_edit)
        
        # Col 1: Percentage QDoubleSpinBox
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(1)
        spin.setValue(pct)
        spin.setSuffix("%")
        spin.valueChanged.connect(self._on_fm_data_changed)
        self.fm_table.setCellWidget(row, 1, spin)
        
        # Col 2: Remove button
        del_btn = QPushButton("❌")
        del_btn.setToolTip("Remove this failure mode")
        del_btn.setStyleSheet("border: none; padding: 2px 6px; color: #dc3545;")
        del_btn.clicked.connect(lambda checked, btn=del_btn: self._remove_failure_mode_row(btn))
        self.fm_table.setCellWidget(row, 2, del_btn)
        
        self._update_total_percentage()

    def _remove_failure_mode_row(self, btn: QPushButton):
        for r in range(self.fm_table.rowCount()):
            if self.fm_table.cellWidget(r, 2) == btn:
                self.fm_table.removeRow(r)
                break
        self._update_total_percentage()

    def _on_fm_data_changed(self):
        self._update_total_percentage()

    def _update_total_percentage(self):
        total = 0.0
        for r in range(self.fm_table.rowCount()):
            spin = self.fm_table.cellWidget(r, 1)
            if spin and isinstance(spin, QDoubleSpinBox):
                total += spin.value()
        self.total_pct_lbl.setText(f"Total: {total:.1f}%")

    def _load_existing_data(self):
        if not self.component_id:
            return
        snap = ComponentLibraryService.get_custom_component_snapshot(self.component_id)
        if not snap:
            QMessageBox.warning(self, "Error", f"Custom component '{self.component_id}' not found.")
            self.reject()
            return
            
        self.type_input.setText(snap.get("component_type") or "")
        self.display_name_input.setText(snap.get("display_name") or "")
        self.fit_input.setValue(float(snap.get("failure_rate") or 0.0))
        
        self.copied_from_source_type = snap.get("copied_from_source_type")
        self.copied_from_component_id = snap.get("copied_from_component_id")
        self.copied_from_failure_rate_id = snap.get("copied_from_failure_rate_id")
        self.copied_at = snap.get("copied_at")
        
        if self.copied_from_source_type:
            src_title = self.copied_from_source_type.title()
            fr_str = f" ({self.copied_from_failure_rate_id})" if self.copied_from_failure_rate_id else ""
            self.copied_info_lbl.setText(
                f"📋 <b>Traceability:</b> Originally copied from {src_title} component "
                f"ID <code>{self.copied_from_component_id}</code>{fr_str} at {self.copied_at}."
            )
            self.copied_info_lbl.setVisible(True)
            
        self.fm_table.setRowCount(0)
        fms = snap.get("failure_modes", {})
        for fm_name, fm_pct in fms.items():
            self._add_failure_mode_row(fm_name, fm_pct)
            
        if self.fm_table.rowCount() < 2:
            while self.fm_table.rowCount() < 2:
                self._add_failure_mode_row("", 0.0)

    def _on_copy_from_existing_clicked(self):
        active_proj = self._get_active_project()
        active_profile = (
            getattr(active_proj, "selected_profile", None) or
            getattr(active_proj, "environmental_profile", None) or
            getattr(self.parent(), "project_profile", None) or
            getattr(self, "project_profile", None) or
            "Profile 1"
        )
        dlg = ComponentPickerDialog(selected_profile=active_profile, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_snapshot:
            self._apply_copied_snapshot(dlg.selected_snapshot)

    def _apply_copied_snapshot(self, snap: Dict[str, Any]):
        self.copied_from_source_type = snap.get("source_type", "exida")
        self.copied_from_component_id = snap.get("library_component_id")
        self.copied_from_failure_rate_id = snap.get("failure_rate_id")
        self.copied_at = datetime.now().isoformat()
        
        # Component Type
        comp_type = snap.get("component_type") or snap.get("material") or snap.get("displayed_label") or ""
        self.type_input.setText(comp_type)
        
        # Suggested Display Name
        suggested_name = snap.get("display_name") or snap.get("displayed_label") or ""
        self.display_name_input.setText(suggested_name)
        
        # FIT
        fit_val = snap.get("failure_rate")
        self.fit_input.setValue(float(fit_val) if fit_val is not None and float(fit_val) >= 0.0 else 10.0)
        
        # Failure modes
        self.fm_table.setRowCount(0)
        fms = snap.get("failure_modes", {})
        for fm_name, fm_pct in fms.items():
            self._add_failure_mode_row(fm_name, float(fm_pct))
            
        if self.fm_table.rowCount() < 2:
            while self.fm_table.rowCount() < 2:
                self._add_failure_mode_row("", 0.0)
                
        self._update_total_percentage()
        
        # Update Info Banner
        src_title = self.copied_from_source_type.title()
        src_label = snap.get("displayed_label") or snap.get("display_name") or snap.get("component_type") or ""
        fr_str = f" ({self.copied_from_failure_rate_id})" if self.copied_from_failure_rate_id else ""
        self.copied_info_lbl.setText(
            f"📋 <b>Source:</b> Copied from {src_title} component '<b>{src_label}</b>'{fr_str}. "
            f"You may edit all fields. Note: Display name must be unique across catalogs or left empty."
        )
        self.copied_info_lbl.setVisible(True)

    @property
    def fm_total_lbl(self):
        return self.total_pct_lbl

    def add_failure_mode(self, name: str, pct: float = 0.0):
        self._add_failure_mode_row(name, pct)

    def _on_save(self):
        self._on_save_clicked()

    def _collect_failure_modes(self) -> Tuple[bool, str, Dict[str, float]]:
        modes: Dict[str, float] = {}
        row_count = self.fm_table.rowCount()
        
        for r in range(row_count):
            name_widget = self.fm_table.cellWidget(r, 0)
            spin_widget = self.fm_table.cellWidget(r, 1)
            
            if not isinstance(name_widget, QLineEdit) or not isinstance(spin_widget, QDoubleSpinBox):
                continue
                
            raw_name = name_widget.text()
            name = raw_name.strip()
            pct = spin_widget.value()
            
            if raw_name != "" and not name:
                return False, "Failure mode name cannot be empty.", {}
                
            if not name:
                continue
                
            if name in modes:
                return False, f"Duplicate failure mode name '{name}'. Each failure mode name must be distinct.", {}
            modes[name] = pct
            
        if len(modes) < 2:
            return False, "At least 2 failure modes with non-empty names are required.", {}
            
        return True, "", modes

    def _on_save_clicked(self):
        comp_type = self.type_input.text().strip()
        if not comp_type:
            QMessageBox.warning(self, "Validation Error", "Component Type is required.")
            self.type_input.setFocus()
            return
            
        fit_val = self.fit_input.value()
        if fit_val <= 0.0:
            QMessageBox.warning(self, "Validation Error", "Failure Rate (FIT) must be greater than 0.")
            self.fit_input.setFocus()
            return
            
        disp_name = self.display_name_input.text().strip() or None
        
        valid_fm, err_fm, failure_modes = self._collect_failure_modes()
        if not valid_fm:
            QMessageBox.warning(self, "Validation Error", err_fm)
            return
            
        # Display name uniqueness validation
        if disp_name:
            valid_dname, msg_dname = ComponentLibraryService.validate_display_name(
                disp_name, current_component_id=self.component_id
            )
            if not valid_dname:
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    "Display Name already exists. Enter a unique name or leave it empty."
                    if ("already exists" in msg_dname or "conflicts" in msg_dname)
                    else msg_dname
                )
                self.display_name_input.setFocus()
                return
                
        if self.is_edit:
            success, msg, snap = ComponentLibraryService.update_custom_component(
                custom_component_id=self.component_id,
                component_type=comp_type,
                fits=fit_val,
                failure_modes=failure_modes,
                display_name=disp_name
            )
        else:
            success, msg, snap = ComponentLibraryService.create_custom_component(
                component_type=comp_type,
                fits=fit_val,
                failure_modes=failure_modes,
                display_name=disp_name,
                copied_from_source_type=self.copied_from_source_type,
                copied_from_component_id=self.copied_from_component_id,
                copied_from_failure_rate_id=self.copied_from_failure_rate_id,
                copied_at=self.copied_at
            )
            
        if not success:
            QMessageBox.warning(self, "Save Error", msg)
            return
            
        self.saved_snapshot = snap
        QMessageBox.information(self, "Success", msg)
        self.accept()

    def _get_active_project(self) -> Optional[Any]:
        if hasattr(self, "project") and self.project:
            return self.project
        curr = self.parent()
        while curr:
            if hasattr(curr, "current_project") and curr.current_project:
                return curr.current_project
            if hasattr(curr, "project") and curr.project:
                return curr.project
            curr = curr.parent()
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                if hasattr(widget, "current_project") and widget.current_project:
                    return widget.current_project
        return None

    def _on_delete_clicked(self):
        if not self.component_id:
            return
            
        active_proj = self._get_active_project()
        is_ref, ref_msg, _ = ComponentLibraryService.is_custom_component_referenced(
            self.component_id, project=active_proj
        )
        if is_ref:
            QMessageBox.warning(
                self,
                "Deletion Blocked",
                f"This component is currently used and cannot be deleted.\n\n{ref_msg}"
            )
            return
            
        snap = ComponentLibraryService.get_custom_component_snapshot(self.component_id)
        disp_lbl = snap.get("displayed_label") or snap.get("display_name") or snap.get("component_type") if snap else self.component_id
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Delete Custom Component")
        msg_box.setText(f"Are you sure you want to permanently delete custom component '{disp_lbl}'?\n\nThis action cannot be undone.")
        del_btn = msg_box.addButton("Delete", QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(cancel_btn)
        msg_box.exec()
        
        if msg_box.clickedButton() == del_btn:
            success, msg = ComponentLibraryService.delete_custom_component(self.component_id)
            if not success:
                QMessageBox.warning(self, "Error", msg)
                return
            QMessageBox.information(self, "Deleted", msg)
            self.accept()
