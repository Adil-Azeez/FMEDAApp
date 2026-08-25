
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from fmeda_tool.ui import MainWindow, MainMenu


def main():
    """Main application entry point"""
    print("="*70)
    print("FMEDA Tool - Failure Mode, Effects and Diagnostic Analysis")
    print("="*70)
    print("\nApplication starting...")
    
    # Configure global exception handler
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
            
        import traceback
        err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print("\n[UNHANDLED UI EXCEPTION] Traceback:", file=sys.stderr)
        print(err_msg, file=sys.stderr)
        
        try:
            from pathlib import Path
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / "error.log"
            with open(log_file, "a", encoding="utf-8") as f:
                from datetime import datetime
                f.write(f"\n=== ERROR LOGGED AT {datetime.now()} ===\n")
                f.write(err_msg)
                f.write("="*40 + "\n")
        except Exception as le:
            print(f"Failed to write to error log: {le}", file=sys.stderr)
            
        try:
            from PyQt6.QtWidgets import QMessageBox
            active_app = QApplication.instance()
            if active_app:
                # Find active main window to act as parent, if any
                parent_win = None
                for widget in active_app.topLevelWidgets():
                    if widget.isWindow() and widget.isVisible():
                        parent_win = widget
                        break
                msg_box = QMessageBox(parent_win)
                msg_box.setIcon(QMessageBox.Icon.Critical)
                msg_box.setWindowTitle("Application Error")
                msg_box.setText("An unexpected error occurred in the user interface.")
                msg_box.setInformativeText(str(exc_value))
                msg_box.setDetailedText(err_msg)
                msg_box.exec()
        except Exception as de:
            print(f"Failed to show error dialog: {de}", file=sys.stderr)

    sys.excepthook = handle_exception
    
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    # Create Qt application
    app = QApplication(sys.argv)
    

    
    # Create main window
    main_window = MainWindow()
    
    # Create and add main menu view
    main_menu = MainMenu()
    main_window.add_view("main_menu", main_menu)
    
    # Connect main menu signals to main window actions
    main_menu.new_project_clicked.connect(main_window._on_new_project)
    main_menu.open_project_clicked.connect(main_window._on_open_project)
    main_menu.components_db_clicked.connect(main_window._on_components_db)
    
    # Show main menu by default
    main_window.show_view("main_menu")
    
    # Show main window
    main_window.show()
    
    print("✓ Application launched successfully")
    print("\nGUI is now ready. Use the menu bar for navigation.")
    
    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
