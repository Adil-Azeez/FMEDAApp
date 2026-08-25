

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton,
    QScrollArea, QFrame, QDoubleSpinBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional
import uuid

from fmeda_tool.models import DiagnosticMeasure


class CreateDiagnosticMeasureView(QWidget):
    """Full-page view for creating a diagnostic measure"""
    
    measure_saved = pyqtSignal(DiagnosticMeasure)
    cancel_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.measure: Optional[DiagnosticMeasure] = None
        self.edit_mode = False
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the UI layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Custom Header
        self._create_header()
        main_layout.addWidget(self.header_frame)
        
        # Scrollable content area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(40, 30, 40, 30)
        content_layout.setSpacing(30)
        
        # Form Section
        self._create_form_section(content_layout)
        
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
        
    def _create_header(self):
        """Create custom header with title and save/cancel buttons"""
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-bottom: 2px solid #dee2e6;
            }
        """)
        self.header_frame.setFixedHeight(70)
        
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(30, 10, 30, 10)
        
        header_layout.addStretch()
        
        # Center: Title
        self.title_label = QLabel("Create Diagnostic Measure")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #212529;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # Right: Save and Cancel buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(100, 35)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        cancel_btn.clicked.connect(self._on_cancel)
        buttons_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save Measure")
        save_btn.setFixedSize(130, 35)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        save_btn.clicked.connect(self._save_measure)
        buttons_layout.addWidget(save_btn)
        
        header_layout.addLayout(buttons_layout)
        
    def _create_form_section(self, parent_layout):
        """Create form section for diagnostic measure fields"""
        section_label = QLabel("Diagnostic Measure Details")
        section_font = QFont()
        section_font.setPointSize(14)
        section_font.setBold(True)
        section_label.setFont(section_font)
        parent_layout.addWidget(section_label)
        
        # Form layout
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # ID (auto-generated, read-only in create mode)
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Auto-generated...")
        self.id_input.setReadOnly(True)
        self.id_input.setMinimumHeight(35)
        self.id_input.setStyleSheet("background-color: #e9ecef;")
        form_layout.addRow("ID:", self.id_input)
        
        # Diagnostic Coverage (0-100)
        dc_layout = QHBoxLayout()
        self.dc_input = QDoubleSpinBox()
        self.dc_input.setRange(0.0, 100.0)
        self.dc_input.setValue(95.0)
        self.dc_input.setDecimals(2)
        self.dc_input.setSuffix(" %")
        self.dc_input.setMinimumHeight(35)
        self.dc_input.setMinimumWidth(150)
        dc_layout.addWidget(self.dc_input)
        dc_layout.addWidget(QLabel("Diagnostic Coverage (0-100%)"))
        dc_layout.addStretch()
        form_layout.addRow("DC*:", dc_layout)
        
        # Description
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Enter diagnostic measure description...")
        self.description_input.setMinimumHeight(100)
        self.description_input.setMaximumHeight(150)
        form_layout.addRow("Description*:", self.description_input)
        
        # Risk ID (optional)
        self.risk_id_input = QLineEdit()
        self.risk_id_input.setPlaceholderText("Optional: Associated risk identifier...")
        self.risk_id_input.setMinimumHeight(35)
        form_layout.addRow("Risk ID:", self.risk_id_input)
        
        # SW Requirement ID (optional)
        self.sw_req_id_input = QLineEdit()
        self.sw_req_id_input.setPlaceholderText("Optional: Software requirement identifier...")
        self.sw_req_id_input.setMinimumHeight(35)
        form_layout.addRow("SW Requirement ID:", self.sw_req_id_input)
        
        parent_layout.addLayout(form_layout)
        
        # Help text
        help_label = QLabel("* Required fields")
        help_label.setStyleSheet("color: #6c757d; font-style: italic;")
        parent_layout.addWidget(help_label)
        
    def _validate_inputs(self) -> bool:
        """Validate user inputs"""
        if not self.description_input.toPlainText().strip():
            QMessageBox.warning(
                self,
                "Validation Error",
                "Description is required."
            )
            self.description_input.setFocus()
            return False
        
        # DC validation (already constrained by spinbox, but double-check)
        if self.dc_input.value() < 0 or self.dc_input.value() > 100:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Diagnostic Coverage must be between 0 and 100%."
            )
            self.dc_input.setFocus()
            return False
        
        return True
        
    def _save_measure(self):
        """Save the diagnostic measure"""
        if not self._validate_inputs():
            return
        
        try:
            # Generate unique ID if not in edit mode
            measure_id = self.id_input.text().strip()
            if not measure_id:
                measure_id = f"dm_{uuid.uuid4().hex[:8]}"
            
            # Get risk ID and SW requirement ID (optional)
            risk_id = self.risk_id_input.text().strip() or None
            sw_req_id = self.sw_req_id_input.text().strip() or None
            
            # Create diagnostic measure
            self.measure = DiagnosticMeasure(
                id=measure_id,
                dc=self.dc_input.value(),
                description=self.description_input.toPlainText().strip(),
                riskId=risk_id,
                swRequirementId=sw_req_id
            )
            
            # Emit signal
            self.measure_saved.emit(self.measure)
            
            # Show success message
            QMessageBox.information(
                self,
                "Success",
                f"Diagnostic measure saved successfully!"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save diagnostic measure:\n{str(e)}"
            )
    
    def _on_cancel(self):
        """Handle cancel button"""
        reply = QMessageBox.question(
            self,
            "Cancel",
            "Are you sure you want to cancel? Any unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cancel_requested.emit()
    
    def reset_form(self):
        """Reset the form to default values"""
        self.id_input.clear()
        self.dc_input.setValue(95.0)
        self.description_input.clear()
        self.risk_id_input.clear()
        self.sw_req_id_input.clear()
        self.measure = None
        self.edit_mode = False
        self.title_label.setText("Create Diagnostic Measure")
    
    def load_measure(self, measure: DiagnosticMeasure):
        """Load an existing measure for editing"""
        self.measure = measure
        self.edit_mode = True
        self.title_label.setText("Edit Diagnostic Measure")
        
        self.id_input.setText(measure.id)
        self.dc_input.setValue(measure.dc)
        self.description_input.setPlainText(measure.description)
        self.risk_id_input.setText(measure.risk_id or "")
        self.sw_req_id_input.setText(measure.sw_requirement_id or "")
