"""
Custom QStyledItemDelegate editors for FMEDA table cells:
- FmedaComboBoxDelegate: Temporary QComboBox editor for dropdown columns.
- FmedaSpinBoxDelegate: Temporary QDoubleSpinBox editor for numerical percentage columns.
- FmedaLineEditDelegate: Temporary QLineEdit editor for text columns.

Editors are created only when a cell is actively edited and destroyed immediately upon commit/cancel.
"""

from PyQt6.QtWidgets import (
    QStyledItemDelegate, QComboBox, QDoubleSpinBox, QLineEdit, QWidget, QStyleOptionViewItem
)
from PyQt6.QtCore import Qt, QModelIndex, QEvent
from typing import Optional, List, Dict, Any, Callable


class FmedaComboBoxDelegate(QStyledItemDelegate):
    """
    Delegate that creates a single temporary QComboBox editor for dropdown cells.
    Uses shared cached choices and destroys the widget after editing completes.
    """
    def __init__(self, items_callback: Optional[Callable[[QModelIndex], List[Dict[str, Any]]]] = None, parent=None):
        super().__init__(parent)
        self.items_callback = items_callback

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        combo = QComboBox(parent)
        combo.setFrame(False)
        combo.setStyleSheet("QComboBox { background-color: white; padding: 2px 4px; border: 1px solid #0d6efd; }")
        
        # Populate options dynamically via callback or model data
        options = []
        if self.items_callback:
            options = self.items_callback(index)
        else:
            raw_options = index.data(Qt.ItemDataRole.UserRole + 1)
            if isinstance(raw_options, list):
                options = raw_options

        for opt in options:
            if isinstance(opt, dict):
                label = opt.get("label", "")
                data = opt.get("data", None)
                combo.addItem(label, data)
            elif isinstance(opt, tuple) and len(opt) == 2:
                combo.addItem(str(opt[0]), opt[1])
            else:
                combo.addItem(str(opt), opt)

        return combo

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if not isinstance(editor, QComboBox):
            return
        current_data = index.data(Qt.ItemDataRole.EditRole)
        current_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        
        # Try finding by UserRole data first
        found_idx = -1
        if current_data is not None:
            found_idx = editor.findData(current_data)
        if found_idx < 0 and current_text:
            found_idx = editor.findText(current_text)
            
        if found_idx >= 0:
            editor.setCurrentIndex(found_idx)
        elif editor.count() > 0:
            editor.setCurrentIndex(0)

    def setModelData(self, editor: QWidget, model, index: QModelIndex) -> None:
        if not isinstance(editor, QComboBox):
            return
        selected_data = editor.currentData()
        selected_text = editor.currentText()
        model.setData(index, selected_data if selected_data is not None else selected_text, Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        editor.setGeometry(option.rect)


class FmedaSpinBoxDelegate(QStyledItemDelegate):
    """
    Delegate that creates a single temporary QDoubleSpinBox editor for numerical percentage cells.
    """
    def __init__(
        self,
        min_val: float = 0.0,
        max_val: float = 100.0,
        step: float = 1.0,
        decimals: int = 2,
        suffix: str = "%",
        parent=None
    ):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.decimals = decimals
        self.suffix = suffix

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        spin = QDoubleSpinBox(parent)
        spin.setFrame(False)
        spin.setRange(self.min_val, self.max_val)
        spin.setSingleStep(self.step)
        spin.setDecimals(self.decimals)
        if self.suffix:
            spin.setSuffix(self.suffix)
        spin.setStyleSheet("QDoubleSpinBox { background-color: white; padding: 2px 4px; border: 1px solid #0d6efd; }")
        return spin

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if not isinstance(editor, QDoubleSpinBox):
            return
        raw_val = index.data(Qt.ItemDataRole.EditRole)
        try:
            val = float(raw_val) if raw_val is not None else 0.0
        except (ValueError, TypeError):
            val = 0.0
        editor.setValue(val)

    def setModelData(self, editor: QWidget, model, index: QModelIndex) -> None:
        if not isinstance(editor, QDoubleSpinBox):
            return
        model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        editor.setGeometry(option.rect)


class FmedaLineEditDelegate(QStyledItemDelegate):
    """
    Delegate that creates a single temporary QLineEdit editor for text cells.
    """
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.placeholder = placeholder

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        line_edit = QLineEdit(parent)
        line_edit.setFrame(False)
        if self.placeholder:
            line_edit.setPlaceholderText(self.placeholder)
        line_edit.setStyleSheet("QLineEdit { background-color: white; padding: 2px 4px; border: 1px solid #0d6efd; }")
        return line_edit

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if not isinstance(editor, QLineEdit):
            return
        val = index.data(Qt.ItemDataRole.EditRole)
        editor.setText(str(val) if val is not None else "")

    def setModelData(self, editor: QWidget, model, index: QModelIndex) -> None:
        if not isinstance(editor, QLineEdit):
            return
        model.setData(index, editor.text().strip(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        editor.setGeometry(option.rect)
