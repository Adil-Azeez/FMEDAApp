from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGraphicsView,
    QGraphicsScene, QPushButton, QLabel, QFrame, QMenu,
    QGraphicsRectItem, QGraphicsTextItem, QScrollArea, QGridLayout,
    QMessageBox, QStackedWidget, QTableView, QHeaderView,
    QComboBox, QDoubleSpinBox, QLineEdit, QDialog, QDialogButtonBox, QFormLayout,
    QTextEdit, QCheckBox, QFileDialog, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF, QModelIndex
from PyQt6.QtGui import (
    QFont, QPainter, QWheelEvent, QMouseEvent, QContextMenuEvent,
    QColor, QPen, QBrush
)
from typing import Optional, List, Dict, Tuple, Any
import uuid
import time
import json
from pathlib import Path

from fmeda_tool.models import (
    Unit, Component, Project, ComponentDB, FailureModeAssignment,
    Deviation, Mitigation, DiagnosticMeasure, DeviationType, DeviationSeverity, MitigationType
)
from fmeda_tool.ui.dialogs import (
    ComponentSelectionDialog, ComponentInstanceDialog, DeviationDialog, MitigationDialog,
    BOMImportDialog, ComponentMappingDialog
)
from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel, FmedaRowEntry, COLUMN_HEADERS
from fmeda_tool.ui.delegates.fmeda_delegates import (
    FmedaComboBoxDelegate, FmedaSpinBoxDelegate, FmedaLineEditDelegate
)
from fmeda_tool.services import ValidationService, ComponentLibraryService
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


class ProjectOverviewTab(QScrollArea):
    """Dashboard displaying metadata, safety context, and key metrics of the project"""
    
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
            elif self.col == 7:
                return entry.assignment
        idx = self.model.index(self.row, self.col)
        return self.model.data(idx, role)


class FunctionalGroupTab(QWidget):
    """
    Workspace tab representing a single Functional Group (Unit).
    Uses QTableView + FmedaTableModel with lightweight delegates and Locked View Mode.
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
        
        self.add_comp_type_btn = QPushButton("Add Component Type")
        self.add_bom_man_btn = QPushButton("Add Component Manually")
        self.import_csv_btn = QPushButton("Import BOM CSV")
        self.map_bom_btn = QPushButton("Map BOM")
        self.manage_dev_btn = QPushButton("Manage Deviations")
        self.manage_mit_btn = QPushButton("Manage Mitigations")
        self.manage_dm_btn = QPushButton("Manage Diagnostic Measures")
        self.validate_btn = QPushButton("Validate Group")
        self.calculate_btn = QPushButton("Calculate Group")
        self.save_btn = QPushButton("Save Project")
        
        for btn in [
            self.add_comp_type_btn, self.add_bom_man_btn, self.import_csv_btn,
            self.map_bom_btn, self.manage_dev_btn, self.manage_mit_btn,
            self.manage_dm_btn, self.validate_btn, self.calculate_btn,
            self.save_btn
        ]:
            btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px 12px; border-radius: 4px;")
            self.toolbar.addWidget(btn)
            
        self.toolbar.addStretch()
        layout.addLayout(self.toolbar)
        
        self.save_btn.clicked.connect(lambda: self.main_editor.save_requested.emit())
        self.import_csv_btn.clicked.connect(self._on_import_bom_csv)
        self.map_bom_btn.clicked.connect(self._on_map_bom_components)
        self.add_comp_type_btn.clicked.connect(self._on_add_comp_type)
        self.add_bom_man_btn.clicked.connect(self._on_add_bom_man_clicked)
        self.manage_dev_btn.clicked.connect(self._on_manage_deviations_clicked)
        self.manage_mit_btn.clicked.connect(self._on_manage_mitigations_clicked)
        self.manage_dm_btn.clicked.connect(self._on_manage_dm_clicked)
        self.validate_btn.clicked.connect(self._on_validate_clicked)
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
        
        # QTableView and FmedaTableModel
        self.table = QTableView()
        self.model = FmedaTableModel(self.unit, self.project, parent=self)
        self.table.setModel(self.model)
        
        # Attach custom lightweight delegates
        self.combo_delegate = FmedaComboBoxDelegate(parent=self.table)
        self.spin_delegate = FmedaSpinBoxDelegate(parent=self.table)
        self.text_delegate = FmedaLineEditDelegate(parent=self.table)
        
        for col in (5, 13, 15, 18, 21, 23):
            self.table.setItemDelegateForColumn(col, self.combo_delegate)
            
        for col in (8, 16, 17, 19, 24, 25, 26):
            self.table.setItemDelegateForColumn(col, self.spin_delegate)
            
        for col in (2, 3, 4, 14, 22):
            self.table.setItemDelegateForColumn(col, self.text_delegate)
            
        # Hide col 20 (DC Test Ref)
        self.table.setColumnHidden(20, True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        
        # Backward compatibility helpers on table instance
        self.table.item = lambda r, c: TableItemProxy(self.model, r, c)
        self.table.rowCount = lambda: self.model.rowCount() if self.model else 0
        self.table.columnCount = lambda: self.model.columnCount() if self.model else 0
        self.table.cellWidget = lambda r, c: None
        
        table_layout.addWidget(self.table)
        
        legend = QFrame()
        legend.setStyleSheet("background-color: #f1f3f5; border-radius: 4px; border: 1px solid #dee2e6;")
        legend.setFixedHeight(35)
        leg_lay = QHBoxLayout(legend)
        leg_lay.setContentsMargins(15, 0, 15, 0)
        leg_lay.addWidget(QLabel("<b>FMEDA Row Legend:</b>"))
        leg_lay.addWidget(QLabel("🟢 Valid (Pass)"))
        leg_lay.addWidget(QLabel("🟡 Warning (Missing deviations/diagnostics)"))
        leg_lay.addWidget(QLabel("🔴 Error (Percentage out of bounds or invalid inputs)"))
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
            
        # Check if another functional group tab is in edit mode
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
        if self.model:
            self.model.set_edit_mode(True)
        self._update_edit_mode_ui()
        return True

    def confirm_changes(self) -> None:
        """Validates, recalculates, commits single coherent Undo state, and returns to View Mode."""
        if not self.is_in_edit_mode:
            return
            
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
            
        self.table.setFocus()
        
        if self.unit_snapshot:
            restored = Unit.model_validate(self.unit_snapshot)
            self.unit.components = restored.components
            self.unit.name = restored.name
            self.unit.description = restored.description
            self.unit.notes = restored.notes
            
        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)
        
        if self.model:
            self.model.reload_data()
            self.model.set_edit_mode(False)
            
        self.unit_snapshot = None
        self.is_in_edit_mode = False
        self._update_edit_mode_ui()

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
        for c in range(0, 7):
            self.table.setColumnHidden(c, not show_bom)

        show_fail = self.cb_fail.isChecked()
        for c in range(7, 13):
            self.table.setColumnHidden(c, not show_fail)

        show_eng = self.cb_eng.isChecked()
        for c in range(13, 24):
            self.table.setColumnHidden(c, not show_eng)

        self.table.setColumnHidden(20, True)

        show_proof = self.cb_proof.isChecked()
        for c in range(24, 28):
            self.table.setColumnHidden(c, not show_proof)

        show_calc = self.cb_calc.isChecked()
        for c in range(28, 41):
            self.table.setColumnHidden(c, not show_calc)

    def _on_table_context_menu(self, pos):
        if not self.model:
            return
            
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
            
        row = index.row()
        if row < 0 or row >= len(self.model.rows):
            return
            
        entry = self.model.rows[row]
        if entry.is_separator or not entry.component or not entry.assignment:
            return
            
        target_comp = entry.component
        target_assignment = entry.assignment
        
        menu = QMenu(self)
        act_dev = menu.addAction("Copy Deviation to all rows of this Component")
        act_class = menu.addAction("Copy Classification to all rows of this Component")
        act_dm = menu.addAction("Copy Diagnostic Measure & DC to all rows of this Component")
        act_mit = menu.addAction("Copy Mitigation to all rows of this Component")
        act_comm = menu.addAction("Copy Comments/Justification to all rows of this Component")
        
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not action:
            return
            
        if not self.is_in_edit_mode:
            self.enable_editing()
            
        for a in target_comp.failure_mode_assignments:
            if action == act_dev:
                a.deviation_id = target_assignment.deviation_id
            elif action == act_class:
                a.classification = target_assignment.classification
                if a.classification == "safe_failure":
                    a.dangerous_failure_percentage = 0.0
                elif a.classification == "dangerous_failure":
                    a.dangerous_failure_percentage = 100.0
            elif action == act_dm:
                a.diagnostic_measure_id = target_assignment.diagnostic_measure_id
                a.detection_percentage = target_assignment.detection_percentage
            elif action == act_mit:
                a.mitigation_id = target_assignment.mitigation_id
            elif action == act_comm:
                a.notes = target_assignment.notes
                
        self._trigger_recalculation()
        self.model.refresh_all_metrics()

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

    def _on_import_bom_csv(self):
        existing_designators = (
            [c.position for c in self.unit.components] +
            [b.designator for b in self.unit.bom_components]
        )
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select BOM CSV File", "", "CSV Files (*.csv);;All Files (*.*)"
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
        
    def _on_map_bom_components(self):
        if not self.unit.bom_components:
            QMessageBox.warning(self, "No BOM Imported", "Please import a BOM first before mapping components.")
            return
        prof = getattr(self.project, "selected_profile", "Profile 1") if hasattr(self, "project") and self.project else "Profile 1"
        dialog = ComponentMappingDialog(self.unit, project_profile=prof, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_fmeda_table()
            self._trigger_recalculation()
            QMessageBox.information(self, "Mappings Saved", "BOM component mappings have been confirmed and FMEDA rows generated successfully!")

    def _on_add_comp_type(self):
        try:
            viewport = self.canvas.viewport()
            center_pos = self.canvas.mapToScene(viewport.rect().center()) if viewport else QPointF(0, 0)
        except Exception:
            center_pos = QPointF(0, 0)
        self._on_add_component_at_position(center_pos)
        
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
            
    def _on_validate_clicked(self):
        if hasattr(self, "stacked_view") and self.stacked_view.currentIndex() == 0:
            self.ensure_populated(reason="manual_validate")
            QMessageBox.information(self, "Validation", "FMEDA spreadsheet validation complete. Check status indicator icons.")
        else:
            errors_cnt = 0
            warnings_cnt = 0
            for comp in self.unit.components:
                c_status, c_msgs = ValidationService.validate_component(comp)
                if c_status == "error":
                    errors_cnt += len(c_msgs)
                elif c_status == "warning":
                    warnings_cnt += len(c_msgs)
            QMessageBox.information(
                self,
                "Validation",
                f"Validation complete for '{self.unit.name}'. Errors: {errors_cnt}. Warnings: {warnings_cnt}."
            )
            
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
    """Main FMEDA tabbed workspace supporting Project Overview and lazy-loaded Functional Group Tabs"""
    
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
        if isinstance(tab, FunctionalGroupTab) and hasattr(tab, "add_comp_type_btn"):
            return tab.add_comp_type_btn
        for idx in range(self.unit_tabs.count()):
            widget = self.unit_tabs.widget(idx)
            if isinstance(widget, FunctionalGroupTab) and hasattr(widget, "add_comp_type_btn"):
                return widget.add_comp_type_btn
        if not hasattr(self, "_dummy_add_btn"):
            self._dummy_add_btn = QPushButton()
            self._dummy_add_btn.setEnabled(False)
        return self._dummy_add_btn

    @property
    def config_comp_btn(self):
        tab = self.unit_tabs.currentWidget()
        if isinstance(tab, FunctionalGroupTab) and hasattr(tab, "add_bom_man_btn"):
            return tab.add_bom_man_btn
        for idx in range(self.unit_tabs.count()):
            widget = self.unit_tabs.widget(idx)
            if isinstance(widget, FunctionalGroupTab) and hasattr(widget, "add_bom_man_btn"):
                return widget.add_bom_man_btn
        if not hasattr(self, "_dummy_config_btn"):
            self._dummy_config_btn = QPushButton()
            self._dummy_config_btn.setEnabled(False)
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
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background-color: #ffffff; border-bottom: 2px solid #dee2e6; }")
        
        layout = QHBoxLayout(header_frame)
        layout.setContentsMargins(20, 10, 20, 10)
        
        title_lay = QVBoxLayout()
        self.project_name_label = QLabel("No Project Open")
        title_font = QFont("Arial", 14, QFont.Weight.Bold)
        self.project_name_label.setFont(title_font)
        self.project_name_label.setStyleSheet("color: #212529; border: none;")
        title_lay.addWidget(self.project_name_label)
        
        self.project_status_label = QLabel("Status: N/A")
        self.project_status_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        title_lay.addWidget(self.project_status_label)
        layout.addLayout(title_lay)
        
        layout.addStretch()
        
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
        layout.addWidget(self.undo_btn)
        
        self.add_fg_btn = QPushButton("➕ Add Functional Group")
        self.add_fg_btn.setStyleSheet("background-color: #0d6efd; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.add_fg_btn.clicked.connect(self._on_add_fg)
        self.add_fg_btn.setEnabled(False)
        layout.addWidget(self.add_fg_btn)
        
        self.edit_fg_btn = QPushButton("✏️ Edit Group Details")
        self.edit_fg_btn.setStyleSheet("background-color: #ffc107; color: black; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.edit_fg_btn.clicked.connect(self._on_edit_fg)
        self.edit_fg_btn.setEnabled(False)
        layout.addWidget(self.edit_fg_btn)
        
        self.remove_fg_btn = QPushButton("❌ Remove Group")
        self.remove_fg_btn.setStyleSheet("background-color: #dc3545; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.remove_fg_btn.clicked.connect(self._on_remove_fg)
        self.remove_fg_btn.setEnabled(False)
        layout.addWidget(self.remove_fg_btn)
        
        parent_layout.addWidget(header_frame)
        
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
        """
        Loads a project into the workspace using true lazy-loading:
        - Inactive tabs create lightweight headers only.
        - If Overview is active, zero functional group tables are populated.
        - If a group tab is active, only that single active group is populated.
        """
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
            
            # Clear old functional group tabs
            while self.unit_tabs.count() > 1:
                self.unit_tabs.removeTab(1)
                
            # Populate overview dashboard
            if timer:
                timer.start_phase("overview_widget_refresh")
            self.overview_tab.refresh(project)
            if timer:
                timer.end_phase("overview_widget_refresh")
                
            # Create lightweight functional group tab placeholders
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
                
            # Determine target active tab index
            target_idx = 0
            if project.last_active_tab_id and project.last_active_tab_id != "overview" and project.units:
                for idx, u in enumerate(project.units):
                    if u.id == project.last_active_tab_id:
                        target_idx = idx + 1
                        break
                        
            self.unit_tabs.setCurrentIndex(target_idx)
            self._current_active_tab_widget = self.unit_tabs.widget(target_idx)
            
            # Only populate the active tab if it is a FunctionalGroupTab
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
        # Handle unconfirmed edits on previously active tab
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
