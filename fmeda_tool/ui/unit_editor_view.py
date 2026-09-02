from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGraphicsView,
    QGraphicsScene, QPushButton, QLabel, QFrame, QMenu,
    QGraphicsRectItem, QGraphicsTextItem, QScrollArea, QGridLayout,
    QMessageBox, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QDoubleSpinBox, QLineEdit, QDialog, QDialogButtonBox, QFormLayout,
    QTextEdit, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (
    QFont, QPainter, QWheelEvent, QMouseEvent, QContextMenuEvent,
    QColor, QPen, QBrush
)
from typing import Optional, List, Dict, Tuple
import uuid
import time
import json
from pathlib import Path

from fmeda_tool.models import (
    Unit, Component, Project, ComponentDB, FailureModeAssignment,
    Deviation, Mitigation, DiagnosticMeasure, DeviationType, DeviationSeverity
)
from fmeda_tool.ui.dialogs import (
    ComponentSelectionDialog, ComponentInstanceDialog, DeviationDialog, MitigationDialog,
    BOMImportDialog, ComponentMappingDialog
)
from fmeda_tool.ui.unit_table_view import UnitTableView
from fmeda_tool.services import ValidationService, ComponentLibraryService



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
        scene_pos = self.mapToScene(event.pos())
        menu = QMenu(self)
        add_action = menu.addAction("Add Component")
        add_action.triggered.connect(lambda: self.add_component_requested.emit(scene_pos))
        menu.exec(event.globalPos())
        
    def reset_view(self):
        self.resetTransform()
        self.zoom_level = 1.0
        self.centerOn(0, 0)
        
    def component_clicked(self, component_item: ComponentGraphicsItem):
        if self.tab_parent and hasattr(self.tab_parent, '_on_component_clicked'):
            self.tab_parent._on_component_clicked(component_item)


class ChangeHistoryDialog(QDialog):
    """Dialog showing the project's modification change history log"""
    
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project Change History Log")
        self.setMinimumSize(750, 450)
        self.project = project
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel(f"Change History: {self.project.name}")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Timestamp", "User", "Action", "Details"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        # Populate table
        logs = getattr(self.project, "change_history", []) or []
        self.table.setRowCount(0)
        for entry in reversed(logs):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(entry.get("timestamp", "")))
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
        
        # Separator line
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #dee2e6;")
        layout.addWidget(div)
        
        # Review Workflow Panel
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
        
        # View History Log Button
        self.view_history_btn = QPushButton("📜 View Project Change History Log")
        self.view_history_btn.setStyleSheet("background-color: #6c757d; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.view_history_btn.clicked.connect(self._on_view_history)
        layout.addWidget(self.view_history_btn)
        
        layout.addStretch()
        self.setWidget(widget)
        
    def refresh(self, project: Project):
        self.project = project
        
        # Temporarily block signals to avoid triggering handlers while loading values
        self.status_combo.blockSignals(True)
        self.reviewer_input.blockSignals(True)
        
        self.reviewer_input.setText(project.reviewer or "")
        status_val = project.status.value if project.status else "draft"
        idx = self.status_combo.findData(status_val)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
            
        self.status_combo.blockSignals(False)
        self.reviewer_input.blockSignals(False)
        
        for i in reversed(range(self.grid.count())):
            self.grid.itemAt(i).widget().setParent(None)
            
        if not project:
            return
            
        row = 0
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
        add_info_row("Status:", project.status.value.replace("_", " ").title(), 1, 2)
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
        if not self.project:
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
        if not self.project:
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


class DiagnosticMeasureMiniDialog(QDialog):
    """Simple form dialog to add/edit diagnostic measures"""
    
    def __init__(self, dm: Optional[DiagnosticMeasure] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Diagnostic Measure" if dm is None else "Edit Diagnostic Measure")
        self.dm = dm
        self._setup_ui()
        if self.dm:
            self._load_data()
            
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.desc_input = QLineEdit()
        form.addRow("Description*:", self.desc_input)
        
        self.dc_input = QDoubleSpinBox()
        self.dc_input.setRange(0, 100)
        self.dc_input.setValue(90.0)
        self.dc_input.setSuffix(" %")
        form.addRow("Diagnostic Coverage (DC%)*:", self.dc_input)
        
        self.notes_input = QLineEdit()
        form.addRow("Notes:", self.notes_input)
        
        layout.addLayout(form)
        
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
    def _on_accept(self):
        if not self.desc_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Description is required.")
            return
            
        if self.dm:
            self.dm.description = self.desc_input.text().strip()
            self.dm.dc = self.dc_input.value()
            self.dm.notes = self.notes_input.text().strip() or None
            from datetime import datetime
            self.dm.updated_at = datetime.now()
        else:
            dm_id = f"dm_{uuid.uuid4().hex[:8]}"
            self.dm = DiagnosticMeasure(
                id=dm_id,
                description=self.desc_input.text().strip(),
                dc=self.dc_input.value(),
                notes=self.notes_input.text().strip() or None
            )
        self.accept()
        
    def _load_data(self):
        self.desc_input.setText(self.dm.description)
        self.dc_input.setValue(self.dm.dc)
        self.notes_input.setText(self.dm.notes or "")


class DiagnosticMeasureManagerDialog(QDialog):
    """Dialog to manage diagnostic measures list on a project"""
    
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Diagnostic Measures")
        self.setMinimumSize(700, 450)
        self.project = project
        self._setup_ui()
        self._refresh_table()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        btn_lay = QHBoxLayout()
        add_btn = QPushButton("+ Add Diagnostic Measure")
        add_btn.clicked.connect(self._on_add)
        btn_lay.addWidget(add_btn)
        btn_lay.addStretch()
        layout.addLayout(btn_lay)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Description", "DC%", "Notes", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, Qt.Orientation.Horizontal, self)
        self.buttons.rejected.connect(self.accept)
        layout.addWidget(self.buttons)
        
    def _refresh_table(self):
        self.table.setRowCount(0)
        for idx, dm in enumerate(self.project.diagnostic_measures):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(dm.description))
            self.table.setItem(row, 1, QTableWidgetItem(f"{dm.dc:.1f}%"))
            self.table.setItem(row, 2, QTableWidgetItem(getattr(dm, "notes", None) or ""))
            
            actions = QWidget()
            lay = QHBoxLayout(actions)
            lay.setContentsMargins(2, 2, 2, 2)
            
            edit = QPushButton("Edit")
            edit.clicked.connect(lambda checked, i=idx: self._on_edit(i))
            lay.addWidget(edit)
            
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda checked, i=idx: self._on_delete(i))
            lay.addWidget(delete)
            
            self.table.setCellWidget(row, 3, actions)
            
    def _on_add(self):
        dialog = DiagnosticMeasureMiniDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.dm:
            self.project.diagnostic_measures.append(dialog.dm)
            self._refresh_table()
            if self.parent() and hasattr(self.parent(), "main_editor"):
                self.parent().main_editor.project_changed.emit()
            
    def _on_edit(self, idx: int):
        dialog = DiagnosticMeasureMiniDialog(self.project.diagnostic_measures[idx], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.dm:
            self.project.diagnostic_measures[idx] = dialog.dm
            self._refresh_table()
            if self.parent() and hasattr(self.parent(), "main_editor"):
                self.parent().main_editor.project_changed.emit()
            
    def _on_delete(self, idx: int):
        dm = self.project.diagnostic_measures[idx]
        assigned_locations = []
        for unit in self.project.units:
            for comp in unit.components:
                for assignment in comp.failure_mode_assignments:
                    if assignment.diagnostic_measure_id == dm.id:
                        assigned_locations.append((unit, comp, assignment))
                        
        if assigned_locations:
            msg = f"This diagnostic measure is assigned to {len(assigned_locations)} failure mode(s).\n\n"
            msg += "If you delete it, these assignments will be cleared.\n\n"
            msg += "Are you sure you want to delete this diagnostic measure?"
            reply = QMessageBox.warning(
                self,
                "Delete Assigned Measure",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        else:
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete the diagnostic measure '{dm.description}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
                
        # Clear assignments to prevent broken references
        for unit, comp, assignment in assigned_locations:
            assignment.diagnostic_measure_id = None
            
        self.project.diagnostic_measures.pop(idx)
        self._refresh_table()
        if self.parent() and hasattr(self.parent(), "main_editor"):
            self.parent().main_editor.project_changed.emit()


class DeviationManagerDialog(QDialog):
    """Dialog to list and configure deviations on a project"""
    
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Deviations")
        self.setMinimumSize(800, 500)
        self.project = project
        self._setup_ui()
        self._refresh_table()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        btn_lay = QHBoxLayout()
        add_btn = QPushButton("+ Add Deviation")
        add_btn.clicked.connect(self._on_add)
        btn_lay.addWidget(add_btn)
        btn_lay.addStretch()
        layout.addLayout(btn_lay)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Severity", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, Qt.Orientation.Horizontal, self)
        self.buttons.rejected.connect(self.accept)
        layout.addWidget(self.buttons)
        
    def _refresh_table(self):
        self.table.setRowCount(0)
        for idx, dev in enumerate(self.project.deviations):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(dev.name))
            self.table.setItem(row, 1, QTableWidgetItem(dev.description or ""))
            self.table.setItem(row, 2, QTableWidgetItem(dev.severity.value if dev.severity else ""))
            
            actions = QWidget()
            lay = QHBoxLayout(actions)
            lay.setContentsMargins(2, 2, 2, 2)
            
            edit = QPushButton("Edit")
            edit.clicked.connect(lambda checked, i=idx: self._on_edit(i))
            lay.addWidget(edit)
            
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda checked, i=idx: self._on_delete(i))
            lay.addWidget(delete)
            
            self.table.setCellWidget(row, 3, actions)
            
    def _on_add(self):
        dialog = DeviationDialog("Global Project Context", parent=self)
        dialog.deviation_saved.connect(self._on_deviation_saved)
        dialog.exec()
        
    def _on_deviation_saved(self, deviation: Deviation, mitigations: List[Mitigation]):
        self.project.deviations.append(deviation)
        for mit in mitigations:
            if mit.id not in [m.id for m in self.project.mitigations]:
                self.project.mitigations.append(mit)
        self._refresh_table()
        
    def _on_edit(self, idx: int):
        deviation = self.project.deviations[idx]
        dialog = DeviationDialog("Global Project Context", deviation, self.project.mitigations, parent=self)
        dialog.deviation_saved.connect(lambda dev, mits: self._on_deviation_updated(idx, dev, mits))
        dialog.exec()
        
    def _on_deviation_updated(self, idx: int, deviation: Deviation, mitigations: List[Mitigation]):
        self.project.deviations[idx] = deviation
        for mit in mitigations:
            if mit.id not in [m.id for m in self.project.mitigations]:
                self.project.mitigations.append(mit)
        self._refresh_table()
        
    def _on_delete(self, idx: int):
        self.project.deviations.pop(idx)
        self._refresh_table()


class MitigationManagerDialog(QDialog):
    """Dialog to list and configure mitigations on a project"""
    
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Mitigations")
        self.setMinimumSize(800, 500)
        self.project = project
        self._setup_ui()
        self._refresh_table()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        btn_lay = QHBoxLayout()
        add_btn = QPushButton("+ Add Mitigation")
        add_btn.clicked.connect(self._on_add)
        btn_lay.addWidget(add_btn)
        btn_lay.addStretch()
        layout.addLayout(btn_lay)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name/ID", "Description", "Type", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, Qt.Orientation.Horizontal, self)
        self.buttons.rejected.connect(self.accept)
        layout.addWidget(self.buttons)
        
    def _refresh_table(self):
        self.table.setRowCount(0)
        for idx, mit in enumerate(self.project.mitigations):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(mit.name or mit.id))
            self.table.setItem(row, 1, QTableWidgetItem(mit.description or ""))
            self.table.setItem(row, 2, QTableWidgetItem(mit.mitigation_type.value if mit.mitigation_type else ""))
            
            actions = QWidget()
            lay = QHBoxLayout(actions)
            lay.setContentsMargins(2, 2, 2, 2)
            
            edit = QPushButton("Edit")
            edit.clicked.connect(lambda checked, i=idx: self._on_edit(i))
            lay.addWidget(edit)
            
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda checked, i=idx: self._on_delete(i))
            lay.addWidget(delete)
            
            self.table.setCellWidget(row, 3, actions)
            
    def _on_add(self):
        dialog = MitigationDialog(parent=self)
        dialog.mitigation_saved.connect(self._on_mitigation_saved)
        dialog.exec()
        
    def _on_mitigation_saved(self, mitigation: Mitigation):
        self.project.mitigations.append(mitigation)
        self._refresh_table()
        
    def _on_edit(self, idx: int):
        mitigation = self.project.mitigations[idx]
        # dialog = MitigationDialog(mitigation, parent=self)
        dialog = MitigationDialog(mitigation=mitigation,parent=self)
        dialog.mitigation_saved.connect(lambda mit: self._on_mitigation_updated(idx, mit))
        dialog.exec()
        
    def _on_mitigation_updated(self, idx: int, mitigation: Mitigation):
        self.project.mitigations[idx] = mitigation
        self._refresh_table()
        
    def _on_delete(self, idx: int):
        self.project.mitigations.pop(idx)
        self._refresh_table()


class FunctionalGroupTab(QWidget):
    """Workspace tab representing a single Functional Group (Unit)"""
    
    def __init__(self, unit: Unit, project: Project, main_editor, parent=None):
        super().__init__(parent)
        self.unit = unit
        self.project = project
        self.main_editor = main_editor
        self._setup_ui()
        self._load_components_to_canvas()
        self._load_fmeda_table()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Toolbar layout
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(8)
        
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
        
        # Legacy canvas toggle is hidden.
        # The canvas remains internally because component creation still uses it.
        # self.toggle_view_btn = QPushButton("📺 Toggle Table/Canvas")
        # self.toggle_view_btn.setStyleSheet(
        #     "background-color: #0dcaf0; font-weight: bold;"
        # )
        # self.toggle_view_btn.clicked.connect(self._toggle_view)
        
        for btn in [
            self.add_comp_type_btn, self.add_bom_man_btn, self.import_csv_btn,
            self.map_bom_btn, self.manage_dev_btn, self.manage_mit_btn,
            self.manage_dm_btn, self.validate_btn, self.calculate_btn,
            self.save_btn
        ]:
            btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px 12px; border-radius: 4px;")
            self.toolbar.addWidget(btn)
            
        self.toolbar.addStretch()

        # Toggle button intentionally hidden.
        # self.toolbar.addWidget(self.toggle_view_btn)

        layout.addLayout(self.toolbar)
        
        # Button connections
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
        
        # Stacked area for Table vs Graphical Canvas
        self.stacked_view = QStackedWidget()
        layout.addWidget(self.stacked_view)
        
        # Page 0: The Central FMEDA spreadsheet view
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(8)
        
        # Checkboxes for toggling column groups
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
        
        self.table = QTableWidget()
        self.table.setColumnCount(41)
        self.table.setHorizontalHeaderLabels([
            # Component/BOM Columns
            "Component ID / Designator", "Status", "Function", "Value / Description",
            "Internal Part Number", "Fitted Status", "Component Type",
            # Failure Model Columns
            "Failure Mode", "Failure-Mode %", "Base Failure Rate (FIT)",
            "Reliability Source", "Source Reference", "Environmental Profile",
            # Manual Engineering Columns
            "Failure Effect / Deviation", "Diagnostic Function", "Failure Classification",
            "Dangerous %", "Safe %",
            "Diagnostic Measure ID", "Detection % (DC)", "DC Test Ref", "Mitigation",
            "Comments / Justification", "Review Status",
            # Proof-Test Columns
            "Proof Test A", "Proof Test B", "Proof Test C", "No Part / No Effect",
            # Calculated Result Columns
            "lambda (FIT)", "lambda_safe (FIT)", "lambda_dangerous (FIT)",
            "lambda_sd (FIT)", "lambda_su (FIT)", "lambda_dd (FIT)", "lambda_du (FIT)",
            "lambda_no_part (FIT)", "lambda_no_effect (FIT)", "SFF %", "DC %", "MTBF (h)", "MTTFd (y)"
        ])

        # Keep the column internally, but hide it from the interface.
        self.table.setColumnHidden(20, True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        table_layout.addWidget(self.table)
        
        # Legend Display
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
        
        # Page 1: Legacy Whiteboard Canvas
        self.canvas = ComponentCanvas(self)
        self.canvas.add_component_requested.connect(self._on_add_component_at_position)
        self.stacked_view.addWidget(self.canvas)
        
        self.stacked_view.setCurrentIndex(0)
        
    def _toggle_view(self):
        cur = self.stacked_view.currentIndex()
        new_idx = 1 - cur
        self.stacked_view.setCurrentIndex(new_idx)
        if new_idx == 0:
            self._load_fmeda_table()
            
    # def _toggle_column_groups(self):
    #     # Component/BOM: 0-6
    #     show_bom = self.cb_bom.isChecked()
    #     for c in range(0, 7):
    #         (c, not show_bom)
            
    #     # Failure Model: 7-12
    #     show_fail = self.cb_fail.isChecked()
    #     for c in range(7, 13):
    #         (c, not show_fail)
            
    #     # Manual Engineering: 13-21
    #     show_eng = self.cb_eng.isChecked()
    #     for c in range(13, 22):
    #         (c, not show_eng)
            
    #     # Proof-Test: 22-25
    #     show_proof = self.cb_proof.isChecked()
    #     for c in range(22, 26):
    #         (c, not show_proof)
            
    #     # Calculated: 26-39
    #     show_calc = self.cb_calc.isChecked()
    #     for c in range(26, 39):
    #         (c, not show_calc)

    def _toggle_column_groups(self):
        # Component/BOM: columns 0-6
        show_bom = self.cb_bom.isChecked()

        for c in range(0, 7):
            self.table.setColumnHidden(c, not show_bom)

        # Failure Model: columns 7-12
        show_fail = self.cb_fail.isChecked()

        for c in range(7, 13):
            self.table.setColumnHidden(c, not show_fail)

        # Manual Engineering: columns 13-23
        show_eng = self.cb_eng.isChecked()

        for c in range(13, 24):
            self.table.setColumnHidden(c, not show_eng)

        # Always keep DC Test Ref, column 20, hidden.
        self.table.setColumnHidden(20, True)

        # Proof-Test: columns 24-27
        show_proof = self.cb_proof.isChecked()

        for c in range(24, 28):
            self.table.setColumnHidden(c, not show_proof)

        # Calculated Results: columns 28-40
        show_calc = self.cb_calc.isChecked()

        for c in range(28, 41):
            self.table.setColumnHidden(c, not show_calc)


    def _on_table_context_menu(self, pos):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
            
        row = selected_rows[0].row()
        # Find which component/assignment is at this row
        item0 = self.table.item(row, 0)
        item7 = self.table.item(row, 7)
        target_comp = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        target_assignment = item7.data(Qt.ItemDataRole.UserRole) if item7 else None
        
        if not target_comp or not target_assignment:
            return
            
        menu = QMenu(self)
        
        act_dev = menu.addAction("Copy Deviation to all rows of this Component")
        act_class = menu.addAction("Copy Classification to all rows of this Component")
        act_dm = menu.addAction("Copy Diagnostic Measure & DC to all rows of this Component")
        act_mit = menu.addAction("Copy Mitigation to all rows of this Component")
        act_comm = menu.addAction("Copy Comments/Justification to all rows of this Component")
        
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not action:
            return
            
        # Perform propagation
        for a in target_comp.failure_mode_assignments:
            if action == act_dev:
                a.deviation_id = target_assignment.deviation_id
            elif action == act_class:
                a.classification = target_assignment.classification
            elif action == act_dm:
                a.diagnostic_measure_id = target_assignment.diagnostic_measure_id
                a.detection_percentage = target_assignment.detection_percentage
            elif action == act_mit:
                a.mitigation_id = target_assignment.mitigation_id
            elif action == act_comm:
                a.notes = target_assignment.notes
                
        self._trigger_recalculation()
        self._load_fmeda_table()

    def _load_fmeda_table(self):
        # Disable sorting temporarily during load
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        from fmeda_tool.services.calculation_service import CalculationService
        
        class_map_rev = {
            "not_evaluated": "Not Evaluated",
            "safe_failure": "Safe Failure",
            "dangerous_failure": "Dangerous Failure"
        }
        
        is_first_comp = True
        for comp in self.unit.components:
            if not is_first_comp:
                # Insert exactly one blank visual separator row between different components
                sep_row = self.table.rowCount()
                self.table.insertRow(sep_row)
                for c in range(self.table.columnCount()):
                    sep_item = QTableWidgetItem("")
                    sep_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    sep_item.setBackground(QColor("#f8f9fa"))  # Neutral light gray background
                    self.table.setItem(sep_row, c, sep_item)
                self.table.setRowHeight(sep_row, 10)  # Small height
                
            is_first_comp = False
            
            for fm_name, fm_percentage in comp.failure_modes.items():
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                # Get assignment
                assignment = next((a for a in comp.failure_mode_assignments if a.failure_mode_name == fm_name), None)
                if not assignment:
                    assignment = FailureModeAssignment(
                        failure_mode_name=fm_name,
                        failure_rate_percentage=fm_percentage,
                        classification="not_evaluated",
                        dangerous_failure_percentage=100.0,
                        detection_percentage=0.0
                    )
                    comp.failure_mode_assignments.append(assignment)
                    
                # Calculate detailed row metrics via calculation service
                local_fit = (comp.failure_rate or 0.0) * (fm_percentage / 100.0)
                classif = getattr(assignment, "classification", "not_evaluated")
                dp = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage is not None else 100.0
                det = assignment.detection_percentage if assignment.detection_percentage is not None else 0.0
                
                # Backwards compatible mapping if it is no_part_failure/no_effect_failure/diagnostic_function_failure
                if classif in ["no_part_failure", "no_effect_failure", "diagnostic_function_failure"]:
                    assignment.dont_care = True
                    assignment.dangerous_failure_percentage = 0.0
                    assignment.classification = "safe_failure"
                    classif = "safe_failure"
                    dp = 0.0
                
                row_metrics = CalculationService.calculate_row_detailed(local_fit, classif, dp, det)
                
                # ----------------- Component/BOM Columns (0-6) -----------------
                # Column 0: Designator (ReadOnly)
                des_item = self._read_only_item(comp.position)
                des_item.setData(Qt.ItemDataRole.UserRole, comp)
                self.table.setItem(row, 0, des_item)
                
                # Column 1: Status Code (Will be styled in _style_row)
                status_item = QTableWidgetItem("🟢")
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 1, status_item)
                
                # Column 2: Function (Component Level edit)
                fn_edit = QLineEdit(comp.function or "")
                fn_edit.textChanged.connect(lambda txt, c=comp: self._on_comp_text_changed(txt, "function", c))
                self.table.setCellWidget(row, 2, fn_edit)
                
                # Column 3: Value / Description (Component Level edit)
                val_edit = QLineEdit(comp.value or "")
                val_edit.textChanged.connect(lambda txt, c=comp: self._on_comp_text_changed(txt, "value", c))
                self.table.setCellWidget(row, 3, val_edit)
                
                # Column 4: Internal Part Number (Component Level edit)
                pn_edit = QLineEdit(comp.internal_pn or "")
                pn_edit.textChanged.connect(lambda txt, c=comp: self._on_comp_text_changed(txt, "internal_pn", c))
                self.table.setCellWidget(row, 4, pn_edit)
                
                # Column 5: Fitted Status (Component Level edit)
                fit_combo = QComboBox()
                fit_combo.addItems(["Fitted", "Not Fitted"])
                fit_combo.setCurrentText(comp.fitted_status or "Fitted")
                fit_combo.currentTextChanged.connect(lambda txt, c=comp: self._on_fitted_changed(txt, c))
                self.table.setCellWidget(row, 5, fit_combo)
                
                # Column 6: Component Type (ReadOnly)
                self.table.setItem(row, 6, self._read_only_item(comp.type))
                
                # ----------------- Failure Model Columns (7-12) -----------------
                # Column 7: Failure Mode (ReadOnly)
                fm_item = self._read_only_item(fm_name)
                fm_item.setData(Qt.ItemDataRole.UserRole, assignment)
                self.table.setItem(row, 7, fm_item)
                
                # Column 8: Distribution % (ReadOnly)
                self.table.setItem(row, 8, self._read_only_item(f"{fm_percentage:.1f}%"))
                
                # Column 9: Base FIT (ReadOnly)
                self.table.setItem(row, 9, self._read_only_item(f"{comp.failure_rate or 0.0:.4f}"))
                
                # Column 10: Reliability Source (ReadOnly)
                rel_db = self.project.reliability_database_source or "MIL-HDBK-217F"
                self.table.setItem(row, 10, self._read_only_item(rel_db))
                
                # Column 11: Source Reference (ReadOnly)
                self.table.setItem(row, 11, self._read_only_item("Section 5"))
                
                # Column 12: Environmental Profile (ReadOnly)
                env_prof = self.project.environmental_profile or "Ground Benign (GB)"
                self.table.setItem(row, 12, self._read_only_item(env_prof))
                
                # ----------------- Manual Engineering Columns (13-23) -----------------
                # Column 13: Deviation / Failure Effect
                dev_combo = QComboBox()
                dev_combo.addItem("-- None --", None)
                for dev in self.project.deviations:
                    dev_combo.addItem(dev.name, dev.id)
                if assignment.deviation_id:
                    dev_idx = dev_combo.findData(assignment.deviation_id)
                    if dev_idx >= 0:
                        dev_combo.setCurrentIndex(dev_idx)
                dev_combo.currentIndexChanged.connect(
                    lambda idx, a=assignment, c=comp, r=row, combo=dev_combo: self._on_dev_changed(combo.currentData(), a, c, r)
                )
                self.table.setCellWidget(row, 13, dev_combo)
                
                # Column 14: Diagnostic Function
                diag_fn_edit = QLineEdit(assignment.diagnostic_function or "")
                diag_fn_edit.textChanged.connect(
                    lambda txt, a=assignment: self._on_assignment_text_changed(txt, "diagnostic_function", a)
                )
                self.table.setCellWidget(row, 14, diag_fn_edit)
                
                # Column 15: Failure Classification
                class_combo = QComboBox()
                class_combo.addItems([
                    "Not Evaluated", "Safe Failure", "Dangerous Failure"
                ])
                class_combo.setCurrentText(class_map_rev.get(classif, "Not Evaluated"))
                class_combo.currentTextChanged.connect(
                    lambda txt, a=assignment, c=comp, r=row: self._on_classif_changed(txt, a, c, r)
                )
                self.table.setCellWidget(row, 15, class_combo)
                
                # Column 16: Dangerous %
                dang_spin = QDoubleSpinBox()
                dang_spin.setRange(0.0, 100.0)
                dang_spin.setValue(dp)
                dang_spin.setSuffix("%")
                
                # Column 17: Safe %
                safe_spin = QDoubleSpinBox()
                safe_spin.setRange(0.0, 100.0)
                safe_spin.setValue(100.0 - dp)
                safe_spin.setSuffix("%")
                
                dang_spin.valueChanged.connect(
                    lambda val, a=assignment, s_spin=safe_spin, c=comp, r=row: self._on_dang_pct_changed(val, a, s_spin, c, r)
                )
                safe_spin.valueChanged.connect(
                    lambda val, a=assignment, d_spin=dang_spin, c=comp, r=row: self._on_safe_pct_changed(val, a, d_spin, c, r)
                )
                self.table.setCellWidget(row, 16, dang_spin)
                self.table.setCellWidget(row, 17, safe_spin)
                
                # Column 18: Diagnostic Measure ID
                dm_combo = QComboBox()
                dm_combo.addItem("-- None --", None)
                for dm in self.project.diagnostic_measures:
                    dm_combo.addItem(dm.description, dm.id)
                if assignment.diagnostic_measure_id:
                    dm_idx = dm_combo.findData(assignment.diagnostic_measure_id)
                    if dm_idx >= 0:
                        dm_combo.setCurrentIndex(dm_idx)
                self.table.setCellWidget(row, 18, dm_combo)
                
                # Column 19: Detection % (DC)
                det_spin = QDoubleSpinBox()
                det_spin.setRange(0.0, 100.0)
                det_spin.setValue(det)
                det_spin.valueChanged.connect(
                    lambda val, a=assignment, c=comp, r=row: self._on_det_changed(val, a, c, r)
                )
                self.table.setCellWidget(row, 19, det_spin)
                
                dm_combo.currentIndexChanged.connect(
                    lambda idx, a=assignment, c=comp, r=row, combo=dm_combo, d_spin=det_spin: self._on_dm_changed(combo.currentData(), a, c, r, d_spin)
                )
                
                # Column 21: Mitigation
                mit_combo = QComboBox()
                mit_combo.addItem("-- None --", None)
                for mit in self.project.mitigations:
                    mit_combo.addItem(mit.name or mit.id, mit.id)
                if assignment.mitigation_id:
                    mit_idx = mit_combo.findData(assignment.mitigation_id)
                    if mit_idx >= 0:
                        mit_combo.setCurrentIndex(mit_idx)
                mit_combo.currentIndexChanged.connect(
                    lambda idx, a=assignment, c=comp, r=row, combo=mit_combo: self._on_mit_changed(combo.currentData(), a, c, r)
                )
                self.table.setCellWidget(row, 21, mit_combo)
                
                # Column 22: Comments / Justification
                comm_edit = QLineEdit(assignment.notes or "")
                comm_edit.textChanged.connect(
                    lambda txt, a=assignment: self._on_assignment_text_changed(txt, "notes", a)
                )
                self.table.setCellWidget(row, 22, comm_edit)
                
                # Column 23: Review Status
                rev_combo = QComboBox()
                rev_combo.addItems(["Draft", "Under Review", "Approved"])
                rev_combo.setCurrentText((assignment.review_status or "Draft").title())
                rev_combo.currentTextChanged.connect(
                    lambda txt, a=assignment: self._on_assignment_text_changed(txt.lower(), "review_status", a)
                )
                self.table.setCellWidget(row, 23, rev_combo)
                
                # ----------------- Proof-Test Columns (24-27) -----------------
                # Column 24: Proof Test A
                pt_a_spin = QDoubleSpinBox()
                pt_a_spin.setRange(0.0, 100.0)
                pt_a_spin.setValue(getattr(assignment, "proof_test_a", 0.0) or 0.0)
                pt_a_spin.valueChanged.connect(
                    lambda val, a=assignment: self._on_pt_changed(val, "proof_test_a", a)
                )
                self.table.setCellWidget(row, 24, pt_a_spin)
                
                # Column 25: Proof Test B
                pt_b_spin = QDoubleSpinBox()
                pt_b_spin.setRange(0.0, 100.0)
                pt_b_spin.setValue(getattr(assignment, "proof_test_b", 0.0) or 0.0)
                pt_b_spin.valueChanged.connect(
                    lambda val, a=assignment: self._on_pt_changed(val, "proof_test_b", a)
                )
                self.table.setCellWidget(row, 25, pt_b_spin)
                
                # Column 26: Proof Test C
                pt_c_spin = QDoubleSpinBox()
                pt_c_spin.setRange(0.0, 100.0)
                pt_c_spin.setValue(getattr(assignment, "proof_test_c", 0.0) or 0.0)
                pt_c_spin.valueChanged.connect(
                    lambda val, a=assignment: self._on_pt_changed(val, "proof_test_c", a)
                )
                self.table.setCellWidget(row, 26, pt_c_spin)
                
                # Column 27: No Part / No Effect Checkbox
                dc_check = QCheckBox()
                dc_check.setChecked(getattr(assignment, "dont_care", False) or False)
                dc_check.stateChanged.connect(
                    lambda state, a=assignment, c=comp, r=row: self._on_dont_care_changed(state, a, c, r)
                )
                ch_widget = QWidget()
                ch_lay = QHBoxLayout(ch_widget)
                ch_lay.addWidget(dc_check)
                ch_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ch_lay.setContentsMargins(0,0,0,0)
                self.table.setCellWidget(row, 27, ch_widget)
                
                # ----------------- Calculated Result Columns (28-40) -----------------
                self.table.setItem(row, 28, self._read_only_item(f"{row_metrics['lambda']:.4f}"))
                self.table.setItem(row, 29, self._read_only_item(f"{row_metrics['lambda_safe']:.4f}"))
                self.table.setItem(row, 30, self._read_only_item(f"{row_metrics['lambda_dangerous']:.4f}"))
                self.table.setItem(row, 31, self._read_only_item(f"{row_metrics['lambda_sd']:.4f}"))
                self.table.setItem(row, 32, self._read_only_item(f"{row_metrics['lambda_su']:.4f}"))
                self.table.setItem(row, 33, self._read_only_item(f"{row_metrics['lambda_dd']:.4f}"))
                self.table.setItem(row, 34, self._read_only_item(f"{row_metrics['lambda_du']:.4f}"))
                self.table.setItem(row, 35, self._read_only_item(f"{row_metrics['lambda_no_part']:.4f}"))
                self.table.setItem(row, 36, self._read_only_item(f"{row_metrics['lambda_no_effect']:.4f}"))
                
                self.table.setItem(row, 37, self._read_only_item(f"{row_metrics['sff']:.1f}%"))
                self.table.setItem(row, 38, self._read_only_item(f"{row_metrics['dc']:.1f}%"))
                
                mtbf_str = f"{row_metrics['mtbf']:.1e}" if row_metrics['mtbf'] > 0 else "N/A"
                self.table.setItem(row, 39, self._read_only_item(mtbf_str))
                
                mttfd_str = f"{row_metrics['mttfd']:.1f}" if row_metrics['mttfd'] > 0 else "N/A"
                self.table.setItem(row, 40, self._read_only_item(mttfd_str))
                
                self._style_row(row, assignment, comp)
                
        # Re-apply toggled headers
        self._toggle_column_groups()

    def _read_only_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item
        
    def _trigger_recalculation(self):
        from fmeda_tool.services.calculation_service import CalculationService
        CalculationService.calculate_project(self.project)
        self.main_editor.project_changed.emit()

    def _on_comp_text_changed(self, text: str, field: str, comp: Component):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            last_act = self.main_editor.main_window.undo_stack[-1][1] if self.main_editor.main_window.undo_stack else ""
            act = f"Edit {field.title().replace('_', ' ')} of {comp.position}"
            if last_act != act:
                self.main_editor.main_window.push_undo_state(act)
        setattr(comp, field, text)
        self.main_editor.project_changed.emit()
        
        # Update other repeated rows for the same component in real-time
        col_map = {
            "function": 2,
            "value": 3,
            "internal_pn": 4
        }
        col = col_map.get(field)
        if col is not None:
            active_sender = self.sender()
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and item.text() == comp.position:
                    widget = self.table.cellWidget(r, col)
                    if isinstance(widget, QLineEdit) and widget != active_sender:
                        widget.blockSignals(True)
                        widget.setText(text)
                        widget.blockSignals(False)

    def _on_assignment_text_changed(self, text: str, field: str, assignment: FailureModeAssignment):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            last_act = self.main_editor.main_window.undo_stack[-1][1] if self.main_editor.main_window.undo_stack else ""
            act = f"Edit {field.title().replace('_', ' ')} of {assignment.failure_mode_name}"
            if last_act != act:
                self.main_editor.main_window.push_undo_state(act)
        setattr(assignment, field, text)
        self.main_editor.project_changed.emit()

    def _on_fitted_changed(self, text: str, comp: Component):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            self.main_editor.main_window.push_undo_state(f"Change Fitted Status of {comp.position}")
        comp.fitted_status = text
        self._trigger_recalculation()
        
        # Update other repeated rows' combo boxes and recalculate calculated columns
        active_sender = self.sender()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.text() == comp.position:
                widget = self.table.cellWidget(r, 5)
                if isinstance(widget, QComboBox) and widget != active_sender:
                    widget.blockSignals(True)
                    widget.setCurrentText(text)
                    widget.blockSignals(False)
                
                # Retrieve assignment for this row and update its calculated cells
                item7 = self.table.item(r, 7)
                assignment = item7.data(Qt.ItemDataRole.UserRole) if item7 else None
                if assignment:
                    self._update_row_calculated_cells(r, assignment, comp)

    def _on_pt_changed(self, val: float, field: str, assignment: FailureModeAssignment):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            last_act = self.main_editor.main_window.undo_stack[-1][1] if self.main_editor.main_window.undo_stack else ""
            act = f"Change Proof Test of {assignment.failure_mode_name}"
            if last_act != act:
                self.main_editor.main_window.push_undo_state(act)
        setattr(assignment, field, val)
        self._trigger_recalculation()

    def _on_dont_care_changed(self, state: int, assignment: FailureModeAssignment, comp: Component, row: int):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            self.main_editor.main_window.push_undo_state(f"Change No Part of {comp.position}")
        assignment.dont_care = (state == 2 or state == Qt.CheckState.Checked.value or state == True)
        self._trigger_recalculation()
        self._load_fmeda_table()

    def _on_dev_changed(self, dev_id: Optional[str], assignment: FailureModeAssignment, component: Component, row: int):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            self.main_editor.main_window.push_undo_state(f"Change Deviation of {component.position}")
        assignment.deviation_id = dev_id
        self._style_row(row, assignment, component)
        self._trigger_recalculation()
        
    def _on_classif_changed(self, text: str, assignment: FailureModeAssignment, component: Component, row: int):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            self.main_editor.main_window.push_undo_state(f"Change Classification of {component.position}")
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
            
        self._trigger_recalculation()
        self._load_fmeda_table()

    def _on_dang_pct_changed(self, val: float, assignment: FailureModeAssignment, safe_spin: QDoubleSpinBox, component: Component, row: int):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            last_act = self.main_editor.main_window.undo_stack[-1][1] if self.main_editor.main_window.undo_stack else ""
            act = f"Change Dangerous % of {component.position}"
            if last_act != act:
                self.main_editor.main_window.push_undo_state(act)
        assignment.dangerous_failure_percentage = val
        safe_spin.blockSignals(True)
        safe_spin.setValue(100.0 - val)
        safe_spin.blockSignals(False)
        
        if val == 0.0:
            assignment.classification = "safe_failure"
        elif val == 100.0:
            assignment.classification = "dangerous_failure"
        else:
            assignment.classification = "dangerous_failure"
            
        class_combo = self.table.cellWidget(row, 15)
        if class_combo:
            class_combo.blockSignals(True)
            if val == 0.0:
                class_combo.setCurrentText("Safe Failure")
            elif val == 100.0:
                class_combo.setCurrentText("Dangerous Failure")
            else:
                class_combo.setCurrentText("Dangerous Failure")
            class_combo.blockSignals(False)
            
        self._trigger_recalculation()
        self._update_row_calculated_cells(row, assignment, component)

    def _on_safe_pct_changed(self, val: float, assignment: FailureModeAssignment, dang_spin: QDoubleSpinBox, component: Component, row: int):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            last_act = self.main_editor.main_window.undo_stack[-1][1] if self.main_editor.main_window.undo_stack else ""
            act = f"Change Safe % of {component.position}"
            if last_act != act:
                self.main_editor.main_window.push_undo_state(act)
        dang_val = 100.0 - val
        assignment.dangerous_failure_percentage = dang_val
        dang_spin.blockSignals(True)
        dang_spin.setValue(dang_val)
        dang_spin.blockSignals(False)
        
        if dang_val == 0.0:
            assignment.classification = "safe_failure"
        elif dang_val == 100.0:
            assignment.classification = "dangerous_failure"
        else:
            assignment.classification = "dangerous_failure"
            
        class_combo = self.table.cellWidget(row, 15)
        if class_combo:
            class_combo.blockSignals(True)
            if dang_val == 0.0:
                class_combo.setCurrentText("Safe Failure")
            elif dang_val == 100.0:
                class_combo.setCurrentText("Dangerous Failure")
            else:
                class_combo.setCurrentText("Dangerous Failure")
            class_combo.blockSignals(False)
            
        self._trigger_recalculation()
        self._update_row_calculated_cells(row, assignment, component)

    def _update_row_calculated_cells(self, row: int, assignment: FailureModeAssignment, component: Component):
        from fmeda_tool.services.calculation_service import CalculationService
        fm_percentage = component.failure_modes.get(assignment.failure_mode_name, 0.0)
        local_fit = (component.failure_rate or 0.0) * (fm_percentage / 100.0)
        dp = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage is not None else 100.0
        det = assignment.detection_percentage if assignment.detection_percentage is not None else 0.0
        
        row_metrics = CalculationService.calculate_row_detailed(local_fit, assignment.classification, dp, det)
        
        self.table.blockSignals(True)
        self.table.setItem(row, 28, self._read_only_item(f"{row_metrics['lambda']:.4f}"))
        self.table.setItem(row, 29, self._read_only_item(f"{row_metrics['lambda_safe']:.4f}"))
        self.table.setItem(row, 30, self._read_only_item(f"{row_metrics['lambda_dangerous']:.4f}"))
        self.table.setItem(row, 31, self._read_only_item(f"{row_metrics['lambda_sd']:.4f}"))
        self.table.setItem(row, 32, self._read_only_item(f"{row_metrics['lambda_su']:.4f}"))
        self.table.setItem(row, 33, self._read_only_item(f"{row_metrics['lambda_dd']:.4f}"))
        self.table.setItem(row, 34, self._read_only_item(f"{row_metrics['lambda_du']:.4f}"))
        self.table.setItem(row, 35, self._read_only_item(f"{row_metrics['lambda_no_part']:.4f}"))
        self.table.setItem(row, 36, self._read_only_item(f"{row_metrics['lambda_no_effect']:.4f}"))
        
        self.table.setItem(row, 37, self._read_only_item(f"{row_metrics['sff']:.1f}%"))
        self.table.setItem(row, 38, self._read_only_item(f"{row_metrics['dc']:.1f}%"))
        
        mtbf_str = f"{row_metrics['mtbf']:.1e}" if row_metrics['mtbf'] > 0 else "N/A"
        self.table.setItem(row, 39, self._read_only_item(mtbf_str))
        
        mttfd_str = f"{row_metrics['mttfd']:.1f}" if row_metrics['mttfd'] > 0 else "N/A"
        self.table.setItem(row, 40, self._read_only_item(mttfd_str))
        self.table.blockSignals(False)
        
        self._style_row(row, assignment, component)

    def _on_dm_changed(self, dm_id: Optional[str], assignment: FailureModeAssignment, component: Component, row: int, det_spin: QDoubleSpinBox):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            self.main_editor.main_window.push_undo_state(f"Change Diagnostic Measure of {component.position}")
        assignment.diagnostic_measure_id = dm_id
        if dm_id:
            dm = next((m for m in self.project.diagnostic_measures if m.id == dm_id), None)
            if dm:
                det_spin.setValue(dm.dc)
                assignment.detection_percentage = dm.dc
        self._trigger_recalculation()
        self._update_row_calculated_cells(row, assignment, component)
        
    def _on_det_changed(self, val: float, assignment: FailureModeAssignment, component: Component, row: int):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            last_act = self.main_editor.main_window.undo_stack[-1][1] if self.main_editor.main_window.undo_stack else ""
            act = f"Change Detection % of {component.position}"
            if last_act != act:
                self.main_editor.main_window.push_undo_state(act)
        assignment.detection_percentage = val
        self._trigger_recalculation()
        self._update_row_calculated_cells(row, assignment, component)
        
    def _on_mit_changed(self, mit_id: Optional[str], assignment: FailureModeAssignment, component: Component, row: int):
        if self.main_editor and hasattr(self.main_editor, "main_window"):
            self.main_editor.main_window.push_undo_state(f"Change Mitigation of {component.position}")
        assignment.mitigation_id = mit_id
        self._trigger_recalculation()
        self._update_row_calculated_cells(row, assignment, component)

    def _style_row(self, row: int, assignment: FailureModeAssignment, component: Component):
        status, msgs = ValidationService.validate_row(assignment, component)
        status_item = self.table.item(row, 1)
        if not status_item:
            return
            
        if status == "error":
            status_item.setText("🔴")
            status_item.setToolTip("\n".join(msgs))
            bg = QColor("#f8d7da")
        elif status == "warning":
            status_item.setText("🟡")
            status_item.setToolTip("\n".join(msgs))
            bg = QColor("#fff3cd")
        else:
            status_item.setText("🟢")
            status_item.setToolTip("Clean")
            bg = QColor("#ffffff")
            
        for col in range(13):
            item = self.table.item(row, col)
            if item:
                item.setBackground(bg)
                
    def _on_import_bom_csv(self):
        existing_designators = (
            [c.position for c in self.unit.components] +
            [b.designator for b in self.unit.bom_components]
        )
        
        # 1. User selects a CSV file
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select BOM CSV File", "", "CSV Files (*.csv);;All Files (*.*)"
        )
        if not filepath:
            # Safely close, do not modify project
            return
            
        dialog = BOMImportDialog(existing_designators, filepath=filepath, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            imported = dialog.imported_components
            
            # Detect accidental duplicate imports
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
                
            # Add imported BOM components to the active functional group
            # Preserve existing components
            self.unit.bom_components.extend(new_imports)
            
            # Mark project as modified
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
        # Adds component type to canvas
        try:
            viewport = self.canvas.viewport()
            if viewport:
                center_pos = self.canvas.mapToScene(viewport.rect().center())
            else:
                center_pos = QPointF(0, 0)
        except Exception:
            center_pos = QPointF(0, 0)
            
        self._on_add_component_at_position(center_pos)
        
    def _on_add_bom_man_clicked(self):
        # Opens dialog to add BOM Component manually
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
            self.main_editor.project_changed.emit()
            QMessageBox.information(self, "Success", f"BOM Component '{des}' added manually.")
            
    def _on_manage_deviations_clicked(self):
        dialog = DeviationManagerDialog(self.project, self)
        dialog.exec()
        if self.stacked_view.currentIndex() == 0:
            self._load_fmeda_table()
            
    def _on_manage_mitigations_clicked(self):
        dialog = MitigationManagerDialog(self.project, self)
        dialog.exec()
        if self.stacked_view.currentIndex() == 0:
            self._load_fmeda_table()
            
    def _on_manage_dm_clicked(self):
        dialog = DiagnosticMeasureManagerDialog(self.project, self)
        dialog.exec()
        if self.stacked_view.currentIndex() == 0:
            self._load_fmeda_table()
            
    def _on_validate_clicked(self):
        if self.stacked_view.currentIndex() == 0:
            self._load_fmeda_table()
            QMessageBox.information(self, "Validation", "FMEDA spreadsheet validation complete. Check status indicator icons.")
        else:
            # Check overview metrics
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
        # calculations will be fully implemented in Increment 6
        if self.stacked_view.currentIndex() == 0:
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
        
        # Build dummy ComponentDB for visual item
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
        
        # Log change
        from fmeda_tool.services.project_service import ProjectService
        ProjectService.log_change(
            self.project,
            "Add Component",
            f"Added component '{component.position}' ({component.name}) to functional group '{self.unit.name}'."
        )
        
        self.main_editor.project_changed.emit()
        self._load_fmeda_table()
        self._trigger_recalculation()
        
    def _on_component_clicked(self, component_item: ComponentGraphicsItem):
        if not component_item.component_instance or not self.project:
            return
        dialog = ComponentInstanceDialog(component_item.component_instance, self.project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Log change
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
    """Page 2: Main FMEDA tabbed workspace supporting Project Overview and Functional Group Tabs"""
    
    save_requested = pyqtSignal()
    back_requested = pyqtSignal()
    next_requested = pyqtSignal()
    project_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.project: Optional[Project] = None
        self.current_unit: Optional[Unit] = None
        self.current_unit_index: int = 0
        self._setup_ui()
        self.project_changed.connect(self._on_project_changed)
        
    @property
    def add_comp_btn(self):
        tab = self.unit_tabs.currentWidget()
        if isinstance(tab, FunctionalGroupTab):
            return tab.add_comp_type_btn
        for idx in range(self.unit_tabs.count()):
            widget = self.unit_tabs.widget(idx)
            if isinstance(widget, FunctionalGroupTab):
                return widget.add_comp_type_btn
        if not hasattr(self, "_dummy_add_btn"):
            self._dummy_add_btn = QPushButton()
            self._dummy_add_btn.setEnabled(False)
        return self._dummy_add_btn

    @property
    def config_comp_btn(self):
        tab = self.unit_tabs.currentWidget()
        if isinstance(tab, FunctionalGroupTab):
            return tab.add_bom_man_btn
        for idx in range(self.unit_tabs.count()):
            widget = self.unit_tabs.widget(idx)
            if isinstance(widget, FunctionalGroupTab):
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
        
        self.edit_fg_btn = QPushButton("✏️ Edit Group")
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
                tab_widget.stacked_view.setCurrentIndex(0)
                
                # Map row_index (flat index of failure mode) to the actual table row containing that item
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
                if target_comp and target_fm:
                    for r in range(tab_widget.table.rowCount()):
                        item0 = tab_widget.table.item(r, 0)
                        item7 = tab_widget.table.item(r, 7)
                        comp_in_row = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
                        if comp_in_row == target_comp and item7 and item7.text() == target_fm:
                            actual_table_row = r
                            break
                            
                if actual_table_row >= 0:
                    tab_widget.table.setCurrentCell(actual_table_row, 0)
                    tab_widget.table.scrollToItem(tab_widget.table.item(actual_table_row, 0))

    def load_project(self, project: Project):
        self.project = project
        self.project_name_label.setText(project.name)
        status_str = project.status.value.replace("_", " ").title() if project.status else "Draft"
        self.project_status_label.setText(f"Status: {status_str}")
        
        self.add_fg_btn.setEnabled(True)
        self.edit_fg_btn.setEnabled(True)
        self.remove_fg_btn.setEnabled(True)
        
        while self.unit_tabs.count() > 1:
            self.unit_tabs.removeTab(1)
            
        self.overview_tab.refresh(project)
        
        if project.units:
            for unit in project.units:
                fg_tab = FunctionalGroupTab(unit, project, self)
                self.unit_tabs.addTab(fg_tab, unit.name)
                
            # Restore active tab
            if project.last_active_tab_id == "overview" or not project.last_active_tab_id:
                self.unit_tabs.setCurrentIndex(0)
            else:
                restored = False
                for idx, u in enumerate(project.units):
                    if u.id == project.last_active_tab_id:
                        self.unit_tabs.setCurrentIndex(idx + 1)
                        restored = True
                        break
                if not restored:
                    self.unit_tabs.setCurrentIndex(0)
        else:
            self.unit_tabs.setCurrentIndex(0)
            
    def _on_undo_clicked(self):
        if hasattr(self, "main_window"):
            self.main_window._on_undo()
            
    def _on_tab_changed(self, idx: int):
        if idx == 0:
            self.current_unit = None
            self.current_unit_index = 0
            if self.project:
                self.overview_tab.refresh(self.project)
        else:
            if self.project and idx - 1 < len(self.project.units):
                self.current_unit_index = idx - 1
                self.current_unit = self.project.units[self.current_unit_index]
                
    def _on_project_changed(self):
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
            if isinstance(tab_widget, FunctionalGroupTab):
                tab_widget.unit = dialog.fg
                tab_widget._load_fmeda_table()
                
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
