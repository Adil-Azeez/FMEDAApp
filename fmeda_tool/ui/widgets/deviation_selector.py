from PyQt6.QtWidgets import QComboBox, QCompleter
from PyQt6.QtCore import Qt, QModelIndex, QSortFilterProxyModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem


class DeviationSelector(QComboBox):
    """Bounded search popup; only catalog IDs can be committed."""
    def __init__(self, options, parent=None):
        super().__init__(parent)
        for opt in options:
            self.addItem(opt["label"], opt["data"])
        self.setEditable(True)
        self.setFrame(False)
        self.setStyleSheet("QComboBox { background-color: white; padding: 2px 4px; border: 1px solid #0d6efd; }")
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(8)
        self.lineEdit().setPlaceholderText("Search name, description, impact or keywords...")
        source = QStandardItemModel(self)
        for opt in options:
            item = QStandardItem(opt["label"])
            item.setData(opt["data"], Qt.ItemDataRole.UserRole)
            item.setData(opt.get("search", opt["label"]), Qt.ItemDataRole.UserRole + 1)
            source.appendRow(item)
        proxy = QSortFilterProxyModel(self)
        proxy.setSourceModel(source)
        proxy.setFilterRole(Qt.ItemDataRole.UserRole + 1)
        proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer = QCompleter(proxy, self)
        completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        completer.setMaxVisibleItems(8)
        self.setCompleter(completer)
        self.search_proxy = proxy

        def filter_choices(text):
            proxy.setFilterFixedString(text)
            completer.complete()
        self.lineEdit().textEdited.connect(filter_choices)

        def select_match(match):
            self.setCurrentIndex(self.findData(match.data(Qt.ItemDataRole.UserRole)))
        completer.activated[QModelIndex].connect(select_match)

    def showPopup(self):
        self.lineEdit().setFocus()
        self.lineEdit().selectAll()
        self.search_proxy.setFilterFixedString("")
        self.completer().setCompletionPrefix("")
        self.completer().complete()
