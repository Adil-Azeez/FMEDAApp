"""
bulk_assignment_dialogs.py: Reusable UI modals for component details, duplication,
bulk assignment pickers, bulk action summaries, and deletion confirmation in the FMEDA spreadsheet.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QFrame,
    QScrollArea, QMessageBox, QRadioButton, QButtonGroup, QDialogButtonBox,
    QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush
from typing import Optional, List, Dict, Any, Tuple
import copy

from fmeda_tool.models import Component, Unit, Project, FailureModeAssignment


class ComponentDetailsDialog(QDialog):
    """
    Read-only dialog displaying comprehensive component metadata, BOM mapping,
    reliability source, base FIT, and full failure-mode assignment table.
    """
    def __init__(self, component: Component, unit: Unit, project: Project, parent=None):
        super().__init__(parent)
        self.component = component
        self.unit = unit
        self.project = project
        
        self.setWindowTitle(f"Component Details: {component.position} - {component.name}")
        self.setMinimumWidth(820)
        self.setMinimumHeight(560)
        self.resize(880, 600)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        
        # Header Banner
        header = QFrame()
        header.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 10px;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(10, 8, 10, 8)
        
        title_lbl = QLabel(f"<b>🔍 {self.component.position}</b> — {self.component.name}")
        title_lbl.setStyleSheet("font-size: 14px; color: #212529;")
        h_lay.addWidget(title_lbl)
        h_lay.addStretch()
        
        src_text = self.component.source_type.title() if self.component.source_type else "Manual"
        badge_lbl = QLabel(f"Source: {src_text}")
        badge_lbl.setStyleSheet("background-color: #e7f1ff; color: #0c63e4; font-weight: bold; padding: 4px 10px; border-radius: 4px; border: 1px solid #b6d4fe;")
        h_lay.addWidget(badge_lbl)
        layout.addWidget(header)
        
        # Metadata Form Grid
        meta_frame = QFrame()
        meta_frame.setStyleSheet("background-color: #ffffff; border: 1px solid #e9ecef; border-radius: 6px; padding: 8px;")
        m_lay = QFormLayout(meta_frame)
        m_lay.setSpacing(8)
        m_lay.setContentsMargins(10, 10, 10, 10)
        
        # BOM info
        bom_comp = next((b for b in getattr(self.unit, "bom_components", []) or [] if b.designator.upper() == self.component.position.upper()), None)
        bom_str = f"Mapped ({bom_comp.part_number or 'No Part Number'})" if bom_comp else "Not Mapped to BOM / Manual"
        
        disp_name = self.component.name
        if self.component.snapshot and isinstance(self.component.snapshot, dict):
            disp_name = self.component.snapshot.get("displayed_label") or self.component.snapshot.get("display_name") or disp_name
            
        m_lay.addRow("<b>Component ID / Position:</b>", QLabel(self.component.position))
        m_lay.addRow("<b>Display Name / Type:</b>", QLabel(disp_name))
        m_lay.addRow("<b>Internal Part Number:</b>", QLabel(self.component.internal_pn or "—"))
        m_lay.addRow("<b>Value / Description:</b>", QLabel(self.component.value or "—"))
        m_lay.addRow("<b>Function:</b>", QLabel(self.component.function or "—"))
        m_lay.addRow("<b>Base Failure Rate (FIT):</b>", QLabel(f"{self.component.failure_rate or 0.0:.4f} FIT (Profile: {self.component.selected_profile or 'Default'})"))
        m_lay.addRow("<b>BOM Status:</b>", QLabel(bom_str))
        if self.component.component_subtype:
            m_lay.addRow("<b>Subtype:</b>", QLabel(self.component.component_subtype))
        if self.component.component_use_category:
            m_lay.addRow("<b>Use Category:</b>", QLabel(self.component.component_use_category))
            
        layout.addWidget(meta_frame)
        
        # Failure Modes Table
        fm_lbl = QLabel("<b>Failure Modes Distribution & Safety Assignments:</b>")
        fm_lbl.setStyleSheet("font-size: 12px; color: #495057;")
        layout.addWidget(fm_lbl)
        
        table = QTableWidget()
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "Failure Mode", "Rate %", "Local FIT", "Deviation",
            "Diagnostic Measure", "Detection %", "Classification", "Mitigation"
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #dee2e6;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                font-weight: bold;
                border: 1px solid #dee2e6;
                padding: 4px;
            }
        """)
        
        row_idx = 0
        table.setRowCount(len(self.component.failure_modes))
        for fm_name, fm_pct in self.component.failure_modes.items():
            assignment = next((a for a in self.component.failure_mode_assignments if a.failure_mode_name == fm_name), None)
            local_fit = (self.component.failure_rate or 0.0) * (fm_pct / 100.0)
            
            dev_name = "—"
            if assignment and assignment.deviation_id:
                dev = next((d for d in self.project.deviations if d.id == assignment.deviation_id), None)
                dev_name = dev.name if dev else assignment.deviation_id
                
            dm_name = "—"
            det_str = "—"
            if assignment and assignment.diagnostic_measure_id:
                dm = next((m for m in self.project.diagnostic_measures if m.id == assignment.diagnostic_measure_id), None)
                dm_name = dm.description if dm else assignment.diagnostic_measure_id
                det_str = f"{assignment.detection_percentage or 0.0:.1f}%"
            elif assignment and assignment.detection_percentage:
                det_str = f"{assignment.detection_percentage:.1f}%"
                
            class_str = "Not Evaluated"
            if assignment:
                if assignment.classification == "safe_failure":
                    class_str = "Safe Failure"
                elif assignment.classification == "dangerous_failure":
                    class_str = "Dangerous Failure"
                    
            mit_name = "—"
            if assignment and assignment.mitigation_id:
                mit = next((m for m in self.project.mitigations if m.id == assignment.mitigation_id), None)
                mit_name = mit.name if mit else assignment.mitigation_id
                
            table.setItem(row_idx, 0, QTableWidgetItem(fm_name))
            table.setItem(row_idx, 1, QTableWidgetItem(f"{fm_pct:.1f}%"))
            table.setItem(row_idx, 2, QTableWidgetItem(f"{local_fit:.4f}"))
            table.setItem(row_idx, 3, QTableWidgetItem(dev_name))
            table.setItem(row_idx, 4, QTableWidgetItem(dm_name))
            table.setItem(row_idx, 5, QTableWidgetItem(det_str))
            table.setItem(row_idx, 6, QTableWidgetItem(class_str))
            table.setItem(row_idx, 7, QTableWidgetItem(mit_name))
            row_idx += 1
            
        layout.addWidget(table)
        
        # Close Button
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("background-color: #6c757d; color: white; padding: 6px 20px; font-weight: bold; border-radius: 4px;")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)


class DuplicateComponentDialog(QDialog):
    """
    Modal dialog prompting for a new unique component label/designator when duplicating a component.
    """
    def __init__(self, source_component: Component, existing_positions: List[str], parent=None):
        super().__init__(parent)
        self.source_component = source_component
        self.existing_positions = [p.upper() for p in existing_positions if p]
        self.new_position: str = ""
        
        self.setWindowTitle("Duplicate Component")
        self.setMinimumWidth(460)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        info_lbl = QLabel(f"Create a duplicate of <b>{self.source_component.position}</b> ({self.source_component.name}):")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)
        
        form = QFormLayout()
        
        # Suggest unique position
        base_pos = self.source_component.position
        suggested = f"{base_pos}_COPY"
        count = 1
        while suggested.upper() in self.existing_positions:
            suggested = f"{base_pos}_COPY{count}"
            count += 1
            
        self.pos_input = QLineEdit(suggested)
        self.pos_input.setPlaceholderText("e.g. C201_COPY or C202")
        self.pos_input.selectAll()
        form.addRow("<b>New Designator*:</b>", self.pos_input)
        layout.addLayout(form)
        
        note_lbl = QLabel("<small style='color:#6c757d;'>The new component will duplicate all failure modes and parameters. BOM linkage will not be copied automatically.</small>")
        note_lbl.setWordWrap(True)
        layout.addWidget(note_lbl)
        
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px 16px; border-radius: 4px;")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)
        
        dup_btn = QPushButton("📋 Duplicate")
        dup_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px;")
        dup_btn.clicked.connect(self._on_accept)
        btn_box.addWidget(dup_btn)
        
        layout.addLayout(btn_box)

    def _on_accept(self):
        val = self.pos_input.text().strip()
        if not val:
            QMessageBox.warning(self, "Validation Error", "Please enter a Component ID / Designator.")
            self.pos_input.setFocus()
            return
            
        if val.upper() in self.existing_positions:
            QMessageBox.warning(
                self, "Designator Already Exists",
                f"Designator '{val}' is already used in this functional group.\nPlease enter a unique designator."
            )
            self.pos_input.selectAll()
            self.pos_input.setFocus()
            return
            
        self.new_position = val
        self.accept()

    def get_new_position(self) -> str:
        return self.new_position


class BulkItemPickerDialog(QDialog):
    """
    Searchable selector dialog to pick a Deviation, Diagnostic Measure, Mitigation, or Classification for bulk assignment.
    """
    def __init__(
        self,
        title: str,
        item_type: str,
        items: List[Tuple[str, str, Any]],  # (Label, Description/Subtext, Data/ID)
        current_value: Any = None,
        allow_create_new: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        self.item_type = item_type
        self.items = items
        self.current_value = current_value
        self.allow_create_new = allow_create_new
        
        self.selected_value: Any = None
        self.selected_label: str = ""
        self.create_new_requested: bool = False
        
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setMinimumHeight(400)
        self._setup_ui()
        self._populate_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        
        header_lbl = QLabel(f"<b>Select {self.item_type} to apply to all selected components:</b>")
        layout.addWidget(header_lbl)
        
        # Search Filter
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(f"Search {self.item_type}...")
        self.search_input.textChanged.connect(self._filter_items)
        layout.addWidget(self.search_input)
        
        # Items Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([f"{self.item_type}", "Details / Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(lambda: self._on_select())
        layout.addWidget(self.table)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        if self.allow_create_new:
            self.create_btn = QPushButton(f"➕ Create New {self.item_type}...")
            self.create_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px 12px; border-radius: 4px;")
            self.create_btn.clicked.connect(self._on_create_new)
            btn_layout.addWidget(self.create_btn)
            
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px 14px; border-radius: 4px;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        self.select_btn = QPushButton("Select")
        self.select_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px;")
        self.select_btn.clicked.connect(self._on_select)
        btn_layout.addWidget(self.select_btn)
        
        layout.addLayout(btn_layout)

    def _populate_list(self, filter_text: str = ""):
        self.table.setRowCount(0)
        query = filter_text.strip().lower()
        
        # Always include "-- None / Clear --" at top
        display_items = [("-- None / Clear --", "Clears current assignment", None)] + self.items
        
        row = 0
        for label, desc, data in display_items:
            if query and query not in label.lower() and query not in desc.lower():
                continue
            self.table.insertRow(row)
            
            lbl_item = QTableWidgetItem(label)
            lbl_item.setData(Qt.ItemDataRole.UserRole, data)
            lbl_item.setData(Qt.ItemDataRole.UserRole + 1, label)
            
            desc_item = QTableWidgetItem(desc)
            if data is None:
                lbl_item.setForeground(QBrush(QColor("#6c757d")))
                desc_item.setForeground(QBrush(QColor("#6c757d")))
                
            self.table.setItem(row, 0, lbl_item)
            self.table.setItem(row, 1, desc_item)
            
            if data == self.current_value:
                self.table.selectRow(row)
            row += 1
            
        if self.table.rowCount() > 0 and not self.table.selectedItems():
            self.table.selectRow(0)

    def _filter_items(self, text: str):
        self._populate_list(filter_text=text)

    def _on_create_new(self):
        self.create_new_requested = True
        self.accept()

    def _on_select(self):
        sel = self.table.selectedItems()
        if not sel:
            QMessageBox.warning(self, "Selection Required", f"Please select a {self.item_type} from the list.")
            return
        row = self.table.currentRow()
        item = self.table.item(row, 0)
        if item:
            self.selected_value = item.data(Qt.ItemDataRole.UserRole)
            self.selected_label = item.data(Qt.ItemDataRole.UserRole + 1)
        self.accept()

    def get_selection(self) -> Tuple[Any, str]:
        return self.selected_value, self.selected_label


class BulkActionSummaryDialog(QDialog):
    """
    Confirmation summary modal displayed before applying bulk operations.
    Shows the action, selected value, number of components, and number of affected rows.
    """
    def __init__(
        self,
        action_title: str,
        action_name: str,
        value_label: str,
        comp_count: int,
        row_count: int,
        component_designators: Optional[List[str]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.action_title = action_title
        self.action_name = action_name
        self.value_label = value_label
        self.comp_count = comp_count
        self.row_count = row_count
        self.component_designators = component_designators or []
        
        self.setWindowTitle(action_title)
        self.setMinimumWidth(480)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        
        # Header Box
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #f0f7ff; border: 1px solid #b6d4fe; border-radius: 6px; padding: 10px;")
        h_lay = QVBoxLayout(header_frame)
        h_lay.setContentsMargins(10, 8, 10, 8)
        
        t_lbl = QLabel(f"<b>⚡ Bulk Action Summary</b>")
        t_lbl.setStyleSheet("font-size: 13px; color: #084298;")
        h_lay.addWidget(t_lbl)
        
        desc_lbl = QLabel("Please review the changes before applying to the functional group:")
        desc_lbl.setStyleSheet("font-size: 11px; color: #052c65;")
        h_lay.addWidget(desc_lbl)
        layout.addWidget(header_frame)
        
        # Summary Form
        form_frame = QFrame()
        form_frame.setStyleSheet("background-color: #ffffff; border: 1px solid #dee2e6; border-radius: 6px; padding: 8px;")
        f_lay = QFormLayout(form_frame)
        f_lay.setSpacing(8)
        f_lay.setContentsMargins(12, 10, 12, 10)
        
        f_lay.addRow("<b>Action:</b>", QLabel(self.action_name))
        f_lay.addRow("<b>Value to Apply:</b>", QLabel(f"<b>{self.value_label}</b>"))
        f_lay.addRow("<b>Selected Components:</b>", QLabel(f"{self.comp_count} component{'s' if self.comp_count != 1 else ''}"))
        f_lay.addRow("<b>Affected Failure-Mode Rows:</b>", QLabel(f"<b>{self.row_count}</b> rows"))
        
        if self.component_designators:
            des_str = ", ".join(self.component_designators[:15])
            if len(self.component_designators) > 15:
                des_str += f" ... (+{len(self.component_designators)-15} more)"
            des_lbl = QLabel(des_str)
            des_lbl.setWordWrap(True)
            des_lbl.setStyleSheet("color: #495057;")
            f_lay.addRow("<b>Components:</b>", des_lbl)
            
        layout.addWidget(form_frame)
        
        note_lbl = QLabel("<small style='color: #6c757d;'>Applying this operation will update all applicable failure-mode rows atomically and create one Undo entry.</small>")
        note_lbl.setWordWrap(True)
        layout.addWidget(note_lbl)
        
        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px 16px; border-radius: 4px;")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)
        
        apply_btn = QPushButton("Apply Bulk Action")
        apply_btn.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 6px 20px; border-radius: 4px;")
        apply_btn.clicked.connect(self.accept)
        btn_box.addWidget(apply_btn)
        
        layout.addLayout(btn_box)


class DeleteComponentsConfirmDialog(QDialog):
    """
    Confirmation dialog before deleting single or multiple components.
    Shows the designators and warns that all failure-mode rows and BOM mappings will be removed/released.
    """
    def __init__(self, components: List[Component], parent=None):
        super().__init__(parent)
        self.components = components
        self.count = len(components)
        
        title = "Delete Component" if self.count == 1 else f"Delete {self.count} Components"
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        
        # Warning Card
        card = QFrame()
        card.setStyleSheet("background-color: #f8d7da; border: 1px solid #f5c2c7; border-radius: 6px; padding: 10px;")
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(10, 8, 10, 8)
        
        if self.count == 1:
            comp = self.components[0]
            w_lbl = QLabel(f"<b>Delete component '{comp.position}' ({comp.name})?</b>")
        else:
            w_lbl = QLabel(f"<b>Delete {self.count} selected components?</b>")
        w_lbl.setStyleSheet("font-size: 13px; color: #842029;")
        c_lay.addWidget(w_lbl)
        
        sub_lbl = QLabel("All associated failure-mode rows will also be removed.\nAssociated BOM positions will be released and available for mapping again.")
        sub_lbl.setStyleSheet("font-size: 11px; color: #842029;")
        c_lay.addWidget(sub_lbl)
        layout.addWidget(card)
        
        # List of component positions if multiple
        if self.count > 1:
            list_frame = QFrame()
            list_frame.setStyleSheet("background-color: #ffffff; border: 1px solid #dee2e6; border-radius: 4px; padding: 6px;")
            l_lay = QVBoxLayout(list_frame)
            l_lay.setContentsMargins(8, 6, 8, 6)
            
            names = [f"• {c.position} ({c.name})" for c in self.components[:12]]
            if len(self.components) > 12:
                names.append(f"• ... and {len(self.components) - 12} more")
            comp_list_lbl = QLabel("\n".join(names))
            comp_list_lbl.setStyleSheet("font-family: monospace; color: #212529;")
            l_lay.addWidget(comp_list_lbl)
            layout.addWidget(list_frame)
            
        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px 16px; border-radius: 4px;")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)
        
        del_btn_text = "Delete Component" if self.count == 1 else f"Delete {self.count} Components"
        del_btn = QPushButton(del_btn_text)
        del_btn.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px;")
        del_btn.clicked.connect(self.accept)
        btn_box.addWidget(del_btn)
        
        layout.addLayout(btn_box)
