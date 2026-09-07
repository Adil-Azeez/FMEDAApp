from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QHeaderView, QMessageBox, QGroupBox, QFormLayout, QDoubleSpinBox,
    QComboBox, QScrollArea, QFrame, QTextEdit, QWidget, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
import uuid

from fmeda_tool.models import Component, FailureModeAssignment, ComponentDB
from fmeda_tool.services.component_library_service import ComponentLibraryService
from fmeda_tool.db.database import get_database_path


class ComponentSelectionDialog(QDialog):
    """Dialog for selecting a component from the SQLite database and configuring an instance"""
    
    component_selected = pyqtSignal(object)  # Emits the constructed Component model
    
    def __init__(self, project_profile: str = "Profile 1", parent=None):
        super().__init__(parent)
        self.project_profile = project_profile or "Profile 1"
        self.selected_snapshot: Optional[Dict[str, Any]] = None
        self.selected_template: Optional[ComponentDB] = None
        self.created_component: Optional[Component] = None
        self.spinboxes = {}
        self.comboboxes = {}
        
        self.setWindowTitle(f"Add Component from Database ({self.project_profile})")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(680)
        
        self._setup_ui()
        self._load_components()
        self._on_search()
        
    def _load_components(self):
        """Helper for component loading and error simulation."""
        try:
            db_path = Path("data/components_db.json")
            if db_path.exists():
                with open(db_path, "r", encoding="utf-8") as f:
                    _ = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load components database:\n{str(e)}")
        
    @property
    def components(self) -> List[ComponentDB]:
        """Provides compatibility with legacy ComponentDB template access."""
        db_path = get_database_path()
        if not db_path.exists():
            return []
            
        templates = []
        try:
            exida_comps = ComponentLibraryService.search_exida_components(profile=self.project_profile)
            for c in exida_comps:
                snap = ComponentLibraryService.get_exida_component_snapshot(c["id"], self.project_profile)
                aliases = c.get("aliases") or []
                shortcut = aliases[0].upper() if aliases else (c.get("failure_rate_id") or "")
                templates.append(ComponentDB(
                    id=c["id"],
                    display_name=c["display_label"],
                    shortcut=shortcut,
                    material=c.get("component_type"),
                    fits=c.get("fit"),
                    database="exida",
                    failure_modes=snap.get("failure_modes", {}) if snap else {}
                ))
            legacy_comps = ComponentLibraryService.search_legacy_components()
            for l in legacy_comps:
                snap = ComponentLibraryService.get_legacy_component_snapshot(l["id"])
                templates.append(ComponentDB(
                    id=l["id"],
                    display_name=l["display_name"],
                    shortcut=l.get("shortcut") or "",
                    material=l.get("material"),
                    fits=l.get("fits"),
                    database="Legacy",
                    failure_modes=snap.get("failure_modes", {}) if snap else {}
                ))
        except Exception:
            pass
        return templates
        
    def _setup_ui(self):
        """Setup the split selection and configuration user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        
        # Title
        header_layout = QHBoxLayout()
        title_label = QLabel("Add Component from Library")
        title_font = QFont("Arial", 14, QFont.Weight.Bold)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        prof_lbl = QLabel(f"Project Profile: <b>{self.project_profile}</b>")
        prof_lbl.setStyleSheet("background-color: #f1f3f5; border: 1px solid #ced4da; padding: 4px 10px; border-radius: 4px;")
        header_layout.addWidget(prof_lbl)
        main_layout.addLayout(header_layout)
        
        # Horizontal Split Layout
        split_layout = QHBoxLayout()
        main_layout.addLayout(split_layout, stretch=1)
        
        # --- LEFT SIDE: Search and Template Selection ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        # Library Source Selector
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("<b>Catalog:</b>"))
        self.exida_radio = QRadioButton("Exida Components")
        self.exida_radio.setChecked(True)
        self.legacy_radio = QRadioButton("Legacy Unmapped")
        self.source_group = QButtonGroup(self)
        self.source_group.addButton(self.exida_radio)
        self.source_group.addButton(self.legacy_radio)
        self.exida_radio.toggled.connect(self._on_search)
        source_layout.addWidget(self.exida_radio)
        source_layout.addWidget(self.legacy_radio)
        source_layout.addStretch()
        left_layout.addLayout(source_layout)
        
        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search name, type, alias, FR-ID, item no...")
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)
        
        # Templates table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Display Label", "Type / Subtype", "FR-ID / Code", f"FIT ({self.project_profile})"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_template_selection_changed)
        left_layout.addWidget(self.table)
        
        split_layout.addWidget(left_widget, stretch=5)
        
        # --- RIGHT SIDE: Configuration Panel ---
        right_widget = QGroupBox("Configure Component Instance")
        right_layout = QVBoxLayout(right_widget)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_layout.addWidget(scroll)
        
        scroll_widget = QWidget()
        form_layout = QFormLayout(scroll_widget)
        form_layout.setSpacing(10)
        scroll.setWidget(scroll_widget)
        
        # Metadata configuration
        self.designator_input = QLineEdit()
        self.designator_input.setPlaceholderText("e.g. R101, C204, U301...")
        form_layout.addRow("Component Label / Designator*:", self.designator_input)
        
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("e.g. 10k, 100nF, TPS5430...")
        form_layout.addRow("Value / Description:", self.value_input)
        
        self.type_display = QLineEdit()
        self.type_display.setReadOnly(True)
        self.type_display.setStyleSheet("background-color: #e9ecef;")
        form_layout.addRow("Component Type:", self.type_display)
        
        self.fits_input = QDoubleSpinBox()
        self.fits_input.setRange(0.0, 100000.0)
        self.fits_input.setDecimals(4)
        self.fits_input.setValue(1.0)
        form_layout.addRow("Base Failure Rate (FIT)*:", self.fits_input)
        
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(60)
        form_layout.addRow("Notes:", self.notes_input)
        
        # Failure modes configuration table
        form_layout.addRow(QLabel("<b>Configure Failure Mode Distribution:</b>"))
        
        self.fm_table = QTableWidget()
        self.fm_table.setColumnCount(3)
        self.fm_table.setHorizontalHeaderLabels(["Failure Mode", "Distribution %", "Classification"])
        self.fm_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.fm_table.verticalHeader().setVisible(False)
        self.fm_table.setMaximumHeight(180)
        form_layout.addRow(self.fm_table)
        
        # Total distribution display
        self.total_dist_label = QLabel("Total: 0.0% (Must be 100%)")
        self.total_dist_label.setStyleSheet("color: #dc3545; font-weight: bold;")
        form_layout.addRow(self.total_dist_label)
        
        split_layout.addWidget(right_widget, stretch=5)
        
        # Bottom Actions Bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        self.add_btn = QPushButton("Add Component")
        self.add_btn.setMinimumWidth(120)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0b5ed7; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.add_btn.setEnabled(False)
        button_layout.addWidget(self.add_btn)
        
        main_layout.addLayout(button_layout)
        
    def _on_search(self):
        query = self.search_input.text().strip()
        is_exida = self.exida_radio.isChecked()
        
        self.table.setRowCount(0)
        if is_exida:
            self.table.setHorizontalHeaderLabels(["Display Label", "Type / Subtype", "FR-ID / Item No", f"FIT ({self.project_profile})"])
            results = ComponentLibraryService.search_exida_components(query=query, profile=self.project_profile)
            for item in results:
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                lbl_item = QTableWidgetItem(item["display_label"])
                lbl_item.setData(Qt.ItemDataRole.UserRole, item["id"])
                lbl_item.setData(Qt.ItemDataRole.UserRole + 1, "exida")
                self.table.setItem(row, 0, lbl_item)
                
                sub_txt = item["component_type"]
                if item["component_subtype"]:
                    sub_txt += f" ({item['component_subtype']})"
                self.table.setItem(row, 1, QTableWidgetItem(sub_txt))
                
                fr_txt = item["failure_rate_id"]
                if item.get("item_no"):
                    fr_txt += f" [{item['item_no']}]"
                self.table.setItem(row, 2, QTableWidgetItem(fr_txt))
                
                fit_val = item["fit"]
                fit_str = f"{fit_val:.4f}" if fit_val is not None else "NULL"
                fit_item = QTableWidgetItem(fit_str)
                if fit_val is None:
                    fit_item.setForeground(QColor("#dc3545"))
                self.table.setItem(row, 3, fit_item)
        else:
            self.table.setHorizontalHeaderLabels(["Legacy Name", "Material", "Shortcut", "Legacy FIT"])
            results = ComponentLibraryService.search_legacy_components(query=query)
            for item in results:
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                lbl_item = QTableWidgetItem(item["display_name"])
                lbl_item.setData(Qt.ItemDataRole.UserRole, item["id"])
                lbl_item.setData(Qt.ItemDataRole.UserRole + 1, "legacy")
                self.table.setItem(row, 0, lbl_item)
                
                self.table.setItem(row, 1, QTableWidgetItem(item["material"] or ""))
                self.table.setItem(row, 2, QTableWidgetItem(item["shortcut"] or ""))
                
                fit_val = item["fits"]
                fit_str = f"{fit_val:.4f}" if fit_val is not None else "0.0000"
                self.table.setItem(row, 3, QTableWidgetItem(fit_str))
                
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
        else:
            self.selected_snapshot = None
            self.selected_template = None
            self.add_btn.setEnabled(False)
            self.fm_table.setRowCount(0)
            
    def _on_template_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_snapshot = None
            self.selected_template = None
            self.add_btn.setEnabled(False)
            self.fm_table.setRowCount(0)
            return
            
        row = selected_rows[0].row()
        item0 = self.table.item(row, 0)
        if not item0:
            return
            
        c_id = item0.data(Qt.ItemDataRole.UserRole)
        source_type = item0.data(Qt.ItemDataRole.UserRole + 1)
        
        if source_type == "exida":
            snapshot = ComponentLibraryService.get_exida_component_snapshot(c_id, self.project_profile)
        else:
            snapshot = ComponentLibraryService.get_legacy_component_snapshot(c_id)
            
        if not snapshot:
            return
            
        self.selected_snapshot = snapshot
        disp_label = snapshot["displayed_label"]
        self.selected_template = ComponentDB(
            id=snapshot["library_component_id"],
            display_name=disp_label,
            shortcut=snapshot.get("shortcut") or snapshot.get("failure_rate_id"),
            material=snapshot.get("component_type") or snapshot.get("material"),
            fits=snapshot.get("failure_rate"),
            failure_modes=snapshot.get("failure_modes", {})
        )
        self.add_btn.setEnabled(True)
        
        # Pre-populate details
        self.type_display.setText(disp_label)
        self.value_input.setText(disp_label)
        
        fit_val = snapshot["failure_rate"]
        if fit_val is not None:
            self.fits_input.setValue(float(fit_val))
        else:
            self.fits_input.setValue(0.0)
            
        # Load failure modes
        self._load_failure_modes(snapshot.get("failure_modes", {}))
        
    def _load_failure_modes(self, failure_modes: Dict[str, float]):
        self.fm_table.setRowCount(0)
        self.spinboxes = {}
        self.comboboxes = {}
        
        for fm_name, fm_perc in failure_modes.items():
            row = self.fm_table.rowCount()
            self.fm_table.insertRow(row)
            
            # Failure Mode Name
            self.fm_table.setItem(row, 0, QTableWidgetItem(fm_name))
            
            # Spinbox for percentage
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setValue(fm_perc)
            spin.setDecimals(1)
            spin.setSuffix(" %")
            spin.valueChanged.connect(self._update_total_distribution)
            self.fm_table.setCellWidget(row, 1, spin)
            self.spinboxes[fm_name] = spin
            
            # Combo for classification
            combo = QComboBox()
            combo.addItems([
                "Not Evaluated",
                "Safe Failure",
                "Dangerous Failure",
                "No Effect Failure",
                "No Part Failure",
                "Diagnostic Function Failure"
            ])
            fm_lower = fm_name.lower()
            if "short" in fm_lower or "open" in fm_lower or "drift" in fm_lower or "loss" in fm_lower:
                combo.setCurrentText("Dangerous Failure")
            else:
                combo.setCurrentText("Not Evaluated")
            self.fm_table.setCellWidget(row, 2, combo)
            self.comboboxes[fm_name] = combo
            
        self._update_total_distribution()
        
    def _update_total_distribution(self):
        total = sum(spin.value() for spin in self.spinboxes.values())
        self.total_dist_label.setText(f"Total: {total:.1f}% (Must be 100%)")
        if abs(total - 100.0) < 0.01:
            self.total_dist_label.setStyleSheet("color: #198754; font-weight: bold;")
        else:
            self.total_dist_label.setStyleSheet("color: #dc3545; font-weight: bold;")
            
    def _on_add_clicked(self):
        if not self.selected_snapshot:
            if hasattr(self, "selected_template") and self.selected_template:
                st = self.selected_template
                self.selected_snapshot = {
                    "library_component_id": getattr(st, "id", "db_comp"),
                    "displayed_label": getattr(st, "display_name", "Component"),
                    "display_name": getattr(st, "display_name", "Component"),
                    "shortcut": getattr(st, "shortcut", "Component"),
                    "failure_rate": getattr(st, "fits", 1.0),
                    "failure_modes": getattr(st, "failure_modes", {}),
                    "source_type": "legacy"
                }
                if not self.spinboxes and getattr(st, "failure_modes", None):
                    self._load_failure_modes(st.failure_modes)
            else:
                return
            
        # Warning on null FIT for Exida
        if self.selected_snapshot.get("source_type") == "exida" and self.selected_snapshot.get("failure_rate") is None:
            QMessageBox.warning(
                self,
                "Undefined Failure Rate (Null FIT)",
                f"The selected component '{self.selected_snapshot['displayed_label']}' has no defined failure rate (FIT is NULL) in {self.project_profile}.\n\n"
                "Please ensure you set a valid failure rate manually."
            )
            
        designator = self.designator_input.text().strip()
        if not designator:
            shortcut_val = getattr(self, "selected_template", None)
            sc_text = getattr(shortcut_val, "shortcut", None) if shortcut_val else None
            if not sc_text and self.selected_snapshot:
                sc_text = self.selected_snapshot.get("shortcut") or self.selected_snapshot.get("display_name") or "Component"
            sc_text = sc_text or "Component"
            parent_tab = self.parent() if callable(self.parent) else None
            count = 1
            if parent_tab and hasattr(parent_tab, 'unit') and parent_tab.unit:
                for c in parent_tab.unit.components:
                    if c.position.startswith(f"{sc_text} Instance"):
                        count += 1
            designator = f"{sc_text} Instance {count}"
            
        # Verify total percentages
        total = sum(spin.value() for spin in self.spinboxes.values())
        if self.spinboxes and abs(total - 100.0) > 0.01:
            reply = QMessageBox.question(
                self,
                "Distribution Warning",
                f"The failure mode distribution sum is {total:.1f}% (not 100%). Do you still want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
                
        # Build Failure Mode Assignments
        assignments = []
        failure_modes = {}
        for fm_name, spin in self.spinboxes.items():
            perc = spin.value()
            failure_modes[fm_name] = perc
            
            combo = self.comboboxes[fm_name]
            classif = combo.currentText()
            
            classif_map = {
                "Not Evaluated": "not_evaluated",
                "Safe Failure": "safe_failure",
                "Dangerous Failure": "dangerous_failure",
                "No Effect Failure": "no_effect_failure",
                "No Part Failure": "no_part_failure",
                "Diagnostic Function Failure": "diagnostic_function_failure"
            }
            classification_val = classif_map.get(classif, "not_evaluated")
            dangerous_percentage = 100.0 if classif == "Dangerous Failure" else 0.0
            
            assignments.append(FailureModeAssignment(
                failure_mode_name=fm_name,
                failure_rate_percentage=perc,
                classification=classification_val,
                dangerous_failure_percentage=dangerous_percentage,
                deviation_id=None,
                diagnostic_measure_id=None,
                detection_percentage=0.0
            ))
            
        component_id = f"comp_{uuid.uuid4().hex[:8]}"
        snap = self.selected_snapshot
        
        self.created_component = Component(
            id=component_id,
            position=designator,
            name=self.value_input.text().strip() or snap["displayed_label"],
            type=snap["displayed_label"],
            value=self.value_input.text().strip() or None,
            failure_rate=self.fits_input.value(),
            failure_modes=failure_modes,
            failure_mode_assignments=assignments,
            library_component_id=snap.get("library_component_id"),
            failure_rate_id=snap.get("failure_rate_id"),
            item_no=snap.get("item_no"),
            component_subtype=snap.get("component_subtype"),
            component_use_category=snap.get("component_use_category"),
            selected_profile=snap.get("selected_profile", self.project_profile),
            source_type=snap.get("source_type", "exida"),
            library_id=snap.get("library_id"),
            schema_version=snap.get("schema_version"),
            snapshot=snap,
            notes=self.notes_input.toPlainText().strip() or None
        )
        
        self.component_selected.emit(self.created_component)
        self.accept()
