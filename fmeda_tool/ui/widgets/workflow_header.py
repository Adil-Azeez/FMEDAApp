"""
WorkflowPageHeader: Reusable, centered header widget for workflow Pages 1 to 4.
Guarantees consistent layout, styling, typography, and true full-page centering
of the title across window resizes while safely accommodating left-side metadata
and right-side action buttons.
"""

from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class WorkflowPageHeader(QFrame):
    """
    Standard workflow page header that centers the page title relative to the full
    page width across all window sizes, matching Page 1's font, weight, spacing,
    and bottom separator style.
    """
    def __init__(self, page_title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background-color: #f8f9fa; border-bottom: 2px solid #dee2e6; }")
        self.setFixedHeight(65)
        
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setContentsMargins(25, 6, 25, 6)
        self.grid_layout.setSpacing(10)
        
        # Left container (left-aligned) for project name, status or metadata
        self.left_container = QWidget()
        self.left_layout = QHBoxLayout(self.left_container)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(10)
        self.grid_layout.addWidget(self.left_container, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Center container & title (strictly centered relative to full header width)
        self.title_label = QLabel(page_title)
        self.title_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #212529;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid_layout.addWidget(self.title_label, 0, 1, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        
        # Right container (right-aligned) for buttons and actions
        self.right_container = QWidget()
        self.right_layout = QHBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(8)
        self.grid_layout.addWidget(self.right_container, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # Column stretch: equal stretch on columns 0 and 2 keeps column 1 centered
        self.grid_layout.setColumnStretch(0, 1)
        self.grid_layout.setColumnStretch(1, 0)
        self.grid_layout.setColumnStretch(2, 1)
        
    def set_title(self, title: str) -> None:
        """Updates the centered page title."""
        self.title_label.setText(title)
