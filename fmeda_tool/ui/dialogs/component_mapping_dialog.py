from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QCheckBox, QMessageBox, QFrame, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from typing import List, Dict, Optional
import json
from pathlib import Path

from fmeda_tool.models import BOMComponent, ComponentDB, ComponentMapping, Unit
from fmeda_tool.services import MappingService


class ComponentMappingDialog(QDialog):
    """Dialog to match and confirm mappings between BOM components and database templates"""
    
    def __init__(self, unit: Unit, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Map BOM Components - {unit.name}")
        self.setMinimumSize(950, 600)
        self.resize(1050, 650)
        
        self.unit = unit
        self.db_templates: List[ComponentDB] = self._load_database_templates()
        self.mappings: List[ComponentMapping] = list(self.unit.component_mappings)
        
        # Keep track of UI controls
        self.comboboxes: Dict[str, QComboBox] = {}
        self.confirm_checkboxes: Dict[str, QCheckBox] = {}
        
        self._setup_ui()
        self._populate_table()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Title & Toolbar
        header_layout = QHBoxLayout()
        title = QLabel(f"Manage Mappings for {len(self.unit.bom_components)} BOM Components")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        auto_btn = QPushButton("🤖 Auto-Match All")
        auto_btn.setStyleSheet("background-color: #0dcaf0; font-weight: bold; padding: 6px 12px;")
        auto_btn.clicked.connect(self._auto_match_all)
        header_layout.addWidget(auto_btn)
        
        confirm_all_btn = QPushButton("✓ Confirm All Suggested")
        confirm_all_btn.clicked.connect(self._confirm_all_suggested)
        header_layout.addWidget(confirm_all_btn)
        
        layout.addLayout(header_layout)
        
        # Mappings Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Designator", "Part Number", "Description", "Value",
            "Matched DB Template", "Confidence", "Confirmed", "Status"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(4, 250)
        layout.addWidget(self.table)
        
        # Info Panel
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        info_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 4px;")
        info_layout = QHBoxLayout(info_frame)
        self.stats_label = QLabel("Unconfirmed components require mapping to generate FMEDA rows.")
        info_layout.addWidget(self.stats_label)
        layout.addWidget(info_frame)
        
        # Button box
        btns_layout = QHBoxLayout()
        btns_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save Mappings")
        save_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 6px 16px;")
        save_btn.clicked.connect(self._on_save)
        btns_layout.addWidget(save_btn)
        
        layout.addLayout(btns_layout)
        
    def _load_database_templates(self) -> List[ComponentDB]:
        try:
            db_path = Path("data/components_db.json")
            if db_path.exists():
                with open(db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return [ComponentDB(**item) for item in data]
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load Component Database:\n{str(e)}")
        return []
        
    def _populate_table(self):
        self.table.setRowCount(0)
        self.comboboxes.clear()
        self.confirm_checkboxes.clear()
        
        # Build mapping index by BOM ID
        mapping_by_bom = {m.bom_component_id: m for m in self.mappings}
        
        for bom in self.unit.bom_components:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Metadata
            self.table.setItem(row, 0, QTableWidgetItem(bom.designator))
            self.table.setItem(row, 1, QTableWidgetItem(bom.part_number))
            self.table.setItem(row, 2, QTableWidgetItem(bom.description or ""))
            self.table.setItem(row, 3, QTableWidgetItem(bom.value or ""))
            
            # Matched Template combo
            combo = QComboBox()
            combo.setMinimumWidth(230)
            
            # Get suggestions from service
            suggestions = MappingService.get_suggestions(bom, self.db_templates)
            
            combo.addItem("-- Unmapped --", None)
            for db, score in suggestions:
                combo.addItem(f"{db.display_name} ({score*100:.0f}%)", (db.id, score))
                
            self.table.setCellWidget(row, 4, combo)
            self.comboboxes[bom.id] = combo
            
            # Confidence Label
            conf_item = QTableWidgetItem("0%")
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, conf_item)
            
            # Confirmed Checkbox
            cb = QCheckBox()
            cb_widget = QWidget()
            cb_lay = QHBoxLayout(cb_widget)
            cb_lay.addWidget(cb)
            cb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_lay.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 6, cb_widget)
            self.confirm_checkboxes[bom.id] = cb
            
            # Status badge
            status_item = QTableWidgetItem("Unmapped")
            status_item.setForeground(QColor("#dc3545"))
            self.table.setItem(row, 7, status_item)
            
            # Set combo connections to dynamically update confidence & status
            combo.currentIndexChanged.connect(
                lambda idx, bid=bom.id, row_idx=row: self._on_combo_changed(bid, row_idx)
            )
            
            # Set checkbox connections
            cb.stateChanged.connect(
                lambda state, bid=bom.id, row_idx=row: self._on_cb_changed(bid, row_idx)
            )
            
            # Pre-select mapped templates
            mapped = mapping_by_bom.get(bom.id)
            if mapped:
                # Find database template index in combobox
                for idx in range(1, combo.count()):
                    db_id, score = combo.itemData(idx)
                    if db_id == mapped.component_db_id:
                        combo.setCurrentIndex(idx)
                        break
                cb.setChecked(mapped.is_confirmed)
                
            self._update_row_status(bom.id, row)
            
        self._update_stats()
        
    def _on_combo_changed(self, bom_id: str, row_idx: int):
        self._update_row_status(bom_id, row_idx)
        self._update_stats()
        
    def _on_cb_changed(self, bom_id: str, row_idx: int):
        self._update_row_status(bom_id, row_idx)
        self._update_stats()
        
    def _update_row_status(self, bom_id: str, row_idx: int):
        combo = self.comboboxes[bom_id]
        cb = self.confirm_checkboxes[bom_id]
        
        data = combo.currentData()
        conf_item = self.table.item(row_idx, 5)
        status_item = self.table.item(row_idx, 7)
        
        if data is None:
            # Unmapped
            conf_item.setText("0%")
            status_item.setText("Unmapped")
            status_item.setForeground(QColor("#dc3545"))
            cb.setChecked(False)
            cb.setEnabled(False)
        else:
            db_id, score = data
            conf_item.setText(f"{score*100:.0f}%")
            cb.setEnabled(True)
            
            if cb.isChecked():
                status_item.setText("Confirmed")
                status_item.setForeground(QColor("#28a745"))
            else:
                status_item.setText("Suggested")
                status_item.setForeground(QColor("#ffc107"))
                
    def _update_stats(self):
        total = len(self.unit.bom_components)
        confirmed = 0
        suggested = 0
        unmapped = 0
        
        for bid, combo in self.comboboxes.items():
            cb = self.confirm_checkboxes[bid]
            if combo.currentData() is None:
                unmapped += 1
            elif cb.isChecked():
                confirmed += 1
            else:
                suggested += 1
                
        self.stats_label.setText(
            f"Summary: {total} total components. Confirmed: {confirmed}. Suggested: {suggested}. Unmapped: {unmapped}."
        )
        
    def _auto_match_all(self):
        for bid, combo in self.comboboxes.items():
            if combo.count() > 1:
                # Select the index 1 (highest scored suggestion)
                combo.setCurrentIndex(1)
                db_id, score = combo.currentData()
                cb = self.confirm_checkboxes[bid]
                # Auto-confirm matches >= 90%
                cb.setChecked(score >= 0.90)
                
        QMessageBox.information(self, "Auto-Match", "Auto-match completed! Review suggestions in yellow and save when ready.")
        
    def _confirm_all_suggested(self):
        confirmed_count = 0
        for bid, combo in self.comboboxes.items():
            if combo.currentData() is not None:
                cb = self.confirm_checkboxes[bid]
                if not cb.isChecked():
                    cb.setChecked(True)
                    confirmed_count += 1
        QMessageBox.information(self, "Confirmed", f"Confirmed {confirmed_count} suggested matches.")
        
    def _on_save(self):
        self.mappings.clear()
        
        for bom in self.unit.bom_components:
            combo = self.comboboxes[bom.id]
            cb = self.confirm_checkboxes[bom.id]
            
            data = combo.currentData()
            if data is not None:
                db_id, score = data
                self.mappings.append(ComponentMapping(
                    bom_component_id=bom.id,
                    component_db_id=db_id,
                    confidence=score,
                    is_confirmed=cb.isChecked()
                ))
                
        # Save to Unit model
        self.unit.component_mappings = self.mappings
        
        # Trigger FMEDA Row Generation
        self._generate_fmeda_rows()
        
        self.accept()
        
    def _generate_fmeda_rows(self):
        """
        Task 12 Extension: Generates FMEDA component mappings and populates project units.
        For confirmed mappings, we generate actual component failure records.
        """
        # Build mapping dictionary
        mapping_dict = {m.bom_component_id: m for m in self.mappings if m.is_confirmed}
        db_map = {t.id: t for t in self.db_templates}
        
        # Check conflicts
        conflicts = []
        for bom in self.unit.bom_components:
            mapping = mapping_dict.get(bom.id)
            if mapping:
                template = db_map.get(mapping.component_db_id)
                if template:
                    existing_comp = next((c for c in self.unit.components if c.position.upper() == bom.designator.upper()), None)
                    if existing_comp:
                        conflicts.append(bom.designator)
                        
        is_merge = True
        if conflicts:
            msg = QMessageBox(self)
            msg.setWindowTitle("Existing Components Conflict")
            msg.setText(
                f"The following components already exist in the workspace:\n"
                f"{', '.join(conflicts[:10])}{' and others' if len(conflicts) > 10 else ''}\n\n"
                f"How would you like to handle these existing components?"
            )
            
            merge_btn = msg.addButton("Merge All", QMessageBox.ButtonRole.YesRole)
            merge_btn.setToolTip("Update failure rates and failure modes from database template, but preserve all manual safety engineering assignments (deviations, mitigations, diagnostics).")
            
            overwrite_btn = msg.addButton("Overwrite All", QMessageBox.ButtonRole.NoRole)
            overwrite_btn.setToolTip("Completely replace existing components and discard all their manual safety engineering assignments.")
            
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
            
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == cancel_btn:
                # User cancelled saving mappings
                return
            is_merge = (clicked == merge_btn)
            
        new_components_list: List[Component] = []
        
        # Keep existing manual canvas components that are not bound to any BOM component
        bom_designators = {b.designator.upper() for b in self.unit.bom_components}
        for comp in self.unit.components:
            if comp.position.upper() not in bom_designators:
                new_components_list.append(comp)
                
        # Create/Update components based on confirmed mappings
        for bom in self.unit.bom_components:
            mapping = mapping_dict.get(bom.id)
            if mapping:
                template = db_map.get(mapping.component_db_id)
                if template:
                    existing_comp = next((c for c in self.unit.components if c.position.upper() == bom.designator.upper()), None)
                    
                    if existing_comp and is_merge:
                        # MERGE: Keep existing assignments, update fits/modes
                        existing_comp.name = template.display_name
                        existing_comp.type = template.material or "Unknown"
                        existing_comp.failure_rate = template.fits
                        existing_comp.failure_modes = template.failure_modes.copy()
                        existing_comp.part_number = bom.part_number
                        
                        # Sync failure mode assignments
                        updated_assignments = []
                        for fm_name, fm_percentage in template.failure_modes.items():
                            a = next((x for x in existing_comp.failure_mode_assignments if x.failure_mode_name == fm_name), None)
                            if a:
                                a.failure_rate_percentage = fm_percentage
                                updated_assignments.append(a)
                            else:
                                updated_assignments.append(FailureModeAssignment(
                                    failure_mode_name=fm_name,
                                    failure_rate_percentage=fm_percentage,
                                    classification="not_evaluated",
                                    dangerous_failure_percentage=100.0,
                                    detection_percentage=0.0
                                ))
                        existing_comp.failure_mode_assignments = updated_assignments
                        new_components_list.append(existing_comp)
                    else:
                        # OVERWRITE or NEW: Completely replace
                        import uuid
                        comp_id = f"comp_{uuid.uuid4().hex[:8]}"
                        
                        idx = len(new_components_list)
                        x_pos = 100 + (idx % 5) * 180
                        y_pos = 100 + (idx // 5) * 110
                        
                        # Default assignments
                        assignments = []
                        for fm_name, fm_percentage in template.failure_modes.items():
                            assignments.append(FailureModeAssignment(
                                failure_mode_name=fm_name,
                                failure_rate_percentage=fm_percentage,
                                classification="not_evaluated",
                                dangerous_failure_percentage=100.0,
                                detection_percentage=0.0
                            ))
                            
                        new_comp = Component(
                            id=comp_id,
                            position=bom.designator,
                            name=template.display_name,
                            type=template.material or "Unknown",
                            failure_rate=template.fits,
                            x_position=x_pos,
                            y_position=y_pos,
                            failure_modes=template.failure_modes.copy(),
                            failure_mode_assignments=assignments,
                            part_number=bom.part_number,
                            fitted_status="Fitted" if bom.is_fitted else "Not Fitted",
                            value=bom.value or None,
                            internal_pn=bom.part_number or None
                        )
                        new_components_list.append(new_comp)
            else:
                # If unconfirmed, keep existing component if present
                existing_comp = next((c for c in self.unit.components if c.position.upper() == bom.designator.upper()), None)
                if existing_comp:
                    new_components_list.append(existing_comp)
                    
        self.unit.components = new_components_list
        print(f"Generated/Updated {len(self.unit.components)} components from confirmed mappings.")
