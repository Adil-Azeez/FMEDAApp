

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QDoubleSpinBox, QPushButton, QLabel, QMessageBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional
import uuid
from datetime import datetime

from fmeda_tool.models import ComponentDB


class ComponentDBDialog(QDialog):
    """Dialog for creating/editing components in the database"""
    
    component_saved = pyqtSignal(ComponentDB)
    
    def __init__(self, parent=None, component: Optional[ComponentDB] = None):
        super().__init__(parent)
        self.component = component
        self.edit_mode = component is not None
        
        self.setWindowTitle("Edit Component" if self.edit_mode else "Add Component to Database")
        self.setMinimumWidth(700)
        self.setMinimumHeight(700)
        
        self._setup_ui()
        
        if self.edit_mode and component:
            self._load_component(component)
    
    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Title
        title_label = QLabel("Edit Component" if self.edit_mode else "Add New Component to Database")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Basic Information Group
        basic_group = QGroupBox("Component Information")
        basic_layout = QFormLayout()
        basic_layout.setSpacing(10)
        
        # Display Name (required)
        self.display_name_input = QLineEdit()
        self.display_name_input.setPlaceholderText("e.g., Ceramic Capacitor 100nF")
        basic_layout.addRow("Display Name*:", self.display_name_input)
        
        # Shortcut
        self.shortcut_input = QLineEdit()
        self.shortcut_input.setPlaceholderText("e.g., C100N")
        basic_layout.addRow("Shortcut:", self.shortcut_input)
        
        # Material
        self.material_input = QLineEdit()
        self.material_input.setPlaceholderText("e.g., Ceramic X7R, Silicon, Aluminum")
        basic_layout.addRow("Material:", self.material_input)
        
        # FITS
        self.fits_input = QDoubleSpinBox()
        self.fits_input.setRange(0, 999999)
        self.fits_input.setDecimals(4)
        self.fits_input.setSuffix(" FIT")
        self.fits_input.setSpecialValueText("Not set")
        basic_layout.addRow("FITS (λ):", self.fits_input)
        
        # Database
        self.database_input = QLineEdit()
        self.database_input.setPlaceholderText("e.g., MIL-HDBK-217F, IEC 61709")
        basic_layout.addRow("Database:", self.database_input)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # Failure Modes Group
        failure_modes_group = QGroupBox("Failure Modes")
        failure_modes_layout = QVBoxLayout()
        
        # Header with Add button
        header_layout = QHBoxLayout()
        header_label = QLabel("Define failure modes and their percentage of overall FITS:")
        header_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        add_failure_mode_btn = QPushButton("+ Add Failure Mode")
        add_failure_mode_btn.setStyleSheet("""
            QPushButton {
                background-color: #198754;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #157347;
            }
        """)
        add_failure_mode_btn.clicked.connect(self._add_failure_mode_row)
        header_layout.addWidget(add_failure_mode_btn)
        
        failure_modes_layout.addLayout(header_layout)
        
        # Failure modes table
        self.failure_modes_table = QTableWidget()
        self.failure_modes_table.setColumnCount(3)
        self.failure_modes_table.setHorizontalHeaderLabels([
            "Failure Mode", "% of FITS", "Actions"
        ])
        
        self.failure_modes_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #dee2e6;
                font-weight: bold;
            }
        """)
        
        # Enable independent column resizing
        self.failure_modes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.failure_modes_table.setColumnWidth(0, 200)  # Failure Mode
        self.failure_modes_table.setColumnWidth(1, 120)  # % of FITS
        self.failure_modes_table.setColumnWidth(2, 100)  # Actions
        self.failure_modes_table.verticalHeader().setVisible(False)
        
        # Enable horizontal scrollbar if columns exceed table width
        self.failure_modes_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        failure_modes_layout.addWidget(self.failure_modes_table)
        
        failure_modes_group.setLayout(failure_modes_layout)
        layout.addWidget(failure_modes_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save" if self.edit_mode else "Add to Database")
        save_btn.setMinimumWidth(120)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
        """)
        save_btn.clicked.connect(self._save_component)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
    
    def _add_failure_mode_row(self):
        """Add a new row to the failure modes table"""
        row = self.failure_modes_table.rowCount()
        self.failure_modes_table.insertRow(row)
        
        # Failure mode name (editable)
        name_item = QTableWidgetItem("")
        self.failure_modes_table.setItem(row, 0, name_item)
        
        # Percentage (editable)
        percentage_item = QTableWidgetItem("0.0")
        self.failure_modes_table.setItem(row, 1, percentage_item)
        
        # Delete button
        delete_btn = QPushButton("Delete")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        delete_btn.clicked.connect(lambda: self._delete_failure_mode_row(row))
        self.failure_modes_table.setCellWidget(row, 2, delete_btn)
    
    def _delete_failure_mode_row(self, row: int):
        """Delete a row from the failure modes table"""
        self.failure_modes_table.removeRow(row)
    
    def _load_component(self, component: ComponentDB):
        """Load component data into form"""
        self.display_name_input.setText(component.display_name)
        
        if component.shortcut:
            self.shortcut_input.setText(component.shortcut)
        
        if component.material:
            self.material_input.setText(component.material)
        
        if component.fits is not None:
            self.fits_input.setValue(component.fits)
        
        if component.database:
            self.database_input.setText(component.database)
        
        # Load failure modes
        for failure_mode, percentage in component.failure_modes.items():
            row = self.failure_modes_table.rowCount()
            self.failure_modes_table.insertRow(row)
            
            name_item = QTableWidgetItem(failure_mode)
            self.failure_modes_table.setItem(row, 0, name_item)
            
            percentage_item = QTableWidgetItem(str(percentage))
            self.failure_modes_table.setItem(row, 1, percentage_item)
            
            delete_btn = QPushButton("Delete")
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #c82333;
                }
            """)
            delete_btn.clicked.connect(lambda checked, r=row: self._delete_failure_mode_row(r))
            self.failure_modes_table.setCellWidget(row, 2, delete_btn)
    
    def _save_component(self):
        """Validate and save the component"""
        # Validate required fields
        display_name = self.display_name_input.text().strip()
        
        if not display_name:
            QMessageBox.warning(self, "Validation Error", "Display Name is required.")
            self.display_name_input.setFocus()
            return
        
        try:
            # Get component ID (preserve if editing, generate if new)
            comp_id = self.component.id if self.edit_mode and self.component else f"compdb_{uuid.uuid4().hex[:8]}"
            
            # Get values
            shortcut = self.shortcut_input.text().strip() or None
            material = self.material_input.text().strip() or None
            fits = self.fits_input.value() if self.fits_input.value() > 0 else None
            database = self.database_input.text().strip() or None
            
            # Get failure modes
            failure_modes = {}
            total_percentage = 0.0
            
            for row in range(self.failure_modes_table.rowCount()):
                name_item = self.failure_modes_table.item(row, 0)
                percentage_item = self.failure_modes_table.item(row, 1)
                
                if name_item and percentage_item:
                    name = name_item.text().strip()
                    try:
                        percentage = float(percentage_item.text())
                        if name:
                            failure_modes[name] = percentage
                            total_percentage += percentage
                    except ValueError:
                        QMessageBox.warning(
                            self,
                            "Validation Error",
                            f"Invalid percentage value in row {row + 1}"
                        )
                        return
            
            # Warn if total percentage doesn't equal 100
            if failure_modes and abs(total_percentage - 100.0) > 0.01:
                reply = QMessageBox.question(
                    self,
                    "Percentage Warning",
                    f"Failure modes total {total_percentage:.2f}%, not 100%. Continue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            
            # Create component
            component = ComponentDB(
                id=comp_id,
                display_name=display_name,
                shortcut=shortcut,
                material=material,
                fits=fits,
                database=database,
                failure_modes=failure_modes,
                created_at=self.component.created_at if self.edit_mode and self.component else datetime.now(),
                updated_at=datetime.now()
            )
            
            # Emit signal and close
            self.component_saved.emit(component)
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save component:\n{str(e)}"
            )
