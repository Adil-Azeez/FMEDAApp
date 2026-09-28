"""
Responsive loading dialog for opening large FMEDA projects.
Displays structured progress stages, percentage indicators, and prevents UI freezing.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor


class ProjectLoadingDialog(QDialog):
    """Modal loading dialog showing project loading stages and progress."""
    
    def __init__(self, project_name: str = "FMEDA Project", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Opening FMEDA Project")
        self.setFixedSize(450, 180)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        self.setModal(True)
        self._setup_ui(project_name)
        
    def _setup_ui(self, project_name: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(12)
        
        # Header title
        self.title_lbl = QLabel(f"Loading: {project_name}")
        title_font = QFont("Arial", 11, QFont.Weight.Bold)
        self.title_lbl.setFont(title_font)
        self.title_lbl.setStyleSheet("color: #212529;")
        layout.addWidget(self.title_lbl)
        
        # Stage description label
        self.stage_lbl = QLabel("Initializing project loader...")
        self.stage_lbl.setStyleSheet("color: #495057; font-size: 12px;")
        layout.addWidget(self.stage_lbl)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ced4da;
                border-radius: 5px;
                text-align: center;
                height: 22px;
                background-color: #e9ecef;
                font-weight: bold;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #0d6efd;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Bottom note
        note_lbl = QLabel("Please wait while project models and failure modes are prepared.")
        note_lbl.setStyleSheet("color: #6c757d; font-size: 10px;")
        layout.addWidget(note_lbl)
        
    def update_stage(self, stage_text: str, percentage: int = -1):
        """Updates the stage description label and progress bar value."""
        self.stage_lbl.setText(stage_text)
        if percentage >= 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percentage)
        else:
            # Indeterminate mode
            self.progress_bar.setRange(0, 0)
            
        # Process pending Qt events to ensure immediate UI repainting
        QApplication.processEvents()

    def set_indeterminate(self, is_indeterminate: bool = True):
        """Toggles between indeterminate pulsing and determinate percentage modes."""
        if is_indeterminate:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
        QApplication.processEvents()
