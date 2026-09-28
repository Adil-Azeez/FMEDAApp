from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QComboBox, QDoubleSpinBox, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, Dict, Any
import uuid

from fmeda_tool.models import Mitigation, MitigationType, MitigationStatus


class MitigationDialog(QDialog):
    """Dialog for creating/editing a mitigation measure."""

    mitigation_saved = pyqtSignal(Mitigation)

    def __init__(
        self,
        deviation_name: str = "Unassigned Deviation",
        unit_name: str = "Global / Project",
        mitigation: Optional[Mitigation] = None,
        parent=None
    ):
        super().__init__(parent)

        self.deviation_name = deviation_name or "Unassigned Deviation"
        self.unit_name = unit_name or "Global / Project"
        self.mitigation = mitigation
        self.saved_mitigation: Optional[Mitigation] = None
        self.is_editing = mitigation is not None

        title_text = (
            f"{mitigation.name if mitigation else 'New Mitigation'} "
            f"({self.deviation_name} — {self.unit_name})"
        )

        self.setWindowTitle(title_text)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self._setup_ui()

        if self.mitigation:
            self._load_data()
    
    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header with title and save button
        self._create_header(layout)
        
        # Form fields
        self._create_form(layout)
    
    def _create_header(self, parent_layout):
        """Create header with title and save button"""
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-bottom: 2px solid #dee2e6;
                padding: 10px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 10)
        
        # Title
        title_label = QLabel(f"{self.mitigation.name if self.mitigation else 'New Mitigation'} ({self.deviation_name} ({self.unit_name}))")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Save button
        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #198754;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #157347;
            }
        """)
        save_btn.clicked.connect(self._on_save)
        header_layout.addWidget(save_btn)
        
        parent_layout.addWidget(header_frame)
    
    def _create_form(self, parent_layout):
        """Create form fields"""
        # Name field
        name_label = QLabel("Name:")
        parent_layout.addWidget(name_label)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter mitigation name...")
        parent_layout.addWidget(self.name_input)
        
        # Effectiveness field
        eff_label = QLabel("Effectiveness (0.0 - 1.0):")
        parent_layout.addWidget(eff_label)
        
        self.effectiveness_input = QDoubleSpinBox()
        self.effectiveness_input.setRange(0.0, 1.0)
        self.effectiveness_input.setSingleStep(0.1)
        self.effectiveness_input.setDecimals(2)
        self.effectiveness_input.setValue(0.9)
        parent_layout.addWidget(self.effectiveness_input)
        
        # Type field
        type_label = QLabel("Type:")
        parent_layout.addWidget(type_label)
        
        self.type_combo = QComboBox()
        for mit_type in MitigationType:
            self.type_combo.addItem(mit_type.value.replace('_', ' ').title(), mit_type.value)
        parent_layout.addWidget(self.type_combo)
        
        # Description field
        desc_label = QLabel("Description:")
        parent_layout.addWidget(desc_label)
        
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Enter detailed description...")
        self.description_input.setMinimumHeight(150)
        parent_layout.addWidget(self.description_input)
        
        parent_layout.addStretch()
    
    def _load_data(self):
        """Load mitigation data into form"""
        if not self.mitigation:
            return
        
        self.name_input.setText(self.mitigation.name)
        self.effectiveness_input.setValue(self.mitigation.effectiveness or 0.9)
        
        # Set type
        index = self.type_combo.findData(self.mitigation.mitigation_type.value)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        
        self.description_input.setPlainText(self.mitigation.description)
    
    def _on_save(self):
        """Handle save button click"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please enter a mitigation name.")
            return
        
        description = self.description_input.toPlainText().strip()
        if not description:
            QMessageBox.warning(self, "Validation Error", "Please enter a description.")
            return
        
        effectiveness = self.effectiveness_input.value()
        mitigation_type = MitigationType(self.type_combo.currentData())
        
        if self.is_editing and self.mitigation:
            # Update existing mitigation
            self.mitigation.name = name
            self.mitigation.description = description
            self.mitigation.effectiveness = effectiveness
            self.mitigation.mitigation_type = mitigation_type
            mitigation_to_save = self.mitigation
        else:
            # Create new mitigation
            mitigation_id = f"mit_{uuid.uuid4().hex[:8]}"
            mitigation_to_save = Mitigation(
                id=mitigation_id,
                name=name,
                description=description,
                effectiveness=effectiveness,
                mitigation_type=mitigation_type,
                status=MitigationStatus.PROPOSED
            )
        
        self.saved_mitigation = mitigation_to_save
        self.mitigation = mitigation_to_save
        self.mitigation_saved.emit(mitigation_to_save)
        self.accept()

    def get_mitigation(self) -> Optional[Mitigation]:
        """Returns the saved or edited Mitigation model instance, if accepted."""
        return getattr(self, "saved_mitigation", self.mitigation)

    def get_mitigation_data(self) -> Optional[Dict[str, Any]]:
        """Returns a dictionary representation of the mitigation data."""
        mit = self.get_mitigation()
        if not mit:
            return None
        return {
            "name": mit.name,
            "description": mit.description,
            "effectiveness": mit.effectiveness,
            "mitigation_type": mit.mitigation_type,
            "status": mit.status.value if hasattr(mit.status, "value") else str(mit.status)
        }
