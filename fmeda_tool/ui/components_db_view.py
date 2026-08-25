

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QLabel, QLineEdit,
    QComboBox, QMessageBox, QFrame, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QAction
from typing import List
import json
from pathlib import Path

from fmeda_tool.models import ComponentDB
from .dialogs import ComponentDBDialog


class ComponentsDBView(QWidget):
    """View for managing the components database"""
    
    def __init__(self):
        super().__init__()
        self.components: List[ComponentDB] = []
        self.filtered_components: List[ComponentDB] = []
        self._setup_ui()
        self._load_components_from_file()
    
    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create header
        self._create_header(layout)
        
        # Create components table
        self._create_table(layout)
    
    def _create_header(self, parent_layout):
        """Create header with search and add button"""
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-bottom: 2px solid #dee2e6;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(15)
        
        # Title row
        title_layout = QHBoxLayout()
        
        title_label = QLabel("Components Database")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #212529; border: none;")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        # Add Component button
        add_btn = QPushButton("+ Add Component")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #198754;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #157347;
            }
            QPushButton:pressed {
                background-color: #146c43;
            }
        """)
        add_btn.clicked.connect(self._on_add_component)
        title_layout.addWidget(add_btn)
        
        header_layout.addLayout(title_layout)
        
        # Search row
        search_layout = QHBoxLayout()
        
        # Search text field
        search_label = QLabel("Search:")
        search_label.setStyleSheet("border: none;")
        search_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        self.search_input.setMinimumWidth(300)
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #0d6efd;
            }
        """)
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        
        # Column selector
        in_label = QLabel("in")
        in_label.setStyleSheet("border: none;")
        search_layout.addWidget(in_label)
        
        self.column_combo = QComboBox()
        self.column_combo.addItems([
            "All Columns",
            "Display Name",
            "Shortcut",
            "Material",
            "Database"
        ])
        self.column_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
            }
        """)
        self.column_combo.currentTextChanged.connect(self._on_search)
        search_layout.addWidget(self.column_combo)
        
        search_layout.addStretch()
        
        # Component count
        self.count_label = QLabel("0 components")
        self.count_label.setStyleSheet("color: #6c757d; border: none;")
        search_layout.addWidget(self.count_label)
        
        header_layout.addLayout(search_layout)
        
        parent_layout.addWidget(header_frame)
    
    def _create_table(self, parent_layout):
        """Create the components table"""
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: white;")
        content_layout = QVBoxLayout(content_widget)
        # Remove horizontal margins - table should span full width from edge to edge
        content_layout.setContentsMargins(0, 20, 0, 20)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Display Name", "Shortcut", "Material", "FITS", "Database"
        ])
        
        # Enable context menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        # Style the table
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                gridline-color: #dee2e6;
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #f1f3f5;
            }
            QTableWidget::item:selected {
                background-color: #e7f1ff;
                color: #212529;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 12px 8px;
                border: none;
                border-bottom: 2px solid #dee2e6;
                border-right: 1px solid #dee2e6;
                font-weight: bold;
                color: #495057;
            }
        """)
        
        # Configure table properties - enable interactive column resizing
        # All columns are independent - resizing one doesn't affect others
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.table.setColumnWidth(0, 200)  # Display Name
        self.table.setColumnWidth(1, 120)  # Shortcut
        self.table.setColumnWidth(2, 150)  # Material
        self.table.setColumnWidth(3, 100)  # FITS
        self.table.setColumnWidth(4, 200)  # Database
        
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Enable horizontal scrollbar if columns exceed table width
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        content_layout.addWidget(self.table)
        
        # Empty state message
        self.empty_state_label = QLabel("No components in database. Click '+ Add Component' to get started.")
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.empty_state_label.setVisible(False)
        content_layout.addWidget(self.empty_state_label)
        
        parent_layout.addWidget(content_widget)
    
    def _show_context_menu(self, position):
        """Show context menu on right-click"""
        # Get the item at the clicked position
        item = self.table.itemAt(position)
        if not item:
            return
        
        # Get the component from the first column of this row
        row = item.row()
        first_item = self.table.item(row, 0)
        if not first_item:
            return
        
        component = first_item.data(Qt.ItemDataRole.UserRole)
        if not component:
            return
        
        # Create context menu
        menu = QMenu(self)
        
        # Edit action
        edit_action = QAction("✏️ Edit", self)
        edit_action.triggered.connect(lambda: self._on_edit_component(component))
        menu.addAction(edit_action)
        
        # Delete action
        delete_action = QAction("🗑️ Delete", self)
        delete_action.triggered.connect(lambda: self._on_delete_component(component))
        menu.addAction(delete_action)
        
        # Show menu at cursor position
        menu.exec(self.table.viewport().mapToGlobal(position))
    
    def _load_components_from_file(self):
        """Load components from JSON file"""
        try:
            db_path = Path("data/components_db.json")
            if db_path.exists():
                with open(db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.components = [ComponentDB(**comp) for comp in data]
                self.filtered_components = self.components.copy()
                self._refresh_table()
                print(f"✓ Loaded {len(self.components)} components from database")
            else:
                print("No components database found, starting empty")
        except Exception as e:
            QMessageBox.warning(
                self,
                "Load Error",
                f"Failed to load components database:\n{str(e)}"
            )
            print(f"✗ Error loading components: {e}")
    
    def _save_components_to_file(self):
        """Save components to JSON file"""
        try:
            db_path = Path("data/components_db.json")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to dicts
            data = [comp.model_dump(mode='json') for comp in self.components]
            
            with open(db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            
            print(f"✓ Saved {len(self.components)} components to database")
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save components database:\n{str(e)}"
            )
            print(f"✗ Error saving components: {e}")
    
    def _refresh_table(self):
        """Refresh the table with current filtered components"""
        self.table.setRowCount(0)
        
        if not self.filtered_components:
            self.table.setVisible(False)
            self.empty_state_label.setVisible(True)
            self.count_label.setText("0 components")
            return
        
        self.table.setVisible(True)
        self.empty_state_label.setVisible(False)
        
        for component in self.filtered_components:
            self._add_component_to_table(component)
        
        # Update count
        total = len(self.components)
        filtered = len(self.filtered_components)
        if filtered < total:
            self.count_label.setText(f"{filtered} of {total} components")
        else:
            self.count_label.setText(f"{total} component{'s' if total != 1 else ''}")
    
    def _add_component_to_table(self, component: ComponentDB):
        """Add a component to the table"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Display Name
        self.table.setItem(row, 0, QTableWidgetItem(component.display_name))
        
        # Shortcut
        shortcut = component.shortcut if component.shortcut else ""
        self.table.setItem(row, 1, QTableWidgetItem(shortcut))
        
        # Material
        material = component.material if component.material else ""
        self.table.setItem(row, 2, QTableWidgetItem(material))
        
        # FITS
        fits = f"{component.fits:.4f}" if component.fits else ""
        self.table.setItem(row, 3, QTableWidgetItem(fits))
        
        # Database
        database = component.database if component.database else ""
        self.table.setItem(row, 4, QTableWidgetItem(database))
        
        # Store component reference in row data for context menu
        self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, component)
    
    def _on_search(self):
        """Handle search input change"""
        search_term = self.search_input.text().strip().lower()
        search_column = self.column_combo.currentText()
        
        if not search_term:
            self.filtered_components = self.components.copy()
        else:
            self.filtered_components = []
            
            for component in self.components:
                match = False
                
                if search_column == "All Columns":
                    # Search in all text fields
                    if (search_term in component.display_name.lower() or
                        (component.shortcut and search_term in component.shortcut.lower()) or
                        (component.material and search_term in component.material.lower()) or
                        (component.database and search_term in component.database.lower())):
                        match = True
                
                elif search_column == "Display Name":
                    if search_term in component.display_name.lower():
                        match = True
                
                elif search_column == "Shortcut":
                    if component.shortcut and search_term in component.shortcut.lower():
                        match = True
                
                elif search_column == "Material":
                    if component.material and search_term in component.material.lower():
                        match = True
                
                elif search_column == "Database":
                    if component.database and search_term in component.database.lower():
                        match = True
                
                if match:
                    self.filtered_components.append(component)
        
        self._refresh_table()
    
    def _on_add_component(self):
        """Handle add component button click"""
        dialog = ComponentDBDialog(self)
        dialog.component_saved.connect(self._on_component_saved)
        dialog.exec()
    
    def _on_edit_component(self, component: ComponentDB):
        """Handle edit component button click"""
        dialog = ComponentDBDialog(self, component=component)
        dialog.component_saved.connect(self._on_component_updated)
        dialog.exec()
    
    def _on_component_saved(self, component: ComponentDB):
        """Handle new component saved"""
        self.components.append(component)
        self._save_components_to_file()
        self._on_search()  # Refresh with current search
        print(f"✓ Component added: {component.display_name}")
    
    def _on_component_updated(self, component: ComponentDB):
        """Handle component updated"""
        # Find and replace the component
        for i, comp in enumerate(self.components):
            if comp.id == component.id:
                self.components[i] = component
                break
        
        self._save_components_to_file()
        self._on_search()  # Refresh with current search
        print(f"✓ Component updated: {component.display_name}")
    
    def _on_delete_component(self, component: ComponentDB):
        """Handle delete component button click"""
        reply = QMessageBox.question(
            self,
            "Delete Component",
            f"Are you sure you want to delete '{component.display_name}' from the database?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from list
            self.components = [c for c in self.components if c.id != component.id]
            
            self._save_components_to_file()
            self._on_search()  # Refresh with current search
            print(f"✓ Component deleted: {component.display_name}")
