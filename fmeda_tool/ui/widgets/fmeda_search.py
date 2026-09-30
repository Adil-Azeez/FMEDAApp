"""Search controls over the existing source model, preserving component row indices."""
from PyQt6.QtCore import Qt, QItemSelectionModel, QModelIndex
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel, QPushButton, QAbstractItemView


class FmedaSearchBar(QWidget):
    def __init__(self, table, model, parent=None):
        super().__init__(parent)
        self.table, self.source_model = table, model
        self.matches = []
        self.active_match = -1
        self._updating = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search this functional group (all columns)…")
        self.count_label = QLabel("0 matches")
        self.previous_button = QPushButton("Previous Match")
        self.next_button = QPushButton("Next Match")
        self.clear_button = QPushButton("Clear Search")
        layout.addWidget(self.search_input, 1)
        for widget in (self.count_label, self.previous_button, self.next_button, self.clear_button):
            layout.addWidget(widget)
        self.search_input.textChanged.connect(self._query_changed)
        self.previous_button.clicked.connect(lambda: self.navigate(-1))
        self.next_button.clicked.connect(lambda: self.navigate(1))
        self.clear_button.clicked.connect(self.search_input.clear)
        model.modelReset.connect(self.refresh)
        model.dataChanged.connect(self._data_changed)
        self.refresh()

    def _query_changed(self):
        self.table.clear_component_selection()
        self.refresh()

    def _data_changed(self, first, last, roles=None):
        if not self._updating and (not roles or Qt.ItemDataRole.DisplayRole in roles):
            self.refresh()

    def refresh(self, *_):
        if self._updating:
            return
        self._updating = True
        try:
            old_row = self.matches[self.active_match] if self.matches and self.active_match >= 0 else None
            query = self.search_input.text().strip()
            self.matches, visible_rows = self.source_model.search_rows(query)
            for row in range(self.source_model.rowCount()):
                self.table.setRowHidden(row, bool(query) and row not in visible_rows)
            self.active_match = self.matches.index(old_row) if old_row in self.matches else (0 if self.matches else -1)
            self._show_match()
        finally:
            self._updating = False

    def navigate(self, direction):
        if self.matches:
            self.table.clear_component_selection()
            self.active_match = (self.active_match + direction) % len(self.matches)
            self._show_match()

    def _show_match(self):
        row = self.matches[self.active_match] if self.active_match >= 0 else None
        self.source_model.set_active_search_row(row)
        count = len(self.matches)
        self.count_label.setText(f"{self.active_match + 1} / {count} matches" if count else "0 matches")
        self.previous_button.setEnabled(bool(count))
        self.next_button.setEnabled(bool(count))
        if row is not None:
            # Hidden columns remain searchable; navigation focuses a visible cell in that row.
            column = next((c for c in range(self.source_model.columnCount()) if not self.table.isColumnHidden(c)), 0)
            index = self.source_model.index(row, column)
            self.table.selectionModel().setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
            self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        elif self.search_input.text().strip():
            self.table.selectionModel().clearSelection()
            self.table.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
        self.table.viewport().update()
