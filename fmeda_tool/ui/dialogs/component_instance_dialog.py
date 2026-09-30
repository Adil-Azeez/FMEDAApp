

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QHeaderView, QWidget, QDoubleSpinBox, QMessageBox, QTextEdit, QFormLayout, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, List

from fmeda_tool.models import (
    Component, FailureModeAssignment, Deviation, DiagnosticMeasure, Project
)


class ComponentInstanceDialog(QDialog):
    """Dialog for editing a component instance with failure mode assignments"""
    
    component_updated = pyqtSignal(Component)
    secondary_failure_requested = pyqtSignal(str)  # Failure mode name for secondary failure selection
    
    def __init__(self, component: Component, project: Project, parent=None, allow_distribution=False):
        super().__init__(parent)
        self.component = component
        self.project = project
        self.allow_distribution = allow_distribution
        self.distribution_unlocked = False
        self.failure_mode_rows = {}  # Map failure mode name to row index
        
        self.setWindowTitle(f"Edit Component: {component.name}")
        self.setMinimumWidth(625)
        self.setMinimumHeight(320)
        self.resize(625, 320)
        
        # Set window flags for floating dialog
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Component info section
        self._create_component_info(layout)
        
        # Failure modes table
        self._create_failure_modes_table(layout)
        
        # Buttons
        self._create_buttons(layout)
    
    def _create_component_info(self, parent_layout):
        """Create component information section"""
        info_widget = QWidget()
        info_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        info_layout = QVBoxLayout(info_widget)
        
        # Title
        title_label = QLabel("Component Information")
        title_font = QFont()
        title_font.setPointSize(9)
        title_font.setBold(True)
        title_label.setFont(title_font)
        info_layout.addWidget(title_label)
        
        # Name and shortcut
        name_layout = QHBoxLayout()
        
        name_lbl = QLabel("Name:")
        name_lbl.setStyleSheet("font-size: 8pt;")
        name_layout.addWidget(name_lbl)
        self.name_label = QLabel(self.component.name)
        self.name_label.setStyleSheet("font-weight: bold; color: #212529; font-size: 8pt;")
        name_layout.addWidget(self.name_label)
        name_layout.addStretch()
        
        shortcut_lbl = QLabel("Shortcut:")
        shortcut_lbl.setStyleSheet("font-size: 8pt;")
        name_layout.addWidget(shortcut_lbl)
        self.shortcut_label = QLabel(self.component.position)
        self.shortcut_label.setStyleSheet("font-weight: bold; color: #495057; font-size: 8pt;")
        name_layout.addWidget(self.shortcut_label)
        name_layout.addStretch()
        
        info_layout.addLayout(name_layout)
        
        parent_layout.addWidget(info_widget)
    
    def _create_failure_modes_table(self, parent_layout):
        """Create failure modes configuration table"""
        # Section title
        title_label = QLabel("Failure Modes Configuration")
        title_font = QFont()
        title_font.setPointSize(9)
        title_font.setBold(True)
        title_label.setFont(title_font)
        parent_layout.addWidget(title_label)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(16)
        self.table.setHorizontalHeaderLabels([
            "Failure Mode",
            "Rate %",
            "Deviation",
            "Diagnostic Measure",
            "Detection %",
            "Dangerous %",
            "Classification", "Review Status", "Proof-test A %", "Proof-test B %",
            "Proof-test C %", "Diagnostic Function", "Mitigation", "No Part / No Effect",
            "Notes", "DC Test Reference"
        ])
        
        # Style the table
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                gridline-color: #dee2e6;
                font-size: 8pt;
            }
            QTableWidget::item {
                padding: 2px;
                border-bottom: 1px solid #f1f3f5;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 4px 4px;
                border: none;
                border-bottom: 2px solid #dee2e6;
                border-right: 1px solid #dee2e6;
                font-weight: bold;
                font-size: 8pt;
                color: #495057;
            }
        """)
        
        # Set vertical header (row numbers) width smaller
        self.table.verticalHeader().setDefaultSectionSize(20)
        
        # Set column widths - enable independent column resizing
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.table.setColumnWidth(0, 150)  # Failure Mode
        self.table.setColumnWidth(1, 50)   # Rate %
        self.table.setColumnWidth(2, 100)  # Deviation
        self.table.setColumnWidth(3, 100)  # Diagnostic
        self.table.setColumnWidth(4, 70)   # Detection %
        self.table.setColumnWidth(5, 75)   # Dangerous %
        self.table.setColumnWidth(6, 120)  # Classification
        
        # Enable horizontal scrollbar if columns exceed table width
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        parent_layout.addWidget(self.table)
    
    def _create_buttons(self, parent_layout):
        """Create dialog buttons"""
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(70)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setMinimumWidth(70)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
        """)
        save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(save_btn)
        
        parent_layout.addLayout(button_layout)
    
    # Column bindings retain every existing assignment field, including hidden legacy data.
    ENGINEERING_FIELDS = (
        "deviation_id", "diagnostic_measure_id", "detection_percentage",
        "dangerous_failure_percentage", "classification", "review_status",
        "proof_test_a", "proof_test_b", "proof_test_c", "diagnostic_function",
        "mitigation_id", "dont_care", "notes", "dc_test_ref",
    )

    def _load_data(self):
        self.table.setRowCount(0)
        assignments = {a.failure_mode_name: a for a in self.component.failure_mode_assignments}
        for name, pct in self.component.failure_modes.items():
            self._add_row(name, pct, assignments.get(name))
        self.table.itemChanged.connect(self._update_total)
        self.distribution_button = QPushButton("Edit Failure-Mode Distribution")
        self.distribution_button.setVisible(self.allow_distribution)
        self.distribution_button.clicked.connect(self._unlock_distribution)
        self.layout().insertWidget(3, self.distribution_button)
        self.distribution_controls = QWidget()
        controls = QHBoxLayout(self.distribution_controls)
        self.add_mode_button = QPushButton("Add Failure Mode")
        self.remove_mode_button = QPushButton("Remove Failure Mode")
        self.total_label = QLabel()
        self.add_mode_button.clicked.connect(lambda: self._add_row("", 0.0))
        self.remove_mode_button.clicked.connect(self._remove_mode)
        controls.addWidget(self.add_mode_button)
        controls.addWidget(self.remove_mode_button)
        controls.addWidget(self.total_label)
        self.layout().insertWidget(4, self.distribution_controls)
        self.distribution_controls.hide()
        self.custom_fields = QWidget()
        form = QFormLayout(self.custom_fields)
        snapshot = self.component.snapshot or {}
        self.type_input = QLineEdit(snapshot.get("component_type") or self.component.type)
        self.description_input = QTextEdit()
        self.description_input.setAcceptRichText(False)
        self.description_input.setMaximumHeight(65)
        self.description_input.setPlainText(snapshot.get("description") or "")
        self.display_name_input = QLineEdit()
        form.addRow("Component Type *", self.type_input)
        form.addRow("Description *", self.description_input)
        form.addRow("Display Name (optional, unique)", self.display_name_input)
        self.layout().insertWidget(5, self.custom_fields)
        self.custom_fields.hide()
        self._update_total()

    def _choices(self, field):
        if field == "deviation_id":
            return [("-- None --", None)] + [(d.name, d.id) for d in self.project.deviations]
        if field == "diagnostic_measure_id":
            return [("-- None --", None)] + [(d.description, d.id) for d in self.project.diagnostic_measures]
        if field == "mitigation_id":
            return [("-- None --", None)] + [(m.name or m.id, m.id) for m in self.project.mitigations]
        if field == "classification":
            return [("Not Evaluated", "not_evaluated"), ("Safe Failure", "safe_failure"), ("Dangerous Failure", "dangerous_failure")]
        if field == "review_status":
            return [("Draft", "draft"), ("Under Review", "under_review"), ("Approved", "approved")]
        if field == "diagnostic_function":
            return [("", None), ("Yes", "Yes"), ("No", "No")]
        return None

    def _add_row(self, name, percentage, assignment=None):
        row = self.table.rowCount()
        self.table.insertRow(row)
        assignment = assignment.model_copy(deep=True) if assignment else FailureModeAssignment(
            failure_mode_name=name, failure_rate_percentage=percentage)
        for col, text in enumerate((name, str(percentage))):
            item = QTableWidgetItem(text)
            if not self.distribution_unlocked:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, item)
        self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, assignment)
        self.failure_mode_rows[name] = row
        for col, field in enumerate(self.ENGINEERING_FIELDS, 2):
            value = getattr(assignment, field)
            choices = self._choices(field)
            if choices is not None:
                widget = QComboBox()
                for label, data in choices:
                    widget.addItem(label, data)
                index = widget.findData(value)
                if index < 0:
                    widget.addItem(str(value or ""), value)
                    index = widget.count() - 1
                widget.setCurrentIndex(index)
            elif field == "dont_care":
                widget = QCheckBox()
                widget.setChecked(bool(value))
            elif field in ("notes", "dc_test_ref"):
                widget = QLineEdit(value or "")
            else:
                widget = QDoubleSpinBox()
                widget.setRange(0, 100)
                widget.setDecimals(6)
                widget.setValue(value or 0.0)
                widget.setSuffix("%")
            widget.setProperty("originalValue", self._widget_value(widget))
            self.table.setCellWidget(row, col, widget)
        self._update_total()

    @staticmethod
    def _widget_value(widget):
        if isinstance(widget, QComboBox):
            return widget.currentData()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QLineEdit):
            return widget.text()
        return widget.value()

    def _unlock_distribution(self):
        if not self.allow_distribution or self.distribution_unlocked:
            return
        warning = QMessageBox(self)
        warning.setWindowTitle("Edit Failure-Mode Distribution")
        warning.setIcon(QMessageBox.Icon.Warning)
        warning.setText("Changing the failure-mode names or distribution creates a modified reliability model. "
                        "The original library component will not be changed. Do you want to continue?")
        proceed = warning.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
        cancel = warning.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        warning.setDefaultButton(cancel)
        warning.exec()
        if warning.clickedButton() != proceed:
            return
        if not self.description_input.toPlainText().strip() and self.component.library_component_id:
            from fmeda_tool.services.component_library_service import ComponentLibraryService
            if self.component.source_type == "custom":
                source = ComponentLibraryService.get_custom_component_snapshot(self.component.library_component_id)
            elif self.component.source_type == "legacy":
                source = ComponentLibraryService.get_legacy_component_snapshot(self.component.library_component_id)
            else:
                source = ComponentLibraryService.get_exida_component_snapshot(
                    self.component.library_component_id, self.component.selected_profile or self.project.selected_profile)
            if source:
                self.description_input.setPlainText(source.get("description") or "")
        self.distribution_unlocked = True
        for row in range(self.table.rowCount()):
            for col in (0, 1):
                item = self.table.item(row, col)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.distribution_button.setEnabled(False)
        self.distribution_controls.show()
        self.custom_fields.show()

    def _remove_mode(self):
        if self.distribution_unlocked and self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())
            self._update_total()

    def _update_total(self, *_):
        if not hasattr(self, "total_label"):
            return
        try:
            total = sum(float(self.table.item(r, 1).text()) for r in range(self.table.rowCount()))
            self.total_label.setText(f"Total: {total:.1f}%")
        except (ValueError, AttributeError):
            self.total_label.setText("Total: N/A")

    def _on_save(self):
        from fmeda_tool.services.component_library_service import ComponentLibraryService
        from math import isfinite
        try:
            modes, assignments = {}, []
            for row in range(self.table.rowCount()):
                name = self.table.item(row, 0).text().strip()
                pct = float(self.table.item(row, 1).text())
                if not name or name in modes:
                    raise ValueError("Failure mode names must be non-empty and unique.")
                if not isfinite(pct) or pct < 0 or pct > 100:
                    raise ValueError("Each Rate % must be between 0 and 100.")
                modes[name] = pct
                original = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                data = original.model_dump()
                data.update(failure_mode_name=name, failure_rate_percentage=pct)
                for col, field in enumerate(self.ENGINEERING_FIELDS, 2):
                    widget = self.table.cellWidget(row, col)
                    value = self._widget_value(widget)
                    if value != widget.property("originalValue"):
                        data[field] = value
                assignments.append(FailureModeAssignment.model_validate(data))
            changed = modes != self.component.failure_modes
            snapshot = None
            if changed:
                if not self.distribution_unlocked:
                    raise ValueError("Unlock failure-mode distribution editing first.")
                # Always copy: updating a shared Custom record could change other projects.
                # The selected instance alone receives the new independent library reference.
                ok, message, snapshot = ComponentLibraryService.create_custom_component(
                    component_type=self.type_input.text(), description=self.description_input.toPlainText(),
                    fits=self.component.failure_rate, failure_modes=modes,
                    display_name=self.display_name_input.text(),
                    copied_from_source_type=self.component.source_type,
                    copied_from_component_id=self.component.library_component_id,
                    copied_from_failure_rate_id=self.component.failure_rate_id,
                    user=self.project.created_by or "System")
                if not ok:
                    raise ValueError(message)
                snapshot["selected_profile"] = self.component.selected_profile or self.project.selected_profile
            self.component.failure_modes = modes
            self.component.failure_mode_assignments = assignments
            if snapshot:
                self.component.snapshot = snapshot
                self.component.library_component_id = snapshot["library_component_id"]
                self.component.source_type = "custom"
                self.component.type = snapshot["component_type"]
                self.component.failure_rate_id = None
                self.component.item_no = None
                self.component.library_id = None
                self.component.schema_version = None
                self.component.selected_profile = snapshot["selected_profile"]
            self.component_updated.emit(self.component)
            self.accept()
        except (ValueError, TypeError) as error:
            QMessageBox.warning(self, "Component validation", str(error))
