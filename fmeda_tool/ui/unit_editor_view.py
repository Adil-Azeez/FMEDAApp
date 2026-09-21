from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGraphicsView,
    QGraphicsScene, QPushButton, QLabel, QFrame, QMenu,
    QGraphicsRectItem, QGraphicsTextItem, QScrollArea, QGridLayout,
    QMessageBox, QStackedWidget, QTableView, QHeaderView,
    QComboBox, QDoubleSpinBox, QLineEdit, QDialog, QDialogButtonBox, QFormLayout,
    QTextEdit, QCheckBox, QFileDialog, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF, QModelIndex, QItemSelection, QItemSelectionModel, QPoint
from PyQt6.QtGui import (
    QFont, QPainter, QWheelEvent, QMouseEvent, QContextMenuEvent, QKeyEvent,
    QColor, QPen, QBrush, QAction
)
from typing import Optional, List, Dict, Tuple, Any, Set
import uuid
import time
import json
import copy
from pathlib import Path

from fmeda_tool.models import (
    Unit, Component, Project, ComponentDB, FailureModeAssignment,
    Deviation, Mitigation, DiagnosticMeasure, DeviationType, DeviationSeverity, MitigationType
)
from fmeda_tool.ui.dialogs import (
    ComponentSelectionDialog, ComponentInstanceDialog, DeviationDialog, MitigationDialog,
    BOMImportDialog, ComponentMappingDialog,
    ComponentDetailsDialog, DuplicateComponentDialog, BulkItemPickerDialog,
    BulkActionSummaryDialog, DeleteComponentsConfirmDialog
)
from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel, FmedaRowEntry, COLUMN_HEADERS
from fmeda_tool.ui.delegates.fmeda_delegates import (
    FmedaComboBoxDelegate, FmedaSpinBoxDelegate, FmedaLineEditDelegate
)
from fmeda_tool.services import ValidationService, ComponentLibraryService
from fmeda_tool.ui.widgets import WorkflowPageHeader
from fmeda_tool.utils.performance import PerformanceTimer


class DiagnosticMeasureMiniDialog(QDialog):
    """Dialog to create or edit a single Diagnostic Measure"""
    def __init__(self, dm: Optional[DiagnosticMeasure] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Diagnostic Measure" if dm is None else "Edit Diagnostic Measure")
        self.setMinimumWidth(450)
        self.dm = dm
        self._setup_ui()
        if self.dm:
            self._load_data()
            
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.desc_input = QLineEdit()
        form.addRow("Description / Test Name*:", self.desc_input)
        
        self.dc_input = QDoubleSpinBox()
        self.dc_input.setRange(0.0, 100.0)
        self.dc_input.setValue(90.0)
        self.dc_input.setSuffix("%")
        form.addRow("Diagnostic Coverage (DC %)*:", self.dc_input)
        
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80)
        self.notes_input.setPlaceholderText("Optional engineering notes or references...")
        form.addRow("Notes:", self.notes_input)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def _on_accept(self):
        desc = self.desc_input.text().strip()
        if not desc:
            QMessageBox.warning(self, "Validation Error", "Description is required.")
            return
            
        dm_id = self.dm.id if self.dm else f"dm_{uuid.uuid4().hex[:8]}"
        self.dm = DiagnosticMeasure(
            id=dm_id,
            description=desc,
            dc=self.dc_input.value(),
            notes=self.notes_input.toPlainText().strip() or None
        )
        self.accept()
        
    def _load_data(self):
        self.desc_input.setText(self.dm.description)
        self.dc_input.setValue(self.dm.dc)
        self.notes_input.setPlainText(getattr(self.dm, "notes", "") or "")


class DiagnosticMeasureManagerDialog(QDialog):
    """Dialog to manage the project's library of diagnostic measures"""
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Diagnostic Measures Library - {project.name}")
        self.setMinimumSize(700, 400)
        self.project = project
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        from PyQt6.QtWidgets import QTableWidget
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Description / Test", "DC %", "Notes"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        
        btn_lay = QHBoxLayout()
        self.add_btn = QPushButton("➕ Add Measure")
        self.add_btn.clicked.connect(self._on_add)
        btn_lay.addWidget(self.add_btn)
        
        self.edit_btn = QPushButton("✏️ Edit Measure")
        self.edit_btn.clicked.connect(self._on_edit)
        btn_lay.addWidget(self.edit_btn)
        
        self.remove_btn = QPushButton("❌ Remove Measure")
        self.remove_btn.clicked.connect(self._on_remove)
        btn_lay.addWidget(self.remove_btn)
        
        btn_lay.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_lay.addWidget(close_btn)
        layout.addLayout(btn_lay)
        
        self._refresh_table()
        
    def _refresh_table(self):
        from PyQt6.QtWidgets import QTableWidgetItem
        self.table.setRowCount(len(self.project.diagnostic_measures))
        for r, dm in enumerate(self.project.diagnostic_measures):
            it_desc = QTableWidgetItem(dm.description)
            it_desc.setData(Qt.ItemDataRole.UserRole, dm)
            self.table.setItem(r, 0, it_desc)
            self.table.setItem(r, 1, QTableWidgetItem(f"{dm.dc:.1f}%"))
            self.table.setItem(r, 2, QTableWidgetItem(getattr(dm, "notes", "") or ""))
            
    def _on_add(self):
        dialog = DiagnosticMeasureMiniDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.dm:
            self.project.diagnostic_measures.append(dialog.dm)
            self._refresh_table()
            
    def _on_edit(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a diagnostic measure to edit.")
            return
        dm = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dialog = DiagnosticMeasureMiniDialog(dm, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.dm:
            self.project.diagnostic_measures[row] = dialog.dm
            self._refresh_table()
            
    def _on_remove(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a diagnostic measure to remove.")
            return
        dm = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        assigned_locations = []
        for u in self.project.units:
            for comp in u.components:
                for a in comp.failure_mode_assignments:
                    if a.diagnostic_measure_id == dm.id:
                        assigned_locations.append((u, comp, a))
                        
        if assigned_locations:
            reply = QMessageBox.question(
                self, "Confirm Remove",
                f"Diagnostic measure '{dm.description}' is currently assigned to {len(assigned_locations)} failure modes.\n"
                "Removing it will clear the diagnostic measure from those rows. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            for u, comp, a in assigned_locations:
                a.diagnostic_measure_id = None
                
        self.project.diagnostic_measures.pop(row)
        self._refresh_table()


class DeviationManagerDialog(QDialog):
    """Dialog to manage the project's library of deviations"""
    def __init__(self, project: Project, unit_name: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Deviations / Failure Effects Library - {project.name}")
        self.setMinimumSize(700, 400)
        self.project = project
        self.unit_name = unit_name or (parent.unit.name if parent and hasattr(parent, "unit") and parent.unit else "Project / Global")
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        from PyQt6.QtWidgets import QTableWidget
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        
        btn_lay = QHBoxLayout()
        self.add_btn = QPushButton("➕ Add Deviation")
        self.add_btn.clicked.connect(self._on_add)
        btn_lay.addWidget(self.add_btn)
        
        self.edit_btn = QPushButton("✏️ Edit Deviation")
        self.edit_btn.clicked.connect(self._on_edit)
        btn_lay.addWidget(self.edit_btn)
        
        self.remove_btn = QPushButton("❌ Remove Deviation")
        self.remove_btn.clicked.connect(self._on_remove)
        btn_lay.addWidget(self.remove_btn)
        
        btn_lay.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_lay.addWidget(close_btn)
        layout.addLayout(btn_lay)
        
        self._refresh_table()
        
    def _refresh_table(self):
        from PyQt6.QtWidgets import QTableWidgetItem
        self.table.setRowCount(len(self.project.deviations))
        for r, dev in enumerate(self.project.deviations):
            it = QTableWidgetItem(dev.name)
            it.setData(Qt.ItemDataRole.UserRole, dev)
            self.table.setItem(r, 0, it)
            dtype = dev.deviation_type.value if hasattr(dev.deviation_type, "value") else str(dev.deviation_type)
            self.table.setItem(r, 1, QTableWidgetItem(dtype.replace("_", " ").title()))
            self.table.setItem(r, 2, QTableWidgetItem(dev.description or ""))
            
    def _on_add(self):
        dialog = DeviationDialog(unit_name=self.unit_name, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_dev = dialog.get_deviation()
        if not new_dev:
            return
        self.project.deviations.append(new_dev)
        for mit in dialog.get_mitigations():
            if mit.id not in [m.id for m in self.project.mitigations]:
                self.project.mitigations.append(mit)
        self._refresh_table()
        if self.parent() and hasattr(self.parent(), "main_editor") and self.parent().main_editor:
            self.parent().main_editor.project_changed.emit()
            
    def _on_edit(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a deviation to edit.")
            return
        dev = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        associated_mitigations = [m for m in self.project.mitigations if m.id in getattr(dev, "mitigation_ids", [])]
        dialog = DeviationDialog(unit_name=self.unit_name, deviation=dev, mitigations=associated_mitigations, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._refresh_table()
        if self.parent() and hasattr(self.parent(), "main_editor") and self.parent().main_editor:
            self.parent().main_editor.project_changed.emit()
            
    def _on_remove(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a deviation to remove.")
            return
        dev = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        assigned_count = 0
        for u in self.project.units:
            for comp in u.components:
                for a in comp.failure_mode_assignments:
                    if a.deviation_id == dev.id:
                        assigned_count += 1
                        
        if assigned_count > 0:
            reply = QMessageBox.question(
                self, "Confirm Remove",
                f"Deviation '{dev.name}' is currently assigned to {assigned_count} failure modes.\n"
                "Removing it will clear the deviation from those rows. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            for u in self.project.units:
                for comp in u.components:
                    for a in comp.failure_mode_assignments:
                        if a.deviation_id == dev.id:
                            a.deviation_id = None
                            
        self.project.deviations.pop(row)
        self._refresh_table()
        if self.parent() and hasattr(self.parent(), "main_editor") and self.parent().main_editor:
            self.parent().main_editor.project_changed.emit()


class MitigationManagerDialog(QDialog):
    """Dialog to manage the project's library of mitigations"""
    def __init__(self, project: Project, unit_name: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Mitigations Library - {project.name}")
        self.setMinimumSize(700, 400)
        self.project = project
        self.unit_name = unit_name or (parent.unit.name if parent and hasattr(parent, "unit") and parent.unit else "Global / Project")
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        from PyQt6.QtWidgets import QTableWidget
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        
        btn_lay = QHBoxLayout()
        self.add_btn = QPushButton("➕ Add Mitigation")
        self.add_btn.clicked.connect(self._on_add)
        btn_lay.addWidget(self.add_btn)
        
        self.edit_btn = QPushButton("✏️ Edit Mitigation")
        self.edit_btn.clicked.connect(self._on_edit)
        btn_lay.addWidget(self.edit_btn)
        
        self.remove_btn = QPushButton("❌ Remove Mitigation")
        self.remove_btn.clicked.connect(self._on_remove)
        btn_lay.addWidget(self.remove_btn)
        
        btn_lay.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_lay.addWidget(close_btn)
        layout.addLayout(btn_lay)
        
        self._refresh_table()
        
    def _refresh_table(self):
        from PyQt6.QtWidgets import QTableWidgetItem
        self.table.setRowCount(len(self.project.mitigations))
        for r, mit in enumerate(self.project.mitigations):
            it = QTableWidgetItem(mit.name or mit.id)
            it.setData(Qt.ItemDataRole.UserRole, mit)
            self.table.setItem(r, 0, it)
            mtype = mit.mitigation_type.value if hasattr(mit.mitigation_type, "value") else str(mit.mitigation_type)
            self.table.setItem(r, 1, QTableWidgetItem(mtype.replace("_", " ").title()))
            self.table.setItem(r, 2, QTableWidgetItem(mit.description or ""))
            
    def _on_add(self):
        dialog = MitigationDialog(unit_name=self.unit_name, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_mit = dialog.get_mitigation()
        if not new_mit:
            return
        self.project.mitigations.append(new_mit)
        self._refresh_table()
        if self.parent() and hasattr(self.parent(), "main_editor") and self.parent().main_editor:
            self.parent().main_editor.project_changed.emit()
            
    def _on_edit(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a mitigation to edit.")
            return
        mit = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dialog = MitigationDialog(unit_name=self.unit_name, mitigation=mit, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._refresh_table()
        if self.parent() and hasattr(self.parent(), "main_editor") and self.parent().main_editor:
            self.parent().main_editor.project_changed.emit()
            
    def _on_remove(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a mitigation to remove.")
            return
        mit = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        assigned_count = 0
        for u in self.project.units:
            for comp in u.components:
                for a in comp.failure_mode_assignments:
                    if a.mitigation_id == mit.id:
                        assigned_count += 1
                        
        if assigned_count > 0:
            reply = QMessageBox.question(
                self, "Confirm Remove",
                f"Mitigation '{mit.name}' is currently assigned to {assigned_count} failure modes.\n"
                "Removing it will clear the mitigation from those rows. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            for u in self.project.units:
                for comp in u.components:
                    for a in comp.failure_mode_assignments:
                        if a.mitigation_id == mit.id:
                            a.mitigation_id = None
                            
        self.project.mitigations.pop(row)
        self._refresh_table()
        if self.parent() and hasattr(self.parent(), "main_editor") and self.parent().main_editor:
            self.parent().main_editor.project_changed.emit()


class ComponentGraphicsItem(QGraphicsRectItem):
    """Visual representation of a component on the canvas"""
    
    def __init__(self, comp_db: ComponentDB, x: float, y: float):
        super().__init__()
        
        self.comp_db = comp_db
        self.component_instance: Optional[Component] = None
        
        width = 150
        height = 80
        self.setRect(0, 0, width, height)
        self.setPos(x - width/2, y - height/2)
        
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
        self.setPen(QPen(QColor("#0d6efd"), 2))
        self.setBrush(QBrush(QColor("#e7f1ff")))
        
        self.text_item = QGraphicsTextItem(self)
        self.text_item.setPlainText(comp_db.display_name)
        self.text_item.setDefaultTextColor(QColor("#212529"))
        
        text_rect = self.text_item.boundingRect()
        text_x = (width - text_rect.width()) / 2
        text_y = (height - text_rect.height()) / 2
        self.text_item.setPos(text_x, text_y)
        
        if comp_db.shortcut:
            self.shortcut_item = QGraphicsTextItem(self)
            self.shortcut_item.setPlainText(comp_db.shortcut)
            shortcut_font = QFont()
            shortcut_font.setPointSize(8)
            self.shortcut_item.setFont(shortcut_font)
            self.shortcut_item.setDefaultTextColor(QColor("#6c757d"))
            
            shortcut_rect = self.shortcut_item.boundingRect()
            shortcut_x = (width - shortcut_rect.width()) / 2
            shortcut_y = height - shortcut_rect.height() - 5
            self.shortcut_item.setPos(shortcut_x, shortcut_y)
        
        self.press_pos = None
        self.press_time = None
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_pos = event.pos()
            self.press_time = time.time()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.press_pos and self.press_time:
            release_pos = event.pos()
            distance = (release_pos - self.press_pos).manhattanLength()
            elapsed_time = time.time() - self.press_time
            
            if distance < 5 and elapsed_time < 0.15:
                if self.scene():
                    scene = self.scene()
                    if hasattr(scene, 'views') and scene.views():
                        view = scene.views()[0]
                        if hasattr(view, 'component_clicked'):
                            view.component_clicked(self)
            
            self.press_pos = None
            self.press_time = None
        super().mouseReleaseEvent(event)
    
    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.component_instance:
                pos = self.pos()
                rect = self.rect()
                center_x = pos.x() + rect.width() / 2
                center_y = pos.y() + rect.height() / 2
                self.component_instance.x_position = center_x
                self.component_instance.y_position = center_y
        return super().itemChange(change, value)


class ComponentCanvas(QGraphicsView):
    """Canvas widget for displaying and editing components"""
    
    add_component_requested = pyqtSignal(QPointF)
    
    def __init__(self, tab_parent=None):
        super().__init__()
        self.tab_parent = tab_parent
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        self.setStyleSheet("QGraphicsView { background-color: #f8f9fa; border: 1px solid #dee2e6; }")
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
    
    def wheelEvent(self, event: QWheelEvent):
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            if self.zoom_level < self.max_zoom:
                self.scale(zoom_factor, zoom_factor)
                self.zoom_level *= zoom_factor
        else:
            if self.zoom_level > self.min_zoom:
                self.scale(1 / zoom_factor, 1 / zoom_factor)
                self.zoom_level /= zoom_factor
        event.accept()
    
    def contextMenuEvent(self, event: QContextMenuEvent):
        super().contextMenuEvent(event)


class ChangeHistoryDialog(QDialog):
    """Dialog to display the chronological change history log of a project"""
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Project Change History - {project.name}")
        self.setMinimumSize(800, 450)
        self.project = project
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Timestamp", "User", "Action", "Details"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        
        history = getattr(self.project, "change_history", []) or []
        self.table.setRowCount(len(history))
        for row, entry in enumerate(history):
            ts = entry.get("timestamp", "")
            ts_str = ts[:19].replace("T", " ") if ts else ""
            self.table.setItem(row, 0, QTableWidgetItem(ts_str))
            self.table.setItem(row, 1, QTableWidgetItem(entry.get("user", "")))
            self.table.setItem(row, 2, QTableWidgetItem(entry.get("action", "")))
            self.table.setItem(row, 3, QTableWidgetItem(entry.get("details", "")))
            
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)


class ChangeEnvironmentalProfileDialog(QDialog):
    """Dialog to select a target environmental profile for the project."""
    def __init__(self, current_profile: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Environmental Profile")
        self.setMinimumWidth(400)
        self.current_profile = current_profile or "Profile 1"
        self.target_profile = self.current_profile
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        info_lbl = QLabel(
            f"Current Environmental Profile: <b>{self.current_profile}</b><br><br>"
            "Select the new target environmental profile for this project:"
        )
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)
        
        form = QFormLayout()
        self.profile_combo = QComboBox()
        profiles = ["Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"]
        self.profile_combo.addItems(profiles)
        idx = self.profile_combo.findText(self.current_profile)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        form.addRow("Target Environmental Profile:", self.profile_combo)
        layout.addLayout(form)
        
        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        
        next_btn = QPushButton("Next")
        next_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover { background-color: #0b5ed7; }
        """)
        next_btn.clicked.connect(self._on_accept)
        btns.addWidget(next_btn)
        layout.addLayout(btns)
        
    def _on_accept(self):
        self.target_profile = self.profile_combo.currentText()
        self.accept()


class ProjectOverviewTab(QScrollArea):
    """Dashboard displaying metadata, safety context, reliability data context, and key metrics"""
    
    def __init__(self, main_editor, parent=None):
        super().__init__(parent)
        self.main_editor = main_editor
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.project = None
        self._setup_ui()
        
    def _setup_ui(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(20)
        
        title = QLabel("Project Overview Dashboard")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        
        self.grid = QGridLayout()
        self.grid.setSpacing(15)
        layout.addLayout(self.grid)
        
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #dee2e6;")
        layout.addWidget(div)
        
        # Reliability Data Context Section
        self.rel_box = QFrame()
        self.rel_box.setStyleSheet("background-color: #f0f7ff; border-radius: 6px; border: 1px solid #b6d4fe; padding: 15px;")
        self.rel_lay = QGridLayout(self.rel_box)
        self.rel_lay.setSpacing(10)
        layout.addWidget(self.rel_box)
        
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("color: #dee2e6;")
        layout.addWidget(div2)
        
        # Reviewer Approval Workflow
        rev_box = QFrame()
        rev_box.setStyleSheet("background-color: #f8f9fa; border-radius: 6px; border: 1px solid #ced4da; padding: 15px;")
        rev_lay = QGridLayout(rev_box)
        rev_lay.setSpacing(10)
        
        rev_title = QLabel("<b>Reviewer Approval Workflow</b>")
        rev_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        rev_lay.addWidget(rev_title, 0, 0, 1, 2)
        
        rev_lay.addWidget(QLabel("Project Status:"), 1, 0)
        self.status_combo = QComboBox()
        self.status_combo.addItem("Draft", "draft")
        self.status_combo.addItem("Under Review", "under_review")
        self.status_combo.addItem("Approved", "completed")
        self.status_combo.currentIndexChanged.connect(self._on_status_changed)
        rev_lay.addWidget(self.status_combo, 1, 1)
        
        rev_lay.addWidget(QLabel("Assigned Reviewer Name:"), 2, 0)
        self.reviewer_input = QLineEdit()
        self.reviewer_input.setPlaceholderText("Enter reviewer name...")
        self.reviewer_input.editingFinished.connect(self._on_reviewer_changed)
        rev_lay.addWidget(self.reviewer_input, 2, 1)
        
        layout.addWidget(rev_box)
        
        self.view_history_btn = QPushButton("📜 View Project Change History Log")
        self.view_history_btn.setStyleSheet("background-color: #6c757d; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.view_history_btn.clicked.connect(self._on_view_history)
        layout.addWidget(self.view_history_btn)
        
        layout.addStretch()
        self.setWidget(widget)
        
    def refresh(self, project: Project):
        self.project = project
        
        self.status_combo.blockSignals(True)
        self.reviewer_input.blockSignals(True)
        
        self.reviewer_input.setText(getattr(project, "reviewer", None) or "")
        status_val = project.status.value if project.status else "draft"
        idx = self.status_combo.findData(status_val)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
            
        self.status_combo.blockSignals(False)
        self.reviewer_input.blockSignals(False)
        
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
                
        for i in reversed(range(self.rel_lay.count())):
            item = self.rel_lay.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
            
        if not project:
            return
            
        def add_info_row(label: str, value: str, r: int, c: int, word_wrap: bool = False):
            lbl = QLabel(f"<b>{label}</b>")
            lbl.setStyleSheet("color: #495057;")
            val = QLabel(value)
            val.setStyleSheet("color: #212529;")
            if word_wrap:
                val.setWordWrap(True)
            self.grid.addWidget(lbl, r, c)
            self.grid.addWidget(val, r, c + 1)
            
        add_info_row("Project Name:", project.name, 0, 0)
        add_info_row("Project Number:", project.project_number or "N/A", 0, 2)
        add_info_row("Version:", project.version, 1, 0)
        add_info_row("Status:", project.status.value.replace("_", " ").title() if project.status else "Draft", 1, 2)
        add_info_row("Created By:", project.created_by or "N/A", 2, 0)
        add_info_row("Reviewer:", project.reviewer or "N/A", 2, 2)
        add_info_row("Safety Standard:", project.safety_standard.value if project.safety_standard else "N/A", 3, 0)
        add_info_row("Target SIL:", project.target_sil or "N/A", 3, 2)
        
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #dee2e6;")
        self.grid.addWidget(div, 4, 0, 1, 4)
        
        sc = project.safety_context
        safety_fn = sc.safety_function_name if sc else "N/A"
        safe_st = sc.safe_state if sc else "N/A"
        arch = sc.safety_architecture if sc else "N/A"
        no_part_def = getattr(sc, "no_part_failure_definition", None) or "Not defined"
        no_effect_def = getattr(sc, "no_effect_failure_definition", None) or "Not defined"
        
        add_info_row("Safety Function:", safety_fn, 5, 0)
        add_info_row("Safe State:", safe_st, 5, 2)
        add_info_row("Architecture:", arch, 6, 0)
        add_info_row("Mission Time:", f"{project.mission_time or 87600:.1f} hours", 6, 2)
        add_info_row("Proof Test Interval:", f"{project.test_interval or 8760:.1f} hours", 7, 0)
        add_info_row("No Part Failure Def:", no_part_def, 7, 2, word_wrap=True)
        add_info_row("No Effect Failure Def:", no_effect_def, 8, 0, word_wrap=True)
        
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("color: #dee2e6;")
        self.grid.addWidget(div2, 9, 0, 1, 4)
        
        bom_cnt = sum(len(fg.bom_components) if hasattr(fg, 'bom_components') and fg.bom_components else 0 for fg in project.units)
        mapped_cnt = sum(1 for fg in project.units if hasattr(fg, 'bom_components') and fg.bom_components for comp in fg.bom_components if comp.part_number)
        unmapped_cnt = bom_cnt - mapped_cnt
        
        add_info_row("Functional Groups:", ", ".join(fg.name for fg in project.units) or "None", 10, 0)
        add_info_row("BOM Import Status:", "Imported" if bom_cnt > 0 else "No Import Yet", 10, 2)
        add_info_row("Total BOM Components:", str(bom_cnt), 11, 0)
        add_info_row("Mapped Components:", str(mapped_cnt), 11, 2)
        add_info_row("Unmapped Components:", str(unmapped_cnt), 12, 0)
        
        tot_rate = project.total_failure_rate or 0.0
        safe_rate = project.safe_failure_rate or 0.0
        dd_rate = project.dangerous_detected_rate or 0.0
        du_rate = project.dangerous_undetected_rate or 0.0
        sff = project.sff or 0.0
        
        add_info_row("Total Failure Rate (FIT):", f"{tot_rate:.4f}", 13, 0)
        add_info_row("Safe Failure Fraction (SFF):", f"{sff:.2f}%", 13, 2)
        add_info_row("Safe Failure Rate (FIT):", f"{safe_rate:.4f}", 14, 0)
        add_info_row("Dangerous Det. Rate (FIT):", f"{dd_rate:.4f}", 14, 2)
        add_info_row("Dangerous Undet. Rate (FIT):", f"{du_rate:.4f}", 15, 0)
        add_info_row("Achieved SIL:", project.achieved_sil or "N/A", 15, 2)

        # ---------------- Reliability Data Context Section ----------------
        rel_title = QLabel("<b>Reliability Data Context & Traceability</b>")
        rel_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        rel_title.setStyleSheet("color: #084298;")
        self.rel_lay.addWidget(rel_title, 0, 0, 1, 4)

        # Component usage metrics
        all_components = [c for u in project.units for c in u.components]
        exida_count = sum(1 for c in all_components if getattr(c, "database", "").lower() == "exida" or "exida" in getattr(c, "id", "").lower())
        legacy_count = sum(1 for c in all_components if getattr(c, "database", "").lower() == "legacy")
        custom_count = len(all_components) - exida_count - legacy_count
        missing_source_count = sum(1 for c in all_components if not getattr(c, "source_reference", None) and not getattr(c, "failure_rate_id", None))

        selected_prof = getattr(project, "selected_profile", None) or getattr(project, "environmental_profile", None) or "Profile 1"

        def add_rel_row(label: str, value: str, r: int, c: int):
            lbl = QLabel(f"<b>{label}</b>")
            lbl.setStyleSheet("color: #084298;")
            val = QLabel(value)
            val.setStyleSheet("color: #052c65;")
            self.rel_lay.addWidget(lbl, r, c)
            self.rel_lay.addWidget(val, r, c + 1)

        # Selected Environmental Profile with Change Profile button
        lbl_p = QLabel("<b>Selected Environmental Profile:</b>")
        lbl_p.setStyleSheet("color: #084298;")
        self.rel_lay.addWidget(lbl_p, 1, 0)

        prof_widget = QWidget()
        prof_lay = QHBoxLayout(prof_widget)
        prof_lay.setContentsMargins(0, 0, 0, 0)
        prof_lay.setSpacing(10)
        
        self.selected_prof_lbl = QLabel(selected_prof)
        self.selected_prof_lbl.setStyleSheet("color: #052c65; font-weight: bold;")
        prof_lay.addWidget(self.selected_prof_lbl)
        
        self.change_prof_btn = QPushButton("🔄 Change Profile")
        self.change_prof_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                font-weight: bold;
                padding: 3px 10px;
                border-radius: 4px;
                border: none;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #0b5ed7; }
        """)
        self.change_prof_btn.clicked.connect(self._on_change_profile)
        prof_lay.addWidget(self.change_prof_btn)
        prof_lay.addStretch()
        self.rel_lay.addWidget(prof_widget, 1, 1)

        add_rel_row("Reliability Library:", "Exida & Legacy Component Library", 1, 2)
        add_rel_row("Handbook / Source Name:", project.reliability_database_source or "Exida Database / SN 29500 / MIL-HDBK-217F", 2, 0)
        add_rel_row("Library Database ID:", "data/fmeda.sqlite", 2, 2)
        add_rel_row("SQLite Schema / Library Version:", "Version 2.0 (Clean Schema)", 3, 0)
        add_rel_row("Component Source Policy:", "Library First with Traceable Fallback", 3, 2)
        add_rel_row("Exida Components Used:", str(exida_count), 4, 0)
        add_rel_row("Legacy Components Used:", str(legacy_count), 4, 2)
        add_rel_row("Custom / Manual Components:", str(custom_count), 5, 0)
        add_rel_row("Unresolved / Missing Source Meta:", str(missing_source_count), 5, 2)

    def _on_change_profile(self):
        if not self.project or getattr(self.main_editor, "is_loading_project", False):
            return
            
        current_profile = getattr(self.project, "selected_profile", None) or getattr(self.project, "environmental_profile", None) or "Profile 1"
        
        dlg = ChangeEnvironmentalProfileDialog(current_profile, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
            
        new_profile = dlg.target_profile
        if new_profile == current_profile:
            return
            
        # Confirmation modal with explicit Confirm and Cancel buttons
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Profile Change")
        msg_box.setText(
            f"Are you sure you want to change the environmental profile from {current_profile} to {new_profile}?\n\n"
            "This will update profile-dependent FIT values and failure-mode distributions."
        )
        msg_box.setIcon(QMessageBox.Icon.Question)
        confirm_btn = msg_box.addButton("Confirm", QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        try:
            msg_box.setDefaultButton(cancel_btn)
        except Exception:
            pass
        msg_box.exec()
        
        if msg_box.clickedButton() != confirm_btn:
            return
            
        # Push undo state before making modifications
        if hasattr(self.main_editor, "main_window") and self.main_editor.main_window:
            self.main_editor.main_window.push_undo_state(f"Change Profile: {current_profile} -> {new_profile}")
            
        # Update SQLite-linked profile-dependent data for Exida components
        from fmeda_tool.services.component_library_service import ComponentLibraryService
        from fmeda_tool.services.calculation_service import CalculationService
        from fmeda_tool.services.project_service import ProjectService
        
        for unit in self.project.units:
            for comp in unit.components:
                # Exclude legacy and custom components from silent modifications
                source_type = getattr(comp, "source_type", None) or getattr(comp, "database", None)
                if source_type in ("legacy", "custom"):
                    continue
                    
                is_exida = (
                    source_type == "exida" or
                    bool(comp.failure_rate_id) or
                    (comp.snapshot and comp.snapshot.get("source_type") == "exida")
                )
                
                if is_exida:
                    c_id = comp.library_component_id or comp.failure_rate_id or (comp.snapshot and comp.snapshot.get("library_component_id"))
                    snapshot = None
                    if c_id:
                        snapshot = ComponentLibraryService.get_exida_component_snapshot(c_id, profile=new_profile)
                    if not snapshot and comp.type:
                        resolved = ComponentLibraryService.resolve_component(comp.type, profile=new_profile)
                        if resolved and resolved.get("source_type") == "exida":
                            snapshot = resolved
                            
                    if snapshot:
                        comp.selected_profile = new_profile
                        comp.failure_rate = snapshot.get("failure_rate")
                        comp.failure_modes = dict(snapshot.get("failure_modes", {}))
                        comp.snapshot = snapshot
                        
                        new_fms = snapshot.get("failure_modes", {})
                        for a in comp.failure_mode_assignments:
                            if a.failure_mode_name in new_fms:
                                a.failure_rate_percentage = new_fms[a.failure_mode_name]
                                
        # Update project selected_profile and environmental_profile
        self.project.selected_profile = new_profile
        self.project.environmental_profile = new_profile
        
        # Recalculate affected functional groups and project metrics
        CalculationService.calculate_project(self.project)
        
        # Log change
        ProjectService.log_change(
            self.project,
            "Change Environmental Profile",
            f"Environmental profile changed from '{current_profile}' to '{new_profile}'. Profile-dependent FIT values updated."
        )
        
        # Reload project in editor to update all unit tabs and overview
        self.main_editor.load_project(self.project)
        
        # Emit project changed signal
        self.main_editor.project_changed.emit()

    def _on_reviewer_changed(self):
        if not self.project or getattr(self.main_editor, "is_loading_project", False):
            return
        old_val = self.project.reviewer
        new_val = self.reviewer_input.text().strip()
        if old_val != new_val:
            self.project.reviewer = new_val or None
            from fmeda_tool.services.project_service import ProjectService
            ProjectService.log_change(
                self.project,
                "Update Reviewer",
                f"Assigned reviewer changed from '{old_val or 'None'}' to '{new_val or 'None'}'."
            )
            self.main_editor.project_changed.emit()
            
    def _on_status_changed(self, idx: int):
        if not self.project or getattr(self.main_editor, "is_loading_project", False):
            return
        new_status = self.status_combo.itemData(idx)
        old_status = self.project.status.value if self.project.status else "draft"
        
        if new_status == old_status:
            return
            
        if new_status == "completed":
            reviewer_name = self.reviewer_input.text().strip()
            if not reviewer_name:
                self.status_combo.blockSignals(True)
                prev_idx = self.status_combo.findData(old_status)
                if prev_idx >= 0:
                    self.status_combo.setCurrentIndex(prev_idx)
                self.status_combo.blockSignals(False)
                
                QMessageBox.warning(
                    self,
                    "Reviewer Name Required",
                    "A reviewer name must be entered before the project status can be changed to Approved."
                )
                return
            
            from datetime import datetime
            self.project.completed_at = datetime.now()
            
        from fmeda_tool.models.project import ProjectStatus
        self.project.status = ProjectStatus(new_status)
        
        from fmeda_tool.services.project_service import ProjectService
        ProjectService.log_change(
            self.project,
            "Change Status",
            f"Project status changed from '{old_status}' to '{new_status}'."
        )
        self.main_editor.project_changed.emit()

    def _on_view_history(self):
        dialog = ChangeHistoryDialog(self.project, self)
        dialog.exec()


class TableItemProxy:
    """Proxy object allowing legacy code and tests to access cell values as table.item(r, c).text()."""
    def __init__(self, model: FmedaTableModel, row: int, col: int):
        self.model = model
        self.row = row
        self.col = col

    def text(self) -> str:
        idx = self.model.index(self.row, self.col)
        return str(self.model.data(idx, Qt.ItemDataRole.DisplayRole) or "")

    def data(self, role: int = Qt.ItemDataRole.UserRole) -> Any:
        if self.row < 0 or self.row >= len(self.model.rows):
            return None
        entry = self.model.rows[self.row]
        if role == Qt.ItemDataRole.UserRole:
            if self.col == 0:
                return entry.component
            elif self.col == 6:
                return entry.assignment
        idx = self.model.index(self.row, self.col)
        return self.model.data(idx, role)


class FmedaTableView(QTableView):
    """
    Excel-style QTableView for FMEDA spreadsheet supporting component-block selection,
    multi-block selection (Ctrl/Shift), Ctrl+A, right-click context menus, and strict View Mode locks.
    """
    def __init__(self, parent_tab, parent=None):
        super().__init__(parent or parent_tab)
        self.parent_tab = parent_tab
        self.selected_component_ids: Set[str] = set()
        self.anchor_component_id: Optional[str] = None
        
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # Backward compatibility helpers on table instance
        self.item = lambda r, c: TableItemProxy(self.model(), r, c) if self.model() else None
        self.rowCount = lambda: self.model().rowCount() if self.model() else 0
        self.columnCount = lambda: self.model().columnCount() if self.model() else 0
        self.cellWidget = lambda r, c: None
        
        # Enhanced selection styling that keeps validation icons and subtle tints readable
        self.setStyleSheet("""
            QTableView {
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
                gridline-color: #dee2e6;
            }
            QTableView::item:selected {
                background-color: #dbeafe;
                color: #0f172a;
            }
        """)

    def is_in_edit_mode(self) -> bool:
        return bool(self.parent_tab and getattr(self.parent_tab, "is_in_edit_mode", False))

    def clear_component_selection(self):
        self.selected_component_ids.clear()
        self.anchor_component_id = None
        self.update_visual_selection()

    def select_all_components(self):
        if not self.is_in_edit_mode():
            return
        m = self.model()
        if not m or not hasattr(m, "rows"):
            return
        all_ids = m.get_distinct_component_ids() if hasattr(m, "get_distinct_component_ids") else []
        if not all_ids:
            all_ids = []
            for entry in m.rows:
                if not entry.is_separator and entry.component and entry.component.id:
                    if entry.component.id not in all_ids:
                        all_ids.append(entry.component.id)
        self.selected_component_ids = set(all_ids)
        if all_ids:
            self.anchor_component_id = all_ids[0]
        self.update_visual_selection()

    def update_visual_selection(self):
        m = self.model()
        sm = self.selectionModel()
        if not m or not sm or not hasattr(m, "rows"):
            return

        sm.blockSignals(True)
        sm.clearSelection()

        # In View Mode, no component-block selection is visualized
        if not self.is_in_edit_mode() or not self.selected_component_ids:
            sm.blockSignals(False)
            self.viewport().update()
            return

        sel = QItemSelection()
        col_count = m.columnCount()
        for r_idx, entry in enumerate(m.rows):
            if not entry.is_separator and entry.component and entry.component.id in self.selected_component_ids:
                top_left = m.index(r_idx, 0)
                bottom_right = m.index(r_idx, col_count - 1)
                sel.select(top_left, bottom_right)

        sm.select(sel, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        sm.blockSignals(False)
        self.viewport().update()

    def mousePressEvent(self, event: QMouseEvent):
        # 1. Right-Click
        if event.button() == Qt.MouseButton.RightButton:
            if not self.is_in_edit_mode():
                # Locked View Mode: right-click does nothing, do not open menu
                event.accept()
                return
            
            # Edit Mode right-click
            pos = event.position().toPoint()
            idx = self.indexAt(pos)
            if not idx.isValid():
                event.accept()
                return
                
            m = self.model()
            if not m or not hasattr(m, "rows") or idx.row() < 0 or idx.row() >= len(m.rows):
                event.accept()
                return
                
            entry = m.rows[idx.row()]
            if entry.is_separator or not entry.component:
                event.accept()
                return
                
            comp_id = entry.component.id
            if comp_id not in self.selected_component_ids:
                self.selected_component_ids = {comp_id}
                self.anchor_component_id = comp_id
                self.update_visual_selection()
                
            # Trigger context menu
            self.parent_tab.show_component_context_menu(event.globalPosition().toPoint())
            event.accept()
            return

        # 2. Left-Click
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.is_in_edit_mode():
                # View Mode: standard navigation, clear any multi-selection
                self.selected_component_ids.clear()
                self.anchor_component_id = None
                super().mousePressEvent(event)
                return

            # Edit Mode Left-Click
            pos = event.position().toPoint()
            idx = self.indexAt(pos)
            if not idx.isValid():
                super().mousePressEvent(event)
                return

            m = self.model()
            if not m or not hasattr(m, "rows") or idx.row() < 0 or idx.row() >= len(m.rows):
                super().mousePressEvent(event)
                return

            entry = m.rows[idx.row()]
            if entry.is_separator or not entry.component:
                # Separator clicked: cannot be selected
                event.accept()
                return

            comp_id = entry.component.id
            mods = event.modifiers()

            if mods & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+Click: Toggle component block
                if comp_id in self.selected_component_ids:
                    self.selected_component_ids.remove(comp_id)
                else:
                    self.selected_component_ids.add(comp_id)
                    self.anchor_component_id = comp_id
            elif (mods & Qt.KeyboardModifier.ShiftModifier) and self.anchor_component_id:
                # Shift+Click: Continuous range of component blocks
                all_ids = m.get_distinct_component_ids() if hasattr(m, "get_distinct_component_ids") else []
                if not all_ids:
                    all_ids = []
                    for e in m.rows:
                        if not e.is_separator and e.component and e.component.id and e.component.id not in all_ids:
                            all_ids.append(e.component.id)

                if self.anchor_component_id in all_ids and comp_id in all_ids:
                    i1 = all_ids.index(self.anchor_component_id)
                    i2 = all_ids.index(comp_id)
                    start_i, end_i = min(i1, i2), max(i1, i2)
                    self.selected_component_ids = set(all_ids[start_i:end_i+1])
                else:
                    self.selected_component_ids = {comp_id}
                    self.anchor_component_id = comp_id
            else:
                # Plain Click: Select single component block
                self.selected_component_ids = {comp_id}
                self.anchor_component_id = comp_id

            self.update_visual_selection()
            # Call super so cell focus/editing triggers (double click) work properly
            super().mousePressEvent(event)
            return

        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if not self.is_in_edit_mode():
            # View Mode: Suppress mutating keys & bulk select
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                event.accept()
                return
            if event.key() == Qt.Key.Key_A and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                event.accept()
                return
            super().keyPressEvent(event)
            return

        # Edit Mode
        if event.key() == Qt.Key.Key_A and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.select_all_components()
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.selected_component_ids:
                self.parent_tab.delete_selected_components()
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Escape:
            self.clear_component_selection()
            event.accept()
            return

        super().keyPressEvent(event)


class FunctionalGroupTab(QWidget):
    """
    Workspace tab representing a single Functional Group (Unit).
    Uses FmedaTableView + FmedaTableModel with lightweight delegates and Locked View Mode.
    """
    
    def __init__(self, unit: Unit, project: Project, main_editor, parent=None):
        super().__init__(parent)
        self.unit = unit
        self.project = project
        self.main_editor = main_editor
        self.is_populated = False
        self.is_dirty = False
        self.ui_initialized = False
        self.is_in_edit_mode = False
        self.unit_snapshot: Optional[Dict[str, Any]] = None
        self.model: Optional[FmedaTableModel] = None
        self.table: Optional[FmedaTableView] = None
        self._setup_ui()
        
    def _setup_ui(self, timer: Optional[PerformanceTimer] = None):
        """Constructs tab UI elements."""
        if self.ui_initialized:
            return
            
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Toolbar
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(8)
        
        # View / Edit Mode Indicator badge
        self.mode_badge = QLabel("🔒 View Mode (Locked)")
        self.mode_badge.setStyleSheet("background-color: #e9ecef; color: #495057; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: 1px solid #ced4da;")
        self.toolbar.addWidget(self.mode_badge)
        
        # Enable Editing button
        self.toggle_edit_btn = QPushButton("✏️ Enable Editing")
        self.toggle_edit_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.toggle_edit_btn.clicked.connect(self.enable_editing)
        self.toolbar.addWidget(self.toggle_edit_btn)
        
        # Confirm and Cancel Changes buttons (hidden by default in View Mode)
        self.confirm_edit_btn = QPushButton("💾 Confirm Changes")
        self.confirm_edit_btn.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.confirm_edit_btn.clicked.connect(self.confirm_changes)
        self.confirm_edit_btn.hide()
        self.toolbar.addWidget(self.confirm_edit_btn)
        
        self.cancel_edit_btn = QPushButton("❌ Cancel Changes")
        self.cancel_edit_btn.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.cancel_edit_btn.clicked.connect(self.cancel_changes)
        self.cancel_edit_btn.hide()
        self.toolbar.addWidget(self.cancel_edit_btn)
        
        div_bar = QFrame()
        div_bar.setFrameShape(QFrame.Shape.VLine)
        div_bar.setStyleSheet("color: #ced4da;")
        self.toolbar.addWidget(div_bar)
        
        self.map_bom_btn = QPushButton("Component & BOM Mapping")
        self.manage_dev_btn = QPushButton("Manage Deviations")
        self.manage_mit_btn = QPushButton("Manage Mitigations")
        self.manage_dm_btn = QPushButton("Manage Diagnostic Measures")
        self.calculate_btn = QPushButton("Calculate Group")
        
        for btn in [
            self.map_bom_btn, self.manage_dev_btn, self.manage_mit_btn,
            self.manage_dm_btn, self.calculate_btn
        ]:
            btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px 12px; border-radius: 4px;")
            self.toolbar.addWidget(btn)
            
        self.toolbar.addStretch()
        layout.addLayout(self.toolbar)
        
        self.map_bom_btn.clicked.connect(self._on_component_bom_mapping)
        self.manage_dev_btn.clicked.connect(self._on_manage_deviations_clicked)
        self.manage_mit_btn.clicked.connect(self._on_manage_mitigations_clicked)
        self.manage_dm_btn.clicked.connect(self._on_manage_dm_clicked)
        self.calculate_btn.clicked.connect(self._on_calculate_clicked)
        
        self.stacked_view = QStackedWidget()
        layout.addWidget(self.stacked_view)
        
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(8)
        
        group_layout = QHBoxLayout()
        group_layout.setContentsMargins(5, 5, 5, 0)
        group_layout.addWidget(QLabel("<b>Show Column Groups:</b>"))
        
        self.cb_bom = QCheckBox("Component/BOM")
        self.cb_bom.setChecked(True)
        self.cb_bom.stateChanged.connect(self._toggle_column_groups)
        group_layout.addWidget(self.cb_bom)
        
        self.cb_fail = QCheckBox("Failure Model")
        self.cb_fail.setChecked(True)
        self.cb_fail.stateChanged.connect(self._toggle_column_groups)
        group_layout.addWidget(self.cb_fail)
        
        self.cb_eng = QCheckBox("Manual Engineering")
        self.cb_eng.setChecked(True)
        self.cb_eng.stateChanged.connect(self._toggle_column_groups)
        group_layout.addWidget(self.cb_eng)
        
        self.cb_proof = QCheckBox("Proof-Test")
        self.cb_proof.setChecked(True)
        self.cb_proof.stateChanged.connect(self._toggle_column_groups)
        group_layout.addWidget(self.cb_proof)
        
        self.cb_calc = QCheckBox("Calculated Result")
        self.cb_calc.setChecked(True)
        self.cb_calc.stateChanged.connect(self._toggle_column_groups)
        group_layout.addWidget(self.cb_calc)
        
        group_layout.addStretch()
        table_layout.addLayout(group_layout)
        
        # FmedaTableView and FmedaTableModel (37 Columns)
        self.table = FmedaTableView(parent_tab=self)
        self.model = FmedaTableModel(self.unit, self.project, auto_populate=False, parent=self)
        self.table.setModel(self.model)
        
        # Attach custom lightweight delegates
        self.combo_delegate = FmedaComboBoxDelegate(parent=self.table)
        self.spin_delegate = FmedaSpinBoxDelegate(parent=self.table)
        self.text_delegate = FmedaLineEditDelegate(parent=self.table)
        
        for col in (9, 11, 14, 17, 19):
            self.table.setItemDelegateForColumn(col, self.combo_delegate)
            
        for col in (7, 12, 13, 15, 20, 21, 22):
            self.table.setItemDelegateForColumn(col, self.spin_delegate)
            
        for col in (2, 3, 4, 10, 18):
            self.table.setItemDelegateForColumn(col, self.text_delegate)
            
        # Hide col 16 (DC Test Ref)
        self.table.setColumnHidden(16, True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        
        table_layout.addWidget(self.table)
        
        # Comprehensive Legend with Entry Origin & Validation Indicators
        legend = QFrame()
        legend.setStyleSheet("background-color: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;")
        legend.setFixedHeight(38)
        leg_lay = QHBoxLayout(legend)
        leg_lay.setContentsMargins(15, 0, 15, 0)
        leg_lay.addWidget(QLabel("<b>Input Origin:</b>"))
        leg_lay.addWidget(QLabel("<span style='background-color:#fffdf0; border:1px solid #ffe69c; padding:2px 6px; border-radius:3px;'>🟨 Manual</span>"))
        leg_lay.addWidget(QLabel("<span style='background-color:#f0f7ff; border:1px solid #b6d4fe; padding:2px 6px; border-radius:3px;'>🟦 Library</span>"))
        leg_lay.addWidget(QLabel("<span style='background-color:#f2faf2; border:1px solid #b7eb8f; padding:2px 6px; border-radius:3px;'>🟩 BOM</span>"))
        leg_lay.addWidget(QLabel("<span style='background-color:#f8f9fa; border:1px solid #ced4da; padding:2px 6px; border-radius:3px;'>⬜ Calculated</span>"))
        
        div_leg = QFrame()
        div_leg.setFrameShape(QFrame.Shape.VLine)
        div_leg.setStyleSheet("color: #ced4da;")
        leg_lay.addWidget(div_leg)
        
        leg_lay.addWidget(QLabel("<b>Validation:</b>"))
        leg_lay.addWidget(QLabel("🟢 Pass"))
        leg_lay.addWidget(QLabel("🟡 Warning"))
        leg_lay.addWidget(QLabel("🔴 Error"))
        leg_lay.addStretch()
        table_layout.addWidget(legend)
        
        self.stacked_view.addWidget(table_container)
        
        if timer:
            timer.start_phase("canvas_or_hidden_view_construction")
        self.canvas = ComponentCanvas(self)
        self.canvas.add_component_requested.connect(self._on_add_component_at_position)
        self.stacked_view.addWidget(self.canvas)
        if timer:
            timer.end_phase("canvas_or_hidden_view_construction")
            
        self.stacked_view.setCurrentIndex(0)
        self.ui_initialized = True

    def enable_editing(self) -> bool:
        """Enters Edit Mode for this functional group tab."""
        if self.is_in_edit_mode:
            return True
            
        if self.main_editor:
            for idx in range(self.main_editor.unit_tabs.count()):
                widget = self.main_editor.unit_tabs.widget(idx)
                if isinstance(widget, FunctionalGroupTab) and widget != self and widget.is_in_edit_mode:
                    QMessageBox.warning(
                        self,
                        "Editing Lock",
                        f"Functional group '{widget.unit.name}' is currently in Edit Mode.\n"
                        "Please confirm or cancel changes in that group before editing another group."
                    )
                    return False
                    
        self.ensure_populated()
        self.unit_snapshot = self.unit.model_dump(mode='json')
        self.is_in_edit_mode = True
        if self.table:
            self.table.clear_component_selection()
        if self.model:
            self.model.set_edit_mode(True)
        self._update_edit_mode_ui()
        return True

    def confirm_changes(self) -> None:
        """Validates, recalculates, commits single coherent Undo state, and returns to View Mode."""
        if not self.is_in_edit_mode:
            return
            
        if self.table:
            self.table.clear_component_selection()
            self.table.setFocus()
        
        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)
        
        if self.model:
            self.model.refresh_all_metrics()
            self.model.set_edit_mode(False)
            
        if self.main_editor and hasattr(self.main_editor, "main_window") and self.main_editor.main_window:
            self.main_editor.main_window.push_undo_state(f"Edit FMEDA Table: {self.unit.name}")
            
        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()
            
        self.unit_snapshot = None
        self.is_in_edit_mode = False
        self._update_edit_mode_ui()

    def cancel_changes(self) -> None:
        """Restores functional group state before editing, discards edits, and returns to View Mode."""
        if not self.is_in_edit_mode:
            return
            
        if self.table:
            self.table.clear_component_selection()
            self.table.setFocus()
        
        if self.unit_snapshot:
            restored = Unit.model_validate(self.unit_snapshot)
            self.unit.components = restored.components
            self.unit.name = restored.name
            self.unit.description = restored.description
            self.unit.notes = restored.notes
            self.unit.bom_components = getattr(restored, "bom_components", [])
            if hasattr(restored, "component_templates"):
                self.unit.component_templates = restored.component_templates
            
        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)
        
        if self.model:
            self.model.reload_data()
            self.model.set_edit_mode(False)
            
        self.unit_snapshot = None
        self.is_in_edit_mode = False
        self._update_edit_mode_ui()

    def clear_component_selection(self):
        """Clears selection in the table."""
        if self.table:
            self.table.clear_component_selection()

    def _update_edit_mode_ui(self) -> None:
        """Updates toolbar badges and buttons based on edit mode."""
        if self.is_in_edit_mode:
            self.mode_badge.setText("✏️ Edit Mode (Unconfirmed)")
            self.mode_badge.setStyleSheet("background-color: #fff3cd; color: #664d03; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: 1px solid #ffecb5;")
            self.toggle_edit_btn.hide()
            self.confirm_edit_btn.show()
            self.cancel_edit_btn.show()
        else:
            self.mode_badge.setText("🔒 View Mode (Locked)")
            self.mode_badge.setStyleSheet("background-color: #e9ecef; color: #495057; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: 1px solid #ced4da;")
            self.toggle_edit_btn.show()
            self.confirm_edit_btn.hide()
            self.cancel_edit_btn.hide()

    def ensure_populated(self, timer: Optional[PerformanceTimer] = None, reason: str = "initial"):
        """Ensures tab UI and FMEDA table model are initialized and loaded."""
        if self.is_populated and not self.is_dirty:
            return
            
        if not self.ui_initialized:
            t0 = time.perf_counter()
            self._setup_ui(timer=timer)
            if timer:
                timer.log_lazy_event(self.unit.id, self.unit.name, "editor_created", duration_ms=(time.perf_counter()-t0)*1000)
                
        t0 = time.perf_counter()
        self._load_fmeda_table(timer=timer, reason=reason)
        self.is_populated = True
        self.is_dirty = False
        
        if timer:
            row_cnt = self.model.rowCount() if self.model else 0
            timer.log_lazy_event(self.unit.id, self.unit.name, "table_populated", row_count=row_cnt, duration_ms=(time.perf_counter()-t0)*1000, reason=reason)

    def _toggle_view(self):
        cur = self.stacked_view.currentIndex()
        new_idx = 1 - cur
        self.stacked_view.setCurrentIndex(new_idx)
        if new_idx == 0:
            self.ensure_populated(reason="view_toggle")
        elif new_idx == 1:
            self._load_components_to_canvas()

    def _toggle_column_groups(self):
        show_bom = self.cb_bom.isChecked()
        for c in range(0, 6):
            self.table.setColumnHidden(c, not show_bom)

        show_fail = self.cb_fail.isChecked()
        for c in range(6, 9):
            self.table.setColumnHidden(c, not show_fail)

        show_eng = self.cb_eng.isChecked()
        for c in range(9, 20):
            self.table.setColumnHidden(c, not show_eng)

        self.table.setColumnHidden(16, True)  # DC Test Ref always hidden

        show_proof = self.cb_proof.isChecked()
        for c in range(20, 24):
            self.table.setColumnHidden(c, not show_proof)

        show_calc = self.cb_calc.isChecked()
        for c in range(24, 37):
            self.table.setColumnHidden(c, not show_calc)

    def show_component_context_menu(self, global_pos: QPoint):
        """Builds and executes the context menu for single vs multi-component selection in Edit Mode."""
        if not self.is_in_edit_mode:
            return

        if not self.table or not self.table.selected_component_ids:
            return

        sel_ids = [cid for cid in self.table.selected_component_ids if any(c.id == cid for c in self.unit.components)]
        if not sel_ids:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #0d6efd;
                color: white;
            }
        """)

        if len(sel_ids) == 1:
            # Single component selected
            comp_id = sel_ids[0]
            act_edit = menu.addAction("✏️ Edit Component")
            act_dup = menu.addAction("📋 Duplicate Component")
            act_view = menu.addAction("🔍 View Component Details")
            menu.addSeparator()
            act_del = menu.addAction("🗑️ Delete Component")

            action = menu.exec(global_pos)
            if not action:
                return

            if action == act_edit:
                self.edit_component(comp_id)
            elif action == act_dup:
                self.duplicate_component(comp_id)
            elif action == act_view:
                self.view_component_details(comp_id)
            elif action == act_del:
                self.delete_selected_components()

        else:
            # Multiple components selected
            act_dev = menu.addAction("⚡ Assign Deviation")
            act_dm = menu.addAction("⚡ Assign Diagnostic Measure")
            act_mit = menu.addAction("⚡ Assign Mitigation")
            act_class = menu.addAction("⚡ Set Classification")
            menu.addSeparator()
            act_del = menu.addAction(f"🗑️ Delete Selected Components ({len(sel_ids)})")

            action = menu.exec(global_pos)
            if not action:
                return

            if action == act_dev:
                self.bulk_assign_deviation()
            elif action == act_dm:
                self.bulk_assign_diagnostic_measure()
            elif action == act_mit:
                self.bulk_assign_mitigation()
            elif action == act_class:
                self.bulk_set_classification()
            elif action == act_del:
                self.delete_selected_components()

    # ---------------------------------------------------------
    # Single Component Modifying Handlers (Guarded by Edit Mode)
    # ---------------------------------------------------------
    def edit_component(self, comp_id: Optional[str] = None) -> bool:
        """Opens ComponentInstanceDialog to edit single component properties."""
        if not self.is_in_edit_mode:
            return False

        if comp_id is None and self.table and self.table.selected_component_ids:
            comp_id = next(iter(self.table.selected_component_ids))

        target_comp = next((c for c in self.unit.components if c.id == comp_id), None)
        if not target_comp:
            return False

        dialog = ComponentInstanceDialog(target_comp, self.project, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            from fmeda_tool.services.calculation_service import CalculationService
            CalculationService.calculate_project(self.project)
            if self.model:
                self.model.refresh_all_metrics()
            if self.table:
                self.table.update_visual_selection()
            if self.main_editor and hasattr(self.main_editor, "project_changed"):
                self.main_editor.project_changed.emit()
            return True
        return False

    def duplicate_component(self, comp_id: Optional[str] = None) -> bool:
        """Creates an independent clone of the selected component with a new unique designator."""
        if not self.is_in_edit_mode:
            return False

        if comp_id is None and self.table and self.table.selected_component_ids:
            comp_id = next(iter(self.table.selected_component_ids))

        source_comp = next((c for c in self.unit.components if c.id == comp_id), None)
        if not source_comp:
            return False

        existing_pos = [c.position for c in self.unit.components if c.position]
        dialog = DuplicateComponentDialog(source_comp, existing_pos, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        new_pos = dialog.get_new_position()
        if not new_pos:
            return False

        # Clone component
        new_comp = Component(
            id=f"comp_{uuid.uuid4().hex[:8]}",
            position=new_pos,
            name=source_comp.name,
            type=source_comp.type,
            failure_rate=source_comp.failure_rate,
            function=source_comp.function,
            value=source_comp.value,
            internal_pn=source_comp.internal_pn,
            failure_modes=dict(source_comp.failure_modes or {}),
            component_subtype=source_comp.component_subtype,
            component_use_category=source_comp.component_use_category,
            selected_profile=source_comp.selected_profile,
            source_type=source_comp.source_type,
            library_component_id=source_comp.library_component_id,
            failure_rate_id=source_comp.failure_rate_id,
            item_no=source_comp.item_no,
            snapshot=copy.deepcopy(source_comp.snapshot) if source_comp.snapshot else None,
            failure_mode_assignments=[
                FailureModeAssignment(
                    failure_mode_name=a.failure_mode_name,
                    failure_rate_percentage=a.failure_rate_percentage,
                    deviation_id=a.deviation_id,
                    diagnostic_measure_id=a.diagnostic_measure_id,
                    mitigation_id=a.mitigation_id,
                    classification=a.classification,
                    detection_percentage=a.detection_percentage,
                    dangerous_failure_percentage=a.dangerous_failure_percentage,
                    notes=a.notes,
                    diagnostic_function=a.diagnostic_function,
                    proof_test_a=a.proof_test_a,
                    proof_test_b=a.proof_test_b,
                    proof_test_c=a.proof_test_c,
                    dont_care=a.dont_care
                ) for a in source_comp.failure_mode_assignments
            ]
        )

        src_idx = self.unit.components.index(source_comp)
        self.unit.components.insert(src_idx + 1, new_comp)

        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)

        if self.model:
            self.model.reload_data()

        if self.table:
            self.table.selected_component_ids = {new_comp.id}
            self.table.anchor_component_id = new_comp.id
            self.table.update_visual_selection()
            if self.model:
                rows = self.model.get_row_indices_for_component(new_comp.id)
                if rows:
                    self.table.scrollTo(self.model.index(rows[0], 0))

        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()
        return True

    def view_component_details(self, comp_id: Optional[str] = None) -> bool:
        """Opens read-only ComponentDetailsDialog."""
        if comp_id is None and self.table and self.table.selected_component_ids:
            comp_id = next(iter(self.table.selected_component_ids))

        target_comp = next((c for c in self.unit.components if c.id == comp_id), None)
        if not target_comp:
            return False

        dialog = ComponentDetailsDialog(target_comp, self.unit, self.project, parent=self)
        dialog.exec()
        return True

    def delete_selected_components(self) -> bool:
        """Deletes selected components, releases associated BOM positions, and updates model."""
        if not self.is_in_edit_mode:
            return False

        if not self.table or not self.table.selected_component_ids:
            return False

        comps_to_del = [c for c in self.unit.components if c.id in self.table.selected_component_ids]
        if not comps_to_del:
            return False

        dialog = DeleteComponentsConfirmDialog(comps_to_del, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        # Identify nearest remaining component to keep visible
        remaining = [c for c in self.unit.components if c.id not in self.table.selected_component_ids]
        nearest_comp = remaining[0] if remaining else None

        if self.main_editor and hasattr(self.main_editor, "main_window") and self.main_editor.main_window:
            self.main_editor.main_window.push_undo_state(f"Delete {len(comps_to_del)} Components: {self.unit.name}")

        self.unit.components = remaining
        self.table.selected_component_ids.clear()
        self.table.anchor_component_id = None

        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)

        if self.model:
            self.model.reload_data()

        if nearest_comp and self.model and self.table:
            rows = self.model.get_row_indices_for_component(nearest_comp.id)
            if rows:
                self.table.scrollTo(self.model.index(rows[0], 0))

        if self.table:
            self.table.update_visual_selection()

        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()
        return True

    # ---------------------------------------------------------
    # Bulk Modifying Handlers (Guarded by Edit Mode & Atomic)
    # ---------------------------------------------------------
    def bulk_assign_deviation(self, selected_dev_id: Optional[str] = "PROMPT") -> bool:
        """Bulk assigns deviation to all failure-mode rows across selected components."""
        if not self.is_in_edit_mode:
            return False

        if not self.table or not self.table.selected_component_ids:
            return False

        comps = [c for c in self.unit.components if c.id in self.table.selected_component_ids]
        if not comps:
            return False

        if selected_dev_id == "PROMPT":
            dev_items = [(d.name, d.effect or d.description, d.id) for d in self.project.deviations]
            picker = BulkItemPickerDialog("Assign Deviation", "Deviation", dev_items, allow_create_new=True, parent=self)
            if picker.exec() != QDialog.DialogCode.Accepted:
                return False

            if picker.create_new_requested:
                dlg = DeviationDialog(unit_name=self.unit.name, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted and dlg.deviation:
                    if dlg.deviation not in self.project.deviations:
                        self.project.deviations.append(dlg.deviation)
                    dev_id = dlg.deviation.id
                    dev_label = dlg.deviation.name
                else:
                    return False
            else:
                dev_id, dev_label = picker.get_selection()
        else:
            dev_id = selected_dev_id
            dev_obj = next((d for d in self.project.deviations if d.id == dev_id), None)
            dev_label = dev_obj.name if dev_obj else ("Clear Deviation" if not dev_id else dev_id)

        affected_rows = sum(len(c.failure_mode_assignments) for c in comps)
        des_list = [c.position for c in comps]

        summary = BulkActionSummaryDialog(
            "Confirm Bulk Assignment", "Assign Deviation",
            dev_label or "Clear Deviation", len(comps), affected_rows, des_list, parent=self
        )
        if summary.exec() != QDialog.DialogCode.Accepted:
            return False

        if self.main_editor and hasattr(self.main_editor, "main_window") and self.main_editor.main_window:
            self.main_editor.main_window.push_undo_state(f"Bulk Assign Deviation '{dev_label}' ({self.unit.name})")

        for c in comps:
            for a in c.failure_mode_assignments:
                a.deviation_id = dev_id

        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)

        if self.model:
            self.model.refresh_all_metrics()
        if self.table:
            self.table.update_visual_selection()
        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()
        return True

    def bulk_assign_diagnostic_measure(self, selected_dm_id: Optional[str] = "PROMPT") -> bool:
        """Bulk assigns diagnostic measure and DC % to all failure-mode rows across selected components."""
        if not self.is_in_edit_mode:
            return False

        if not self.table or not self.table.selected_component_ids:
            return False

        comps = [c for c in self.unit.components if c.id in self.table.selected_component_ids]
        if not comps:
            return False

        if selected_dm_id == "PROMPT":
            dm_items = [(f"{dm.description} (DC: {dm.dc:.1f}%)", dm.notes or "", dm.id) for dm in self.project.diagnostic_measures]
            picker = BulkItemPickerDialog("Assign Diagnostic Measure", "Diagnostic Measure", dm_items, allow_create_new=True, parent=self)
            if picker.exec() != QDialog.DialogCode.Accepted:
                return False

            if picker.create_new_requested:
                dlg = DiagnosticMeasureMiniDialog(parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted and dlg.dm:
                    if dlg.dm not in self.project.diagnostic_measures:
                        self.project.diagnostic_measures.append(dlg.dm)
                    dm_id = dlg.dm.id
                    dm_label = f"{dlg.dm.description} (DC: {dlg.dm.dc:.1f}%)"
                else:
                    return False
            else:
                dm_id, dm_label = picker.get_selection()
        else:
            dm_id = selected_dm_id
            dm_obj = next((m for m in self.project.diagnostic_measures if m.id == dm_id), None)
            dm_label = f"{dm_obj.description} (DC: {dm_obj.dc:.1f}%)" if dm_obj else ("Clear Diagnostic Measure" if not dm_id else dm_id)

        affected_rows = sum(len(c.failure_mode_assignments) for c in comps)
        des_list = [c.position for c in comps]

        summary = BulkActionSummaryDialog(
            "Confirm Bulk Assignment", "Assign Diagnostic Measure",
            dm_label or "Clear Diagnostic Measure", len(comps), affected_rows, des_list, parent=self
        )
        if summary.exec() != QDialog.DialogCode.Accepted:
            return False

        if self.main_editor and hasattr(self.main_editor, "main_window") and self.main_editor.main_window:
            self.main_editor.main_window.push_undo_state(f"Bulk Assign Diagnostic Measure '{dm_label}' ({self.unit.name})")

        dm_obj = next((m for m in self.project.diagnostic_measures if m.id == dm_id), None) if dm_id else None
        for c in comps:
            for a in c.failure_mode_assignments:
                a.diagnostic_measure_id = dm_id
                if dm_obj:
                    a.detection_percentage = dm_obj.dc
                elif dm_id is None:
                    a.detection_percentage = 0.0

        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)

        if self.model:
            self.model.refresh_all_metrics()
        if self.table:
            self.table.update_visual_selection()
        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()
        return True

    def bulk_assign_mitigation(self, selected_mit_id: Optional[str] = "PROMPT") -> bool:
        """Bulk assigns mitigation to all failure-mode rows across selected components."""
        if not self.is_in_edit_mode:
            return False

        if not self.table or not self.table.selected_component_ids:
            return False

        comps = [c for c in self.unit.components if c.id in self.table.selected_component_ids]
        if not comps:
            return False

        if selected_mit_id == "PROMPT":
            mit_items = [(mit.name or mit.id, mit.description or "", mit.id) for mit in self.project.mitigations]
            picker = BulkItemPickerDialog("Assign Mitigation", "Mitigation", mit_items, allow_create_new=True, parent=self)
            if picker.exec() != QDialog.DialogCode.Accepted:
                return False

            if picker.create_new_requested:
                dlg = MitigationDialog(unit_name=self.unit.name, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted and getattr(dlg, "saved_mitigation", None):
                    if dlg.saved_mitigation not in self.project.mitigations:
                        self.project.mitigations.append(dlg.saved_mitigation)
                    mit_id = dlg.saved_mitigation.id
                    mit_label = dlg.saved_mitigation.name
                else:
                    return False
            else:
                mit_id, mit_label = picker.get_selection()
        else:
            mit_id = selected_mit_id
            mit_obj = next((m for m in self.project.mitigations if m.id == mit_id), None)
            mit_label = mit_obj.name if mit_obj else ("Clear Mitigation" if not mit_id else mit_id)

        affected_rows = sum(len(c.failure_mode_assignments) for c in comps)
        des_list = [c.position for c in comps]

        summary = BulkActionSummaryDialog(
            "Confirm Bulk Assignment", "Assign Mitigation",
            mit_label or "Clear Mitigation", len(comps), affected_rows, des_list, parent=self
        )
        if summary.exec() != QDialog.DialogCode.Accepted:
            return False

        if self.main_editor and hasattr(self.main_editor, "main_window") and self.main_editor.main_window:
            self.main_editor.main_window.push_undo_state(f"Bulk Assign Mitigation '{mit_label}' ({self.unit.name})")

        for c in comps:
            for a in c.failure_mode_assignments:
                a.mitigation_id = mit_id

        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)

        if self.model:
            self.model.refresh_all_metrics()
        if self.table:
            self.table.update_visual_selection()
        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()
        return True

    def bulk_set_classification(self, selected_classif: Optional[str] = "PROMPT") -> bool:
        """Bulk sets failure classification across all failure-mode rows of selected components."""
        if not self.is_in_edit_mode:
            return False

        if not self.table or not self.table.selected_component_ids:
            return False

        comps = [c for c in self.unit.components if c.id in self.table.selected_component_ids]
        if not comps:
            return False

        if selected_classif == "PROMPT":
            class_items = [
                ("Not Evaluated", "Default unclassified status", "not_evaluated"),
                ("Safe Failure", "Sets dangerous failure % to 0.0%", "safe_failure"),
                ("Dangerous Failure", "Sets dangerous failure % to 100.0%", "dangerous_failure")
            ]
            picker = BulkItemPickerDialog("Set Classification", "Classification", class_items, parent=self)
            if picker.exec() != QDialog.DialogCode.Accepted:
                return False
            class_key, class_label = picker.get_selection()
        else:
            class_key = selected_classif
            class_label = {
                "not_evaluated": "Not Evaluated",
                "safe_failure": "Safe Failure",
                "dangerous_failure": "Dangerous Failure"
            }.get(class_key, class_key)

        affected_rows = sum(len(c.failure_mode_assignments) for c in comps)
        des_list = [c.position for c in comps]

        summary = BulkActionSummaryDialog(
            "Confirm Bulk Assignment", "Set Classification",
            class_label, len(comps), affected_rows, des_list, parent=self
        )
        if summary.exec() != QDialog.DialogCode.Accepted:
            return False

        if self.main_editor and hasattr(self.main_editor, "main_window") and self.main_editor.main_window:
            self.main_editor.main_window.push_undo_state(f"Bulk Set Classification '{class_label}' ({self.unit.name})")

        for c in comps:
            for a in c.failure_mode_assignments:
                a.classification = class_key
                if class_key == "safe_failure":
                    a.dangerous_failure_percentage = 0.0
                elif class_key == "dangerous_failure":
                    a.dangerous_failure_percentage = 100.0

        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)

        if self.model:
            self.model.refresh_all_metrics()
        if self.table:
            self.table.update_visual_selection()
        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()
        return True

    def _on_table_context_menu(self, pos):
        """Backward compatibility context menu event hook."""
        if not self.is_in_edit_mode:
            return
        if self.table:
            self.show_component_context_menu(self.table.viewport().mapToGlobal(pos))

    def _load_fmeda_table(self, timer: Optional[PerformanceTimer] = None, reason: str = "initial"):
        if timer:
            timer.counters.full_table_refresh_count += 1
            timer.start_phase("every_call_to_populate_or_refresh_table")
            
        try:
            if self.model:
                self.model.reload_data()
            self._toggle_column_groups()
        finally:
            if timer:
                timer.end_phase("every_call_to_populate_or_refresh_table")

    def _on_classif_changed(self, text: str, assignment: FailureModeAssignment, component: Component, row: int):
        """Helper for programmatic or test classification changes."""
        class_map = {
            "Not Evaluated": "not_evaluated",
            "Safe Failure": "safe_failure",
            "Dangerous Failure": "dangerous_failure"
        }
        assignment.classification = class_map.get(text, "not_evaluated")
        if assignment.classification == "safe_failure":
            assignment.dangerous_failure_percentage = 0.0
        elif assignment.classification == "dangerous_failure":
            assignment.dangerous_failure_percentage = 100.0
            
        if self.model:
            self.model.refresh_all_metrics()
        self._trigger_recalculation()

    def _trigger_recalculation(self):
        if getattr(self.main_editor, "is_loading_project", False):
            return
        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)
        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()

    def _on_import_bom_txt(self):
        existing_designators = (
            [c.position for c in self.unit.components] +
            [b.designator for b in self.unit.bom_components]
        )
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select BOM TXT File", "", "BOM Text Files (*.txt)"
        )
        if not filepath:
            return
            
        dialog = BOMImportDialog(existing_designators, filepath=filepath, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            imported = dialog.imported_components
            
            duplicates = []
            new_imports = []
            for comp in imported:
                if any(b.designator.upper() == comp.designator.upper() for b in self.unit.bom_components):
                    duplicates.append(comp.designator)
                else:
                    new_imports.append(comp)
            
            if duplicates:
                QMessageBox.warning(
                    self, "Duplicate Designators Ignored",
                    f"The following {len(duplicates)} designators are already present in the BOM and were skipped:\n"
                    f"{', '.join(duplicates)}"
                )
                
            if not new_imports:
                QMessageBox.information(
                    self, "No New Components",
                    "No new BOM components were added (all selected designators were duplicates)."
                )
                return
                
            self.unit.bom_components.extend(new_imports)
            self.main_editor.project_changed.emit()
            
            QMessageBox.information(
                self, "BOM Imported",
                f"Successfully added {len(new_imports)} components to this functional group.\n"
                "Opening BOM components mapping dialog..."
            )
            self._on_map_bom_components()
        
    def _on_component_bom_mapping(self):
        prof = getattr(self.project, "selected_profile", "Profile 1") if hasattr(self, "project") and self.project else "Profile 1"
        dialog = ComponentMappingDialog(self.unit, project_profile=prof, project=self.project, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            from fmeda_tool.services.calculation_service import CalculationService
            CalculationService.calculate_project(self.project)
            self._load_fmeda_table()
            
            if self.main_editor and hasattr(self.main_editor, "main_window") and self.main_editor.main_window:
                self.main_editor.main_window.push_undo_state(f"Component & BOM Mapping: {self.unit.name}")
                
            if self.main_editor and hasattr(self.main_editor, "project_changed"):
                self.main_editor.project_changed.emit()
                
            QMessageBox.information(
                self, "Mappings Saved",
                f"Component mappings saved and FMEDA rows generated successfully for '{self.unit.name}'!"
            )
            
    def _on_map_bom_components(self):
        """Backward compatibility alias for _on_component_bom_mapping."""
        self._on_component_bom_mapping()

    def _on_add_comp_type(self):
        prof = getattr(self.project, "selected_profile", "Profile 1") if hasattr(self, "project") and self.project else "Profile 1"
        dialog = ComponentSelectionDialog(project_profile=prof, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_component:
            comp = dialog.created_component
            template = ComponentDB(
                id=comp.library_component_id or comp.id,
                display_name=comp.type or comp.name,
                shortcut=comp.failure_rate_id or "",
                material=comp.type,
                fits=comp.failure_rate,
                database=comp.source_type or "exida",
                failure_modes=comp.failure_modes or {},
                library_component_id=comp.library_component_id,
                failure_rate_id=comp.failure_rate_id,
                item_no=comp.item_no,
                component_subtype=comp.component_subtype,
                component_use_category=comp.component_use_category,
                selected_profile=comp.selected_profile or prof,
                source_type=comp.source_type or "exida",
                snapshot=comp.snapshot
            )
            if not hasattr(self.unit, "component_templates") or self.unit.component_templates is None:
                self.unit.component_templates = []
                
            existing_tmpl = next((t for t in self.unit.component_templates if t.id == template.id or (t.display_name == template.display_name and t.shortcut == template.shortcut)), None)
            if not existing_tmpl:
                self.unit.component_templates.append(template)
                
            from fmeda_tool.services.project_service import ProjectService
            ProjectService.log_change(
                self.project,
                "Add Component Type",
                f"Added component template '{template.display_name}' ({template.fits or 0.0:.4f} FIT) to functional group '{self.unit.name}'."
            )
            if self.main_editor and hasattr(self.main_editor, "project_changed"):
                self.main_editor.project_changed.emit()
                
            QMessageBox.information(
                self, "Component Type Added",
                f"Component type '{template.display_name}' ({template.fits or 0.0:.4f} FIT) added as an available mapping template for '{self.unit.name}'.\n\n"
                "Click 'Map BOM' to batch assign BOM positions to this component type."
            )
        
    def _on_add_bom_man_clicked(self):
        from fmeda_tool.models.bom_component import BOMComponent
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Add BOM Component Manually")
        form = QFormLayout(dialog)
        
        des_input = QLineEdit()
        form.addRow("Designator*:", des_input)
        
        pn_input = QLineEdit()
        form.addRow("Part Number:", pn_input)
        
        val_input = QLineEdit()
        form.addRow("Value:", val_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            des = des_input.text().strip()
            if not des:
                QMessageBox.warning(self, "Error", "Designator is required.")
                return
                
            bom = BOMComponent(
                id=f"bom_{uuid.uuid4().hex[:8]}",
                designator=des,
                part_number=pn_input.text().strip(),
                value=val_input.text().strip() or None
            )
            if not hasattr(self.unit, "bom_components") or self.unit.bom_components is None:
                self.unit.bom_components = []
            self.unit.bom_components.append(bom)
            if self.main_editor and hasattr(self.main_editor, "project_changed"):
                self.main_editor.project_changed.emit()
            QMessageBox.information(self, "Success", f"BOM Component '{des}' added manually.")
            
    def _on_manage_deviations_clicked(self):
        unit_name = self.unit.name if hasattr(self, "unit") and self.unit else "Project / Global"
        dialog = DeviationManagerDialog(self.project, unit_name=unit_name, parent=self)
        dialog.exec()
        if hasattr(self, "stacked_view") and self.stacked_view.currentIndex() == 0 and self.is_populated:
            self._load_fmeda_table(reason="deviation_managed")
            
    def _on_manage_mitigations_clicked(self):
        unit_name = self.unit.name if hasattr(self, "unit") and self.unit else "Global / Project"
        dialog = MitigationManagerDialog(self.project, unit_name=unit_name, parent=self)
        dialog.exec()
        if hasattr(self, "stacked_view") and self.stacked_view.currentIndex() == 0 and self.is_populated:
            self._load_fmeda_table(reason="mitigation_managed")
            
    def _on_manage_dm_clicked(self):
        dialog = DiagnosticMeasureManagerDialog(self.project, self)
        dialog.exec()
        if hasattr(self, "stacked_view") and self.stacked_view.currentIndex() == 0 and self.is_populated:
            self._load_fmeda_table(reason="dm_managed")
            
    def _on_calculate_clicked(self):
        self._trigger_recalculation()
        if hasattr(self, "stacked_view") and self.stacked_view.currentIndex() == 0 and self.is_populated:
            self._load_fmeda_table()
        QMessageBox.information(self, "Calculate", "Calculations refreshed.")
        
    def _load_components_from_db(self):
        templates = []
        try:
            prof = getattr(self.project, "selected_profile", "Profile 1") if hasattr(self, "project") and self.project else "Profile 1"
            exida_comps = ComponentLibraryService.search_exida_components(profile=prof)
            for c in exida_comps:
                snap = ComponentLibraryService.get_exida_component_snapshot(c["id"], prof)
                if snap:
                    templates.append(ComponentDB(
                        id=snap["library_component_id"],
                        display_name=snap["displayed_label"],
                        shortcut=snap.get("failure_rate_id"),
                        material=snap.get("component_type"),
                        fits=snap.get("failure_rate"),
                        database="exida",
                        failure_modes=snap.get("failure_modes", {})
                    ))
            legacy_comps = ComponentLibraryService.search_legacy_components()
            for l in legacy_comps:
                snap = ComponentLibraryService.get_legacy_component_snapshot(l["id"])
                if snap:
                    templates.append(ComponentDB(
                        id=snap["library_component_id"],
                        display_name=snap["display_name"],
                        shortcut=snap.get("shortcut"),
                        material=snap.get("material"),
                        fits=snap.get("failure_rate"),
                        database="Legacy",
                        failure_modes=snap.get("failure_modes", {})
                    ))
        except Exception as e:
            print(f"Error loading components database from SQLite: {e}")
        return templates
        
    def _on_add_component_at_position(self, position: QPointF):
        prof = getattr(self.project, "selected_profile", "Profile 1") if hasattr(self, "project") and self.project else "Profile 1"
        dialog = ComponentSelectionDialog(project_profile=prof, parent=self)
        dialog.component_selected.connect(
            lambda component: self._add_component_to_canvas(component, position)
        )
        dialog.exec()
        
    def _add_component_to_canvas(self, component: Component, position: QPointF):
        component.x_position = position.x()
        component.y_position = position.y()
        
        self.unit.components.append(component)
        
        comp_db = ComponentDB(
            id=f"db_{component.id}",
            display_name=component.name,
            shortcut=component.position,
            material=component.type,
            fits=component.failure_rate,
            failure_modes=component.failure_modes
        )
        
        visual_item = ComponentGraphicsItem(comp_db, position.x(), position.y())
        visual_item.component_instance = component
        self.canvas.scene.addItem(visual_item)
        
        from fmeda_tool.services.project_service import ProjectService
        ProjectService.log_change(
            self.project,
            "Add Component",
            f"Added component '{component.position}' ({component.name}) to functional group '{self.unit.name}'."
        )
        
        if self.main_editor and hasattr(self.main_editor, "project_changed"):
            self.main_editor.project_changed.emit()
        self._load_fmeda_table()
        self._trigger_recalculation()
        
    def _on_component_clicked(self, component_item: ComponentGraphicsItem):
        if not component_item.component_instance or not self.project:
            return
        dialog = ComponentInstanceDialog(component_item.component_instance, self.project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            from fmeda_tool.services.project_service import ProjectService
            ProjectService.log_change(
                self.project,
                "Configure Component",
                f"Configured properties / failure modes for component '{component_item.component_instance.position}'."
            )
            self._load_fmeda_table()
            self._trigger_recalculation()
            
    def _load_components_to_canvas(self):
        comps_db = self._load_components_from_db()
        db_map = {c.display_name: c for c in comps_db}
        
        self.canvas.scene.clear()
        for comp in self.unit.components:
            comp_db = db_map.get(comp.name)
            if not comp_db:
                comp_db = ComponentDB(
                    id=f"compdb_fallback",
                    display_name=comp.name,
                    shortcut=comp.position,
                    fits=comp.failure_rate or 0.0,
                    failure_modes={k: 100.0/len(comp.failure_modes) for k in comp.failure_modes} if comp.failure_modes else {}
                )
            visual_item = ComponentGraphicsItem(comp_db, comp.x_position or 0.0, comp.y_position or 0.0)
            visual_item.component_instance = comp
            self.canvas.scene.addItem(visual_item)


class FunctionalGroupDialog(QDialog):
    """Dialog to add/edit functional groups (Units)"""
    def __init__(self, fg: Optional[Unit] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Functional Group" if fg is None else "Edit Functional Group")
        self.setMinimumWidth(500)
        self.fg = fg
        self._setup_ui()
        if self.fg:
            self._load_data()
            
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        self.name_input = QLineEdit()
        form_layout.addRow("Group Name*:", self.name_input)
        
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(80)
        form_layout.addRow("Description:", self.description_input)
        
        self.included_combo = QComboBox()
        self.included_combo.addItems(["Yes", "No"])
        form_layout.addRow("Included in Safety Function:", self.included_combo)
        
        self.optional_combo = QComboBox()
        self.optional_combo.addItems(["No", "Yes"])
        form_layout.addRow("Optional Module:", self.optional_combo)
        
        self.variant_input = QLineEdit()
        form_layout.addRow("Variant Dependency:", self.variant_input)
        
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80)
        form_layout.addRow("Notes:", self.notes_input)
        
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Draft", "In Progress", "Under Review", "Completed", "Archived"])
        form_layout.addRow("Status:", self.status_combo)
        
        layout.addLayout(form_layout)
        
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
    def _on_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Group Name is required.")
            return
            
        fg_id = self.fg.id if self.fg else f"fg_{uuid.uuid4().hex[:8]}"
        self.fg = Unit(
            id=fg_id,
            name=self.name_input.text().strip(),
            description=self.description_input.toPlainText().strip(),
            included_in_safety_function=(self.included_combo.currentText() == "Yes"),
            optional_module=(self.optional_combo.currentText() == "Yes"),
            variant_dependency=self.variant_input.text().strip() or None,
            notes=self.notes_input.toPlainText().strip() or None,
            status=self.status_combo.currentText(),
            components=self.fg.components if self.fg else []
        )
        self.accept()
        
    def _load_data(self):
        self.name_input.setText(self.fg.name)
        self.description_input.setPlainText(self.fg.description or "")
        self.included_combo.setCurrentText("Yes" if self.fg.included_in_safety_function else "No")
        self.optional_combo.setCurrentText("Yes" if self.fg.optional_module else "No")
        self.variant_input.setText(self.fg.variant_dependency or "")
        self.notes_input.setPlainText(self.fg.notes or "")
        self.status_combo.setCurrentText(self.fg.status or "Draft")


class UnitEditorView(QWidget):
    """Page 2: FMEDA Analysis tabbed workspace supporting Project Overview and Functional Group Tabs"""
    
    save_requested = pyqtSignal()
    back_requested = pyqtSignal()
    next_requested = pyqtSignal()
    project_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.project: Optional[Project] = None
        self.current_unit: Optional[Unit] = None
        self.current_unit_index: int = 0
        self.is_loading_project: bool = False
        self._current_active_tab_widget = None
        self._setup_ui()
        self.project_changed.connect(self._on_project_changed)
        
    @property
    def add_comp_btn(self):
        tab = self.unit_tabs.currentWidget()
        if isinstance(tab, FunctionalGroupTab):
            btn = getattr(tab, "add_comp_type_btn", getattr(tab, "map_bom_btn", None))
            if btn:
                return btn
        for idx in range(self.unit_tabs.count()):
            widget = self.unit_tabs.widget(idx)
            if isinstance(widget, FunctionalGroupTab):
                btn = getattr(widget, "add_comp_type_btn", getattr(widget, "map_bom_btn", None))
                if btn:
                    return btn
        if not hasattr(self, "_dummy_add_btn"):
            self._dummy_add_btn = QPushButton()
        self._dummy_add_btn.setEnabled(bool(self.project is not None))
        return self._dummy_add_btn

    @property
    def config_comp_btn(self):
        tab = self.unit_tabs.currentWidget()
        if isinstance(tab, FunctionalGroupTab):
            btn = getattr(tab, "add_bom_man_btn", getattr(tab, "map_bom_btn", None))
            if btn:
                return btn
        for idx in range(self.unit_tabs.count()):
            widget = self.unit_tabs.widget(idx)
            if isinstance(widget, FunctionalGroupTab):
                btn = getattr(widget, "add_bom_man_btn", getattr(widget, "map_bom_btn", None))
                if btn:
                    return btn
        if not hasattr(self, "_dummy_config_btn"):
            self._dummy_config_btn = QPushButton()
        self._dummy_config_btn.setEnabled(bool(self.project is not None))
        return self._dummy_config_btn
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self._create_header(layout)
        
        self.unit_tabs = QTabWidget()
        self.unit_tabs.setStyleSheet("""
            QTabWidget::panel {
                border-top: 1px solid #dee2e6;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #e9ecef;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border: 1px solid #dee2e6;
                border-bottom: none;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background-color: white;
                color: #0d6efd;
                font-weight: bold;
                border-bottom: 2px solid #0d6efd;
            }
            QTabBar::tab:hover {
                background-color: #dee2e6;
            }
        """)
        self.unit_tabs.currentChanged.connect(self._on_tab_changed)
        
        self.overview_tab = ProjectOverviewTab(self)
        self.unit_tabs.addTab(self.overview_tab, "Project Overview")
        
        layout.addWidget(self.unit_tabs)
        self._create_footer(layout)
        
    def _create_header(self, parent_layout):
        self.header_frame = WorkflowPageHeader("Page 2: FMEDA Analysis")
        
        info_lay = QVBoxLayout()
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(1)
        
        self.project_name_label = QLabel("No Project Open")
        self.project_name_label.setStyleSheet("color: #495057; font-weight: bold; font-size: 11px;")
        info_lay.addWidget(self.project_name_label)
        
        self.project_status_label = QLabel("Status: N/A")
        self.project_status_label.setStyleSheet("color: #6c757d; font-size: 10px;")
        info_lay.addWidget(self.project_status_label)
        
        self.header_frame.left_layout.addLayout(info_lay)
        
        self.undo_btn = QPushButton("← Undo")
        self.undo_btn.setEnabled(False)
        self.undo_btn.setToolTip("Nothing to undo")
        self.undo_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #138496; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.undo_btn.clicked.connect(self._on_undo_clicked)
        self.header_frame.right_layout.addWidget(self.undo_btn)
        
        self.add_fg_btn = QPushButton("➕ Add Functional Group")
        self.add_fg_btn.setStyleSheet("background-color: #0d6efd; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.add_fg_btn.clicked.connect(self._on_add_fg)
        self.add_fg_btn.setEnabled(False)
        self.header_frame.right_layout.addWidget(self.add_fg_btn)
        
        self.edit_fg_btn = QPushButton("✏️ Edit Group Details")
        self.edit_fg_btn.setStyleSheet("background-color: #ffc107; color: black; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.edit_fg_btn.clicked.connect(self._on_edit_fg)
        self.edit_fg_btn.setEnabled(False)
        self.header_frame.right_layout.addWidget(self.edit_fg_btn)
        
        self.remove_fg_btn = QPushButton("❌ Remove Group")
        self.remove_fg_btn.setStyleSheet("background-color: #dc3545; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.remove_fg_btn.clicked.connect(self._on_remove_fg)
        self.remove_fg_btn.setEnabled(False)
        self.header_frame.right_layout.addWidget(self.remove_fg_btn)
        
        parent_layout.addWidget(self.header_frame)
        
    def _create_footer(self, parent_layout):
        footer_frame = QFrame()
        footer_frame.setStyleSheet("QFrame { background-color: #f8f9fa; border-top: 1px solid #dee2e6; }")
        footer_frame.setFixedHeight(60)
        
        layout = QHBoxLayout(footer_frame)
        layout.setContentsMargins(20, 10, 20, 10)
        
        self.back_btn = QPushButton("Back")
        self.back_btn.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 6px 15px;")
        self.back_btn.clicked.connect(self.back_requested.emit)
        layout.addWidget(self.back_btn)
        
        layout.addStretch()
        
        self.save_project_btn = QPushButton("Save Project")
        self.save_project_btn.setStyleSheet("background-color: #ffc107; color: black; font-weight: bold; padding: 6px 20px;")
        self.save_project_btn.clicked.connect(self.save_requested.emit)
        layout.addWidget(self.save_project_btn)
        
        self.next_btn = QPushButton("Next")
        self.next_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 25px;")
        self.next_btn.clicked.connect(self.next_requested.emit)
        layout.addWidget(self.next_btn)
        
        parent_layout.addWidget(footer_frame)
        
    def focus_unit_row(self, unit_id: str, row_index: int):
        if not self.project:
            return
            
        unit_idx = -1
        for i, u in enumerate(self.project.units):
            if u.id == unit_id:
                unit_idx = i
                break
                
        if unit_idx >= 0:
            self.unit_tabs.setCurrentIndex(unit_idx + 1)
            tab_widget = self.unit_tabs.widget(unit_idx + 1)
            if isinstance(tab_widget, FunctionalGroupTab):
                tab_widget.ensure_populated(reason="focus_row")
                tab_widget.stacked_view.setCurrentIndex(0)
                
                target_comp = None
                target_fm = None
                curr = 0
                for comp in tab_widget.unit.components:
                    for fm_name in comp.failure_modes.keys():
                        if curr == row_index:
                            target_comp = comp
                            target_fm = fm_name
                            break
                        curr += 1
                    if target_comp:
                        break
                
                actual_table_row = -1
                if target_comp and target_fm and tab_widget.model:
                    for r, entry in enumerate(tab_widget.model.rows):
                        if not entry.is_separator and entry.component == target_comp and entry.fm_name == target_fm:
                            actual_table_row = r
                            break
                            
                if actual_table_row >= 0 and tab_widget.model:
                    idx = tab_widget.model.index(actual_table_row, 0)
                    tab_widget.table.setCurrentIndex(idx)
                    tab_widget.table.scrollTo(idx)

    def load_project(self, project: Project, timer: Optional[PerformanceTimer] = None):
        if timer:
            timer.counters.load_project_count += 1
            
        self.is_loading_project = True
        self.setUpdatesEnabled(False)
        self.blockSignals(True)
        self.unit_tabs.blockSignals(True)
        
        try:
            self.project = project
            self.project_name_label.setText(project.name)
            status_str = project.status.value.replace("_", " ").title() if project.status else "Draft"
            self.project_status_label.setText(f"Status: {status_str}")
            
            self.add_fg_btn.setEnabled(True)
            self.edit_fg_btn.setEnabled(True)
            self.remove_fg_btn.setEnabled(True)
            
            while self.unit_tabs.count() > 1:
                self.unit_tabs.removeTab(1)
                
            if timer:
                timer.start_phase("overview_widget_refresh")
            self.overview_tab.refresh(project)
            if timer:
                timer.end_phase("overview_widget_refresh")
                
            if timer:
                timer.start_phase("functional_group_tab_headers_creation")
            if project.units:
                for unit in project.units:
                    fg_tab = FunctionalGroupTab(unit, project, self)
                    self.unit_tabs.addTab(fg_tab, unit.name)
                    if timer:
                        timer.counters.functional_group_editor_creation_count += 1
                        timer.log_lazy_event(unit.id, unit.name, "tab_header_created")
            if timer:
                timer.end_phase("functional_group_tab_headers_creation")
                
            target_idx = 0
            if project.last_active_tab_id and project.last_active_tab_id != "overview" and project.units:
                for idx, u in enumerate(project.units):
                    if u.id == project.last_active_tab_id:
                        target_idx = idx + 1
                        break
                        
            self.unit_tabs.setCurrentIndex(target_idx)
            self._current_active_tab_widget = self.unit_tabs.widget(target_idx)
            
            if target_idx > 0:
                active_tab = self.unit_tabs.widget(target_idx)
                if isinstance(active_tab, FunctionalGroupTab):
                    if timer:
                        timer.start_phase("active_functional_group_population")
                    active_tab.ensure_populated(timer=timer, reason="initial")
                    if timer:
                        timer.end_phase("active_functional_group_population")
                        
        finally:
            self.unit_tabs.blockSignals(False)
            self.blockSignals(False)
            self.setUpdatesEnabled(True)
            self.is_loading_project = False
            
    def _on_undo_clicked(self):
        if hasattr(self, "main_window"):
            self.main_window._on_undo()
            
    def _on_tab_changed(self, idx: int):
        prev_widget = getattr(self, "_current_active_tab_widget", None)
        if isinstance(prev_widget, FunctionalGroupTab) and prev_widget.is_in_edit_mode and not self.is_loading_project:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setWindowTitle("Unconfirmed Edits")
            msg.setText(f"Functional group '{prev_widget.unit.name}' has unconfirmed changes.")
            msg.setInformativeText("What would you like to do before switching tabs?")
            btn_confirm = msg.addButton("Confirm and Switch", QMessageBox.ButtonRole.AcceptRole)
            btn_discard = msg.addButton("Discard and Switch", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_confirm)
            msg.exec()
            
            clicked = msg.clickedButton()
            if clicked == btn_confirm:
                prev_widget.confirm_changes()
            elif clicked == btn_discard:
                prev_widget.cancel_changes()
            else:
                prev_idx = self.unit_tabs.indexOf(prev_widget)
                self.unit_tabs.blockSignals(True)
                self.unit_tabs.setCurrentIndex(prev_idx)
                self.unit_tabs.blockSignals(False)
                return

        new_widget = self.unit_tabs.widget(idx)
        self._current_active_tab_widget = new_widget
        
        if idx == 0:
            self.current_unit = None
            self.current_unit_index = 0
            if self.project and not self.is_loading_project:
                self.overview_tab.refresh(self.project)
        else:
            if self.project and idx - 1 < len(self.project.units):
                self.current_unit_index = idx - 1
                self.current_unit = self.project.units[self.current_unit_index]
                if isinstance(new_widget, FunctionalGroupTab):
                    new_widget.ensure_populated(reason="selected")
                
    def _on_project_changed(self):
        if self.is_loading_project:
            return
        if self.project:
            self.overview_tab.refresh(self.project)
            
    def _on_add_fg(self):
        if not self.project:
            return
        dialog = FunctionalGroupDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.fg:
            self.project.units.append(dialog.fg)
            fg_tab = FunctionalGroupTab(dialog.fg, self.project, self)
            self.unit_tabs.addTab(fg_tab, dialog.fg.name)
            self.unit_tabs.setCurrentWidget(fg_tab)
            fg_tab.ensure_populated(reason="add_fg")
            self.project_changed.emit()
            
    def _on_edit_fg(self):
        if not self.project or not self.current_unit:
            QMessageBox.warning(self, "Selection Required", "Please select a Functional Group tab first to edit.")
            return
        dialog = FunctionalGroupDialog(self.current_unit, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.fg:
            self.project.units[self.current_unit_index] = dialog.fg
            self.current_unit = dialog.fg
            self.unit_tabs.setTabText(self.current_unit_index + 1, dialog.fg.name)
            
            tab_widget = self.unit_tabs.widget(self.current_unit_index + 1)
            if isinstance(tab_widget, FunctionalGroupTab) and tab_widget.ui_initialized:
                tab_widget.unit = dialog.fg
                if tab_widget.model:
                    tab_widget.model.unit = dialog.fg
                    tab_widget.model.reload_data()
                
            self.project_changed.emit()
            
    def _on_remove_fg(self):
        if not self.project or not self.current_unit:
            QMessageBox.warning(self, "Selection Required", "Please select a Functional Group tab first to remove.")
            return
        reply = QMessageBox.question(
            self,
            "Confirm Remove",
            f"Are you sure you want to remove the Functional Group '{self.current_unit.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.project.units.pop(self.current_unit_index)
            self.unit_tabs.removeTab(self.current_unit_index + 1)
            self.unit_tabs.setCurrentIndex(0)
            self.project_changed.emit()
