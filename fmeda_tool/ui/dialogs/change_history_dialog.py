"""Read-only audit facts with a separately editable change comment."""
import json
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QAbstractItemView, QHeaderView,
                             QDialogButtonBox, QInputDialog)
from fmeda_tool.services.change_history_service import ChangeHistoryService


class ChangeHistoryDialog(QDialog):
    comment_changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle(f"Project Change History - {project.name}")
        self.resize(1100, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Automatic audit facts are read-only. Editing a comment does not alter the original audit facts."))
        self.table = QTableWidget()
        self._configure(self.table, ["Timestamp", "User", "Action", "Affected Object", "Automatic Details", "Comment / Change Reason"])
        layout.addWidget(self.table)
        self.table.setRowCount(len(project.change_history))
        for row, entry in enumerate(project.change_history):
            for column, key in enumerate(("timestamp", "user", "action", "affected_object", "details", "comment")):
                item = QTableWidgetItem(str(entry.get(key, "")))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row, column, item)
        self.edit_comment_button = QPushButton("Add / Edit Comment")
        self.edit_comment_button.clicked.connect(self._edit_comment)
        layout.addWidget(self.edit_comment_button)
        layout.addWidget(QLabel("Individual changes in the selected save (read-only):"))
        self.details_table = QTableWidget()
        self._configure(self.details_table, ["Action", "Affected Object / Field", "Old Value", "New Value", "Automatic Details"])
        layout.addWidget(self.details_table)
        self.table.itemSelectionChanged.connect(self._show_details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)
        if project.change_history:
            self.table.selectRow(len(project.change_history) - 1)

    @staticmethod
    def _configure(table, headers):
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)

    def _show_details(self):
        row = self.table.currentRow()
        if row < 0:
            return
        entry = self.project.change_history[row]
        changes = entry.get("changes") or [entry]
        self.details_table.setRowCount(len(changes))
        for r, change in enumerate(changes):
            values = [change.get("action", ""), change.get("field", change.get("affected_object", "")),
                      change.get("old_value"), change.get("new_value"), change.get("details", "")]
            for c, value in enumerate(values):
                if not isinstance(value, str):
                    value = json.dumps(value, ensure_ascii=False, indent=2)
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setToolTip(value)
                self.details_table.setItem(r, c, item)

    def set_comment(self, row, comment):
        if ChangeHistoryService.update_comment(self.project, row, comment):
            self.table.item(row, 5).setText(comment)
            self.comment_changed.emit()

    def _edit_comment(self):
        row = self.table.currentRow()
        if row < 0:
            return
        comment, accepted = QInputDialog.getMultiLineText(
            self, "Edit Change Comment", "Comment / Change Reason (audit facts remain unchanged):",
            self.project.change_history[row].get("comment", ""))
        if accepted:
            self.set_comment(row, comment)
