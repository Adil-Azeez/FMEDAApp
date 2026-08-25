

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QGridLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPixmap, QIcon


class MainMenuCard(QFrame):
    """A card widget for main menu options"""
    
    clicked = pyqtSignal()
    
    def __init__(self, title: str, description: str, icon_text: str = "📋"):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Set responsive size constraints (minimum and preferred)
        self.setMinimumSize(150, 120)
        self.setMaximumSize(300, 240)
        
        # Set size policy to expand with available space
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Apply stylesheet
        self.setStyleSheet("""
            MainMenuCard {
                background-color: #f8f9fa;
                border: 2px solid #dee2e6;
                border-radius: 10px;
            }
            MainMenuCard:hover {
                background-color: #e9ecef;
                border: 2px solid #0d6efd;
            }
        """)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        
        # Icon label
        icon_label = QLabel(icon_text)
        icon_font = QFont()
        icon_font.setPointSize(38)
        icon_label.setFont(icon_font)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(description)
        desc_font = QFont()
        desc_font.setPointSize(9)
        desc_label.setFont(desc_font)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #6c757d;")

        
    def mousePressEvent(self, event):
        """Handle mouse click"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
    
    def sizeHint(self):
        """Provide preferred size hint for the card"""
        return QSize(200, 160)


class MainMenu(QWidget):
    """Main menu / landing page widget"""
    
    # Signals for navigation
    new_project_clicked = pyqtSignal()
    open_project_clicked = pyqtSignal()
    components_db_clicked = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)
        
        # Header Section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(10)
        
        # Title
        title_label = QLabel("FMEDA Tool")
        title_font = QFont()
        title_font.setPointSize(32)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #212529;")
        header_layout.addWidget(title_label)
        
        # Subtitle
        subtitle_label = QLabel("Failure Mode, Effects and Diagnostic Analysis")
        subtitle_font = QFont()
        subtitle_font.setPointSize(14)
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setStyleSheet("color: #6c757d;")
        header_layout.addWidget(subtitle_label)
        
        main_layout.addLayout(header_layout)
        main_layout.addSpacing(20)
        
        # Cards Grid
        cards_layout = QGridLayout()
        cards_layout.setSpacing(20)
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Main cards
        new_project_card = MainMenuCard(
            "New Project",
            "Create a new FMEDA analysis project",
            "📄"
        )
        new_project_card.clicked.connect(self.new_project_clicked.emit)
        cards_layout.addWidget(new_project_card, 0, 0)
        
        open_project_card = MainMenuCard(
            "Open Project",
            "Open an existing project",
            "📂"
        )
        open_project_card.clicked.connect(self.open_project_clicked.emit)
        cards_layout.addWidget(open_project_card, 0, 1)
        
        components_db_card = MainMenuCard(
            "Components Database",
            "Manage reusable component templates",
            "🗄️"
        )
        components_db_card.clicked.connect(self.components_db_clicked.emit)
        cards_layout.addWidget(components_db_card, 0, 2)
        
        main_layout.addLayout(cards_layout)
        
        # Add stretch to push everything to top
        main_layout.addStretch()
