from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QCheckBox, QFrame, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from typing import List, Optional
from pathlib import Path

from fmeda_tool.models import BOMComponent
from fmeda_tool.services import ImportService


class BOMImportDialog(QDialog):
    """Dialog to import and preview BOM components from a CSV file"""
    
    def __init__(self, existing_designators: Optional[List[str]] = None, filepath: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import BOM CSV")
        self.setMinimumSize(950, 600)
        self.resize(1000, 650)
        
        self.existing_designators = existing_designators or []
        self.imported_components: List[BOMComponent] = []
        self.all_parsed_components: List[BOMComponent] = []
        self.row_checkboxes: List[QCheckBox] = []
        
        self._setup_ui()
        
        if filepath:
            self.file_path_input.setText(filepath)
            self._load_file(filepath)
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # File selector row
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("BOM CSV File:"))
        self.file_path_input = QLineEdit()
        self.file_path_input.setReadOnly(True)
        file_layout.addWidget(self.file_path_input)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)
        
        # Control Actions Row
        actions_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        actions_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self._deselect_all)
        actions_layout.addWidget(deselect_all_btn)
        
        exclude_unfitted_btn = QPushButton("Exclude Unfitted")
        exclude_unfitted_btn.clicked.connect(self._exclude_unfitted)
        actions_layout.addWidget(exclude_unfitted_btn)
        
        actions_layout.addStretch()
        layout.addLayout(actions_layout)
        
        # Preview Table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Import", "Designator", "Part Number", "Description",
            "Value", "Package", "Layer", "Fitted", "Status"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        
        # Connect itemChanged to handle inline editing/correction of fitted status
        self.table.itemChanged.connect(self._on_item_changed)
        
        # Validation Indicator Bar
        self.indicator_frame = QFrame()
        self.indicator_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.indicator_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;")
        
        indicator_layout = QHBoxLayout(self.indicator_frame)
        self.status_indicator = QLabel("No file loaded. Please browse and select a BOM CSV file.")
        self.status_indicator.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        indicator_layout.addWidget(self.status_indicator)
        layout.addWidget(self.indicator_frame)
        
        # Dialog button box
        btns_layout = QHBoxLayout()
        btns_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btns_layout.addWidget(self.cancel_btn)
        
        self.confirm_btn = QPushButton("Confirm Import")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 6px 16px;")
        self.confirm_btn.clicked.connect(self._on_confirm)
        btns_layout.addWidget(self.confirm_btn)
        
        layout.addLayout(btns_layout)
        
    def _on_browse(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open BOM CSV File", "", "CSV Files (*.csv);;All Files (*.*)"
        )
        if not filepath:
            return
            
        self.file_path_input.setText(filepath)
        self._load_file(filepath)
        
    def _load_file(self, filepath: str):
        try:
            try:
                # Open with utf-8-sig to automatically handle standard UTF-8 and UTF-8 with BOM
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
            except UnicodeDecodeError as ude:
                QMessageBox.critical(
                    self, "Load Error", 
                    f"Unreadable encoding: The file is not a valid UTF-8 text file.\n{str(ude)}"
                )
                self._update_indicator(0, 1, 0, failed=True)
                return
                
            parsed, errors, warnings = ImportService.parse_bom_csv(content, self.existing_designators, filepath)
            
            if errors:
                QMessageBox.critical(self, "Import Errors", "\n".join(errors))
                self._update_indicator(len(parsed), len(errors), len(warnings), failed=True)
                self.confirm_btn.setEnabled(False)
                return
                
            self.all_parsed_components = parsed
            self.row_checkboxes.clear()
            
            # Disable signals while populating
            self.table.blockSignals(True)
            self.table.setRowCount(0)
            
            # Detect delimiter name
            first_line = content.splitlines()[0] if content.splitlines() else ""
            delim_name = "semicolon (;)" if ";" in first_line and "," not in first_line else "comma (,)"
            
            # Map of uppercase designator to warnings list
            warning_map = {}
            for w in warnings:
                for comp in parsed:
                    if f"'{comp.designator.upper()}'" in w.upper() or f" '{comp.designator.upper()}'" in w.upper() or f"Row {comp.row_number}:" in w:
                        if comp.designator.upper() not in warning_map:
                            warning_map[comp.designator.upper()] = []
                        warning_map[comp.designator.upper()].append(w)
            
            for comp in parsed:
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                # Checkbox for import selection
                cb = QCheckBox()
                cb.setChecked(True)
                self.row_checkboxes.append(cb)
                
                widget = QWidget()
                lay = QHBoxLayout(widget)
                lay.addWidget(cb)
                lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(row, 0, widget)
                
                # Fields
                self.table.setItem(row, 1, QTableWidgetItem(comp.designator))
                self.table.setItem(row, 2, QTableWidgetItem(comp.part_number))
                self.table.setItem(row, 3, QTableWidgetItem(comp.description or ""))
                self.table.setItem(row, 4, QTableWidgetItem(comp.value or ""))
                # Package is optional / blank in CSV canonical
                self.table.setItem(row, 5, QTableWidgetItem(comp.package or ""))
                self.table.setItem(row, 6, QTableWidgetItem(comp.layer or ""))
                
                # Fitted flag (editable)
                fitted_item = QTableWidgetItem("Yes" if comp.is_fitted else "No")
                fitted_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 7, fitted_item)
                
                # Status column
                status_item = QTableWidgetItem("Valid")
                status_item.setForeground(QColor("#28a745"))
                
                # Apply warnings
                warn_list = warning_map.get(comp.designator.upper())
                if warn_list:
                    status_item.setText("Warning")
                    status_item.setForeground(QColor("#fd7e14"))
                    status_item.setToolTip("\n".join(warn_list))
                    # Color rows with warnings
                    for col in range(1, 8):
                        item = self.table.item(row, col)
                        if item:
                            item.setBackground(QColor("#fff3cd"))
                            
                self.table.setItem(row, 8, status_item)
                
            self.table.blockSignals(False)
            
            self.confirm_btn.setEnabled(len(parsed) > 0)
            self._update_indicator(len(parsed), 0, len(warnings), delim_name=delim_name)
            
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load BOM CSV file:\n{str(e)}")
            self.confirm_btn.setEnabled(False)
            
    def _update_indicator(self, parsed_count: int, error_count: int, warning_count: int, failed: bool = False, delim_name: str = ""):
        if failed:
            self.indicator_frame.setStyleSheet("background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px;")
            self.status_indicator.setText("Failed to parse BOM CSV file due to schema errors.")
            self.status_indicator.setStyleSheet("color: #721c24;")
            return
            
        delim_str = f" [Delimiter: {delim_name}]" if delim_name else ""
        if warning_count > 0:
            self.indicator_frame.setStyleSheet("background-color: #fff3cd; border: 1px solid #ffeeba; border-radius: 4px;")
            self.status_indicator.setText(f"Successfully loaded {parsed_count} components{delim_str}. Warnings identified: {warning_count} (Hover status cell for details).")
            self.status_indicator.setStyleSheet("color: #856404;")
        else:
            self.indicator_frame.setStyleSheet("background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px;")
            self.status_indicator.setText(f"Successfully loaded {parsed_count} components{delim_str}. Schema validation is completely clean!")
            self.status_indicator.setStyleSheet("color: #155724;")
            
    def _select_all(self):
        for cb in self.row_checkboxes:
            cb.setChecked(True)
            
    def _deselect_all(self):
        for cb in self.row_checkboxes:
            cb.setChecked(False)
            
    def _exclude_unfitted(self):
        for i, comp in enumerate(self.all_parsed_components):
            if not comp.is_fitted:
                if i < len(self.row_checkboxes):
                    self.row_checkboxes[i].setChecked(False)
                    
    def _on_item_changed(self, item):
        if item.column() == 7:  # Fitted column
            row = item.row()
            if row < len(self.all_parsed_components):
                comp = self.all_parsed_components[row]
                text = item.text().strip().lower()
                true_options = ["true", "yes", "1", "fitted", "bestückt", "bestueckt"]
                false_options = ["false", "no", "0", "not fitted", "not_fitted", "nicht bestückt", "nicht bestueckt", "dnp", "do not populate"]
                
                if text in true_options:
                    comp.is_fitted = True
                    self.table.blockSignals(True)
                    item.setText("Yes")
                    self.table.blockSignals(False)
                elif text in false_options:
                    comp.is_fitted = False
                    self.table.blockSignals(True)
                    item.setText("No")
                    self.table.blockSignals(False)
                else:
                    QMessageBox.warning(
                        self, "Invalid Fitted Value", 
                        "Please enter a valid fitted value (e.g. Yes, No, True, False, Fitted, DNP)."
                    )
                    self.table.blockSignals(True)
                    item.setText("Yes" if comp.is_fitted else "No")
                    self.table.blockSignals(False)
                    
    def _on_confirm(self):
        self.imported_components.clear()
        for i, cb in enumerate(self.row_checkboxes):
            if cb.isChecked():
                self.imported_components.append(self.all_parsed_components[i])
                
        if not self.imported_components:
            QMessageBox.warning(self, "No Components Selected", "Please select at least one component to import.")
            return
            
        self.accept()
