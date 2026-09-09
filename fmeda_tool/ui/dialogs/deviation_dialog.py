from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, List, Dict, Any
import uuid

from fmeda_tool.models import Deviation, Mitigation, DeviationType, DeviationSeverity
from fmeda_tool.ui.dialogs.mitigation_dialog import MitigationDialog


class DeviationDialog(QDialog):
    """Dialog for creating/editing a deviation"""
    
    deviation_saved = pyqtSignal(Deviation, list)  # Deviation and list of Mitigation objects
    
    def __init__(
        self,
        unit_name: str = "Project / Global",
        deviation: Optional[Deviation] = None,
        mitigations: Optional[List[Mitigation]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.unit_name = unit_name
        self.deviation = deviation
        self.mitigations = list(mitigations) if mitigations else []
        self.saved_deviation: Optional[Deviation] = None
        self.is_editing = deviation is not None
        
        title_text = f"{deviation.name if deviation else 'New Deviation'} ({unit_name})"
        self.setWindowTitle(title_text)
        self.setMinimumWidth(700)
        self.setMinimumHeight(550)
        
        self._setup_ui()
        if self.deviation:
            self._load_data()
        self._refresh_mitigations_table()
    
    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header with title and save button
        self._create_header(layout)
        
        # Form fields
        self._create_form(layout)
        
        # Mitigations table
        self._create_mitigations_section(layout)
    
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
        title_label = QLabel(f"{self.deviation.name if self.deviation else 'New Deviation'} ({self.unit_name})")
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
        self.name_input.setPlaceholderText("Enter deviation name...")
        parent_layout.addWidget(self.name_input)
        
        # Potential Impact field
        impact_label = QLabel("Potential Impact:")
        parent_layout.addWidget(impact_label)
        
        self.impact_input = QLineEdit()
        self.impact_input.setPlaceholderText("Describe the potential impact...")
        parent_layout.addWidget(self.impact_input)
        
        # Description field
        desc_label = QLabel("Description:")
        parent_layout.addWidget(desc_label)
        
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Enter detailed description...")
        self.description_input.setMinimumHeight(120)
        parent_layout.addWidget(self.description_input)
    
    def _create_mitigations_section(self, parent_layout):
        """Create mitigations table section"""
        # Section header with label and add button
        section_header = QHBoxLayout()
        
        mitigations_label = QLabel("Mitigations")
        mitigations_font = QFont()
        mitigations_font.setPointSize(10)
        mitigations_font.setBold(True)
        mitigations_label.setFont(mitigations_font)
        section_header.addWidget(mitigations_label)
        
        section_header.addStretch()
        
        add_mitigation_btn = QPushButton("➕ Add Mitigation")
        add_mitigation_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
        """)
        add_mitigation_btn.clicked.connect(self._on_add_mitigation)
        section_header.addWidget(add_mitigation_btn)
        
        parent_layout.addLayout(section_header)
        
        # Mitigations table
        self.mitigations_table = QTableWidget()
        self.mitigations_table.setColumnCount(4)
        self.mitigations_table.setHorizontalHeaderLabels(["Name", "Type", "Effectiveness", "Actions"])
        
        # Style the table
        self.mitigations_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #dee2e6;
                font-weight: bold;
            }
        """)
        
        # Enable independent column resizing
        self.mitigations_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.mitigations_table.setColumnWidth(0, 200)  # Name
        self.mitigations_table.setColumnWidth(1, 150)  # Category
        self.mitigations_table.setColumnWidth(2, 100)  # Effectiveness
        self.mitigations_table.setColumnWidth(3, 150)  # Actions
        
        # Enable horizontal scrollbar if columns exceed table width
        self.mitigations_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        parent_layout.addWidget(self.mitigations_table)
    
    def _refresh_mitigations_table(self):
        """Refresh the mitigations table"""
        self.mitigations_table.setRowCount(0)
        
        for mitigation in self.mitigations:
            row = self.mitigations_table.rowCount()
            self.mitigations_table.insertRow(row)
            
            # Name
            self.mitigations_table.setItem(row, 0, QTableWidgetItem(mitigation.name))
            
            # Type
            self.mitigations_table.setItem(row, 1, QTableWidgetItem(
                mitigation.mitigation_type.value.replace('_', ' ').title()
            ))
            
            # Effectiveness
            eff_text = f"{mitigation.effectiveness:.2f}" if mitigation.effectiveness else "N/A"
            self.mitigations_table.setItem(row, 2, QTableWidgetItem(eff_text))
            
            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            
            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0d6efd;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #0b5ed7;
                }
            """)
            edit_btn.clicked.connect(lambda checked, m=mitigation: self._on_edit_mitigation(m))
            actions_layout.addWidget(edit_btn)
            
            delete_btn = QPushButton("Delete")
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #bb2d3b;
                }
            """)
            delete_btn.clicked.connect(lambda checked, m=mitigation: self._on_delete_mitigation(m))
            actions_layout.addWidget(delete_btn)
            
            self.mitigations_table.setCellWidget(row, 3, actions_widget)
    
    def _load_data(self):
        """Load deviation data into form"""
        if not self.deviation:
            return
        
        self.name_input.setText(self.deviation.name)
        self.impact_input.setText(self.deviation.effect or "")
        self.description_input.setPlainText(self.deviation.description)
    
    def _on_add_mitigation(self):
        """Handle add mitigation button click"""
        deviation_name = self.name_input.text().strip() or "New Deviation"
        dialog = MitigationDialog(deviation_name=deviation_name, unit_name=self.unit_name, parent=self)
        dialog.mitigation_saved.connect(self._on_mitigation_created)
        dialog.exec()
    
    def _on_edit_mitigation(self, mitigation: Mitigation):
        """Handle edit mitigation button click"""
        deviation_name = self.name_input.text().strip() or "New Deviation"
        dialog = MitigationDialog(deviation_name=deviation_name, unit_name=self.unit_name, mitigation=mitigation, parent=self)
        dialog.mitigation_saved.connect(self._on_mitigation_updated)
        dialog.exec()
    
    def _on_mitigation_created(self, mitigation: Mitigation):
        """Handle new mitigation created"""
        self.mitigations.append(mitigation)
        self._refresh_mitigations_table()
    
    def _on_mitigation_updated(self, mitigation: Mitigation):
        """Handle mitigation updated"""
        self._refresh_mitigations_table()
    
    def _on_delete_mitigation(self, mitigation: Mitigation):
        """Handle delete mitigation button click"""
        reply = QMessageBox.question(
            self,
            "Delete Mitigation",
            f"Are you sure you want to delete mitigation '{mitigation.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.mitigations.remove(mitigation)
            self._refresh_mitigations_table()
    
    def _on_save(self):
        """Handle save button click"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please enter a deviation name.")
            return
        
        impact = self.impact_input.text().strip()
        description = self.description_input.toPlainText().strip()
        if not description:
            QMessageBox.warning(self, "Validation Error", "Please enter a description.")
            return
        
        if self.is_editing and self.deviation:
            # Update existing deviation
            self.deviation.name = name
            self.deviation.effect = impact
            self.deviation.description = description
            self.deviation.mitigation_ids = [m.id for m in self.mitigations]
            deviation_to_save = self.deviation
        else:
            # Create new deviation
            deviation_id = f"dev_{uuid.uuid4().hex[:8]}"
            deviation_to_save = Deviation(
                id=deviation_id,
                name=name,
                description=description,
                deviation_type=DeviationType.DANGEROUS_DETECTED,  # Default
                severity=DeviationSeverity.MEDIUM,  # Default
                failure_mode=name,
                effect=impact,
                mitigation_ids=[m.id for m in self.mitigations]
            )
        
        self.saved_deviation = deviation_to_save
        self.deviation = deviation_to_save
        self.deviation_saved.emit(deviation_to_save, self.mitigations)
        self.accept()

    def get_deviation(self) -> Optional[Deviation]:
        """Returns the saved or edited Deviation model instance, if accepted."""
        return getattr(self, "saved_deviation", self.deviation)

    def get_deviation_data(self) -> Optional[Dict[str, Any]]:
        """Returns a dictionary representation of the deviation data."""
        dev = self.get_deviation()
        if not dev:
            return None
        return {
            "name": dev.name,
            "description": dev.description,
            "deviation_type": dev.deviation_type,
            "severity": dev.severity,
            "failure_mode": dev.failure_mode,
            "effect": getattr(dev, "effect", None)
        }

    def get_mitigations(self) -> List[Mitigation]:
        """Returns the associated list of mitigations."""
        return getattr(self, "mitigations", [])
