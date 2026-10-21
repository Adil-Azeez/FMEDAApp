
import sys
from fmeda_tool.paths import logs_directory, resource_path, projects_directory
from fmeda_tool.version import APP_NAME, APP_VERSION, APP_DISPLAY_NAME


def main():
    """Main application entry point"""
    if len(sys.argv) == 3 and sys.argv[1] == "--deployment-check":
        from fmeda_tool.deployment_check import run
        return run(sys.argv[2])
    # PyInstaller --windowed has no stdout/stderr. Configure before UI imports,
    # which also initialize performance logging.
    log_dir = logs_directory()
    log_dir.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(log_dir / "application.log", "a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon
    from fmeda_tool.ui import MainWindow, MainMenu
    print("="*70)
    print(APP_DISPLAY_NAME + " - Failure Mode, Effects and Diagnostic Analysis")
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
            log_dir = logs_directory()
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

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(resource_path("assets", "FMEDA.ico"))))
    
    # Ensure SQLite component database is initialized
    from fmeda_tool.db import DatabaseService
    try:
        ready, db_msg = DatabaseService.ensure_database_ready()
    except Exception as error:
        ready, db_msg = False, str(error)
    print(f"Database status: {db_msg}")
    if not ready:
        QMessageBox.critical(None, "Database Initialization Failed", db_msg)
        return 1
    projects_directory().mkdir(parents=True, exist_ok=True)
    
    # Create Qt application
    

    
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
    
    print("[OK] Application launched successfully")
    print("\nGUI is now ready. Use the menu bar for navigation.")
    
    # Start event loop
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
