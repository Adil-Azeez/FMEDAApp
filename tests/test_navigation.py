import unittest
import sys

try:
    from PyQt6.QtWidgets import QApplication
    from fmeda_tool.ui.main_window import MainWindow
    pyqt_available = True
except ImportError:
    pyqt_available = False

if pyqt_available:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)


import os
offscreen = os.environ.get("QT_QPA_PLATFORM") == "offscreen"


from unittest.mock import patch

class TestNavigationWorkflow(unittest.TestCase):
    
    @unittest.skipUnless(pyqt_available and not offscreen, "PyQt6 is not available/loadable/offscreen in this environment")
    @patch("fmeda_tool.ui.verification_view.QMessageBox.warning")
    def test_navigation_flow_increments(self, mock_warn):
        from fmeda_tool.ui.main_menu import MainMenu
        window = MainWindow()
        main_menu = MainMenu()
        window.add_view("main_menu", main_menu)
        window.show_view("main_menu")
        
        # Initially, main_menu is shown
        current = window.get_current_view()
        # Find which view name maps to this widget
        view_name = None
        for name, widget in window.views.items():
            if widget == current:
                view_name = name
                break
        self.assertEqual(view_name, "main_menu")
        
        # 1. Trigger New Project -> Shows Page 1 (create_project)
        window._on_new_project()
        current = window.get_current_view()
        view_name = None
        for name, widget in window.views.items():
            if widget == current:
                view_name = name
                break
        self.assertEqual(view_name, "create_project")
        
        # 2. Page 1 Form filling
        page1 = window.create_project_view
        page1.name_input.setText("Test Navigation Project")
        page1.number_input.setText("NAV-123")
        page1.description_input.setPlainText("Description details")
        
        # Click Next -> Triggers _on_project_created and goes to Page 2 (unit_editor)
        page1.next_btn.click()
        current = window.get_current_view()
        view_name = None
        for name, widget in window.views.items():
            if widget == current:
                view_name = name
                break
        self.assertEqual(view_name, "unit_editor")
        self.assertEqual(window.current_project.name, "Test Navigation Project")
        
        # 3. Page 2 footer transitions -> Back button goes back to Page 1
        window.unit_editor_view.back_btn.click()
        current = window.get_current_view()
        view_name = None
        for name, widget in window.views.items():
            if widget == current:
                view_name = name
                break
        self.assertEqual(view_name, "create_project")
        
        # Go to Page 2 again
        page1.next_btn.click()
        
        # Page 2 Next button -> goes to Page 3 (verification)
        window.unit_editor_view.next_btn.click()
        current = window.get_current_view()
        view_name = None
        for name, widget in window.views.items():
            if widget == current:
                view_name = name
                break
        self.assertEqual(view_name, "verification")
        
        # 4. Page 3 Next to Export -> goes to Page 4 (export_view)
        window.verification_view.next_btn.click()
        current = window.get_current_view()
        view_name = None
        for name, widget in window.views.items():
            if widget == current:
                view_name = name
                break
        self.assertEqual(view_name, "export_view")
        
        # Page 4 Back button -> goes to Page 3
        window.export_view.back_btn.click()
        current = window.get_current_view()
        view_name = None
        for name, widget in window.views.items():
            if widget == current:
                view_name = name
                break
        self.assertEqual(view_name, "verification")


if __name__ == "__main__":
    unittest.main()
