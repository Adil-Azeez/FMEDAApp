import unittest
import os
import tempfile
from pathlib import Path
from typing import List, Dict
from unittest.mock import patch

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QTableWidget, QLineEdit,
    QRadioButton, QDoubleSpinBox, QTextEdit, QSplitter, QGroupBox
)
from PyQt6.QtCore import Qt

from fmeda_tool.models import (
    Project, Unit, Component, BOMComponent, ComponentDB, ComponentMapping,
    FailureModeAssignment, SafetyStandard, ProjectStatus
)
from fmeda_tool.services import CalculationService, ProjectService, ImportService
from fmeda_tool.ui.dialogs.component_mapping_dialog import (
    ComponentMappingDialog, parse_range_expression, format_position_ranges
)
from fmeda_tool.ui.unit_editor_view import FunctionalGroupTab, UnitEditorView

app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestComponentBOMMappingWorkspace(unittest.TestCase):
    """
    Test suite for the integrated Component and BOM Mapping workspace in FMEDA Tool.
    Verifies:
    1. Default window size and responsive layout (1420x880 default, compact header).
    2. Embedded Component Library browsing (Exida and Legacy).
    3. Failure Mode Distribution table visibility without clipping and read-only metadata.
    4. Removal of Notes field and compact 2x2 configuration grid.
    5. Workspace opening without pre-existing BOM.
    6. In-workspace BOM TXT import.
    7. Multi-position and range mapping (C3-C15).
    8. Toolbar button simplification on FunctionalGroupTab.
    9. Atomic Save Mappings creating single instances per mapped Pos.
    10. Save and reload project equality and calculation consistency.
    """

    def setUp(self):
        self.unit = Unit(
            id="unit_power",
            name="Power Supply Subsystem",
            description="Power regulation and conditioning",
            components=[],
            bom_components=[],
            component_templates=[]
        )
        self.project = Project(
            id="proj_workspace_test",
            name="Workspace Test Project",
            description="Testing integrated component and BOM workspace",
            status=ProjectStatus.DRAFT,
            safety_standard=SafetyStandard.IEC_61508,
            target_sil="SIL 2",
            selected_profile="Profile 1",
            units=[self.unit]
        )

    def test_workspace_opens_without_bom_and_correct_dimensions(self):
        """Workspace opens cleanly with increased default dimensions (1420x880) and empty BOM placeholder."""
        self.assertEqual(len(self.unit.bom_components), 0)
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        self.assertIsNotNone(dialog)
        self.assertIn("Component", dialog.windowTitle())
        self.assertIn("Power Supply Subsystem", dialog.windowTitle())
        
        # Sizing assertions
        self.assertGreaterEqual(dialog.width(), 1400)
        self.assertGreaterEqual(dialog.height(), 860)
        self.assertGreaterEqual(dialog.minimumWidth(), 950)
        self.assertGreaterEqual(dialog.minimumHeight(), 550)
        
        # Splitters exist
        self.assertTrue(hasattr(dialog, "main_splitter"))
        self.assertTrue(hasattr(dialog, "left_splitter"))
        self.assertIsInstance(dialog.main_splitter, QSplitter)
        self.assertIsInstance(dialog.left_splitter, QSplitter)
        
        # BOM table shows empty notification row
        self.assertEqual(dialog.bom_table.rowCount(), 1)
        first_item = dialog.bom_table.item(0, 0)
        self.assertIn("No BOM components loaded", first_item.text())

    def test_component_library_loads_exida_and_legacy(self):
        """Component Library table in workspace loads Exida components and can toggle to Legacy."""
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        
        # Default: Exida radio is checked
        self.assertTrue(dialog.exida_radio.isChecked())
        self.assertGreater(dialog.lib_table.rowCount(), 0)
        
        # Toggle to Legacy Unmapped
        dialog.legacy_radio.setChecked(True)
        self.assertTrue(dialog.legacy_radio.isChecked())
        self.assertGreater(dialog.lib_table.rowCount(), 0)
        
        # Toggle back to Exida
        dialog.exida_radio.setChecked(True)
        self.assertGreater(dialog.lib_table.rowCount(), 0)

    def test_library_search_and_category_filter(self):
        """Search input and category dropdown filter the component library table."""
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        
        initial_count = dialog.lib_table.rowCount()
        self.assertGreater(initial_count, 10)
        
        # Search specific term present in database
        dialog.lib_search_input.setText("Capacitor")
        filtered_count = dialog.lib_table.rowCount()
        self.assertGreater(filtered_count, 0)
        self.assertLessEqual(filtered_count, initial_count)
        
        # Clear search
        dialog.lib_search_input.setText("")
        self.assertEqual(dialog.lib_table.rowCount(), initial_count)

    def test_failure_modes_distribution_visible_and_readonly(self):
        """Verify Failure Mode Distribution table is immediately visible, populated, and read-only without Notes field."""
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        
        # Select first component
        if dialog.lib_table.rowCount() > 0:
            dialog.lib_table.selectRow(0)
            
        self.assertIsNotNone(dialog.selected_template)
        
        # Editable fields
        self.assertFalse(dialog.cfg_label_input.isReadOnly())
        self.assertFalse(dialog.cfg_value_input.isReadOnly())
        
        # Read-only fields
        self.assertTrue(dialog.cfg_type_input.isReadOnly())
        self.assertTrue(dialog.cfg_fit_input.isReadOnly())
        
        # Notes field must NOT exist as a configuration input
        self.assertFalse(hasattr(dialog, "notes_input"))
        self.assertFalse(hasattr(dialog, "cfg_notes_input"))
        
        # Failure modes table: minimum height allocated, visible rows, not editable
        fm_table = dialog.cfg_fm_table
        self.assertGreaterEqual(fm_table.minimumHeight(), 120)
        self.assertGreater(fm_table.rowCount(), 0)
        for row in range(fm_table.rowCount()):
            for col in range(fm_table.columnCount()):
                item = fm_table.item(row, col)
                if item:
                    self.assertFalse(bool(item.flags() & Qt.ItemFlag.ItemIsEditable))

    def test_toolbar_button_simplification_on_functional_group_tab(self):
        """Verify toolbar on FunctionalGroupTab contains Component & BOM Mapping and removes old buttons."""
        editor = UnitEditorView()
        editor.load_project(self.project)
        
        # Select unit tab (tab index 1, index 0 is overview)
        editor.unit_tabs.setCurrentIndex(1)
        tab = editor.unit_tabs.currentWidget()
        self.assertIsInstance(tab, FunctionalGroupTab)
        
        # The new button must exist and be visible
        self.assertTrue(hasattr(tab, "map_bom_btn"))
        self.assertEqual(tab.map_bom_btn.text(), "Component & BOM Mapping")
        
        # Old buttons must NOT be present on the toolbar layout
        toolbar_buttons = [tab.toolbar.itemAt(i).widget() for i in range(tab.toolbar.count()) if tab.toolbar.itemAt(i).widget() and isinstance(tab.toolbar.itemAt(i).widget(), QPushButton)]
        toolbar_btn_texts = [b.text() for b in toolbar_buttons]
        
        self.assertIn("Component & BOM Mapping", toolbar_btn_texts)
        self.assertNotIn("Add Component Type", toolbar_btn_texts)
        self.assertNotIn("Add Component Manually", toolbar_btn_texts)
        self.assertNotIn("Import BOM TXT", toolbar_btn_texts)

    @patch("PyQt6.QtWidgets.QMessageBox.information")
    @patch("PyQt6.QtWidgets.QMessageBox.warning")
    def test_batch_mapping_workflow_with_range_selection(self, mock_warn, mock_info):
        """Test complete workflow: select library component -> select range C3-C15 -> apply -> save."""
        # Populate BOM items C1..C20
        bom_items = [
            BOMComponent(
                id=f"bom_c{i}",
                designator=f"C{i}",
                part_number="00554433",
                benennung="KERAMIK-KONDENSATOR",
                value="100n",
                description="CAP Ceramic 100nF 50V 0603",
                layer="TOP",
                is_fitted=True
            )
            for i in range(1, 21)
        ]
        self.unit.bom_components = bom_items
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        self.assertEqual(dialog.bom_table.rowCount(), 20)
        
        # Search and select Capacitor
        dialog.lib_search_input.setText("Capacitor")
        self.assertGreater(dialog.lib_table.rowCount(), 0)
        dialog.lib_table.selectRow(0)
        self.assertIsNotNone(dialog.selected_template)
        
        # Select range C3-C15
        available = [b.designator for b in self.unit.bom_components]
        matched = parse_range_expression("C3-C15", available)
        self.assertEqual(len(matched), 13)
        for pos in matched:
            cb = dialog.bom_checkboxes.get(pos.upper())
            if cb:
                cb.setChecked(True)
                
        # Apply selection
        dialog._on_apply_selection()
        
        # Verify 13 positions are staged
        self.assertEqual(len(dialog.staged_mappings), 13)
        for i in range(3, 16):
            self.assertIn(f"C{i}", dialog.staged_mappings)
            
        # Commit mappings
        dialog._commit_mappings()
        
        # Verify exactly 13 components created in self.unit.components
        self.assertEqual(len(self.unit.components), 13)
        positions = [c.position for c in self.unit.components]
        for i in range(3, 16):
            self.assertIn(f"C{i}", positions)
            
        # Verify component properties
        c3 = next(c for c in self.unit.components if c.position == "C3")
        self.assertEqual(c3.position, "C3")
        self.assertEqual(c3.internal_pn, "00554433")
        self.assertEqual(c3.value, "100n / CAP Ceramic 100nF 50V 0603")
        self.assertEqual(c3.fitted_status, "Fitted")
        self.assertGreater(len(c3.failure_mode_assignments), 0)

    @patch("PyQt6.QtWidgets.QMessageBox.information")
    @patch("PyQt6.QtWidgets.QMessageBox.warning")
    def test_not_fitted_bom_handling(self, mock_warn, mock_info):
        """BOM items with 'nicht bestueckt' in notes are mapped with fitted_status = 'Not Fitted'."""
        self.unit.bom_components = [
            BOMComponent(id="bom_r1", designator="R1", part_number="0011", value="10k", description="RES 10k", layer="TOP", is_fitted=True),
            BOMComponent(id="bom_r2", designator="R2", part_number="0012", value="20k", description="RES 20k", layer="BOT", is_fitted=False, notes="nicht bestueckt")
        ]
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        dialog.lib_search_input.setText("Resistor")
        if dialog.lib_table.rowCount() > 0:
            dialog.lib_table.selectRow(0)
            
        dialog.bom_checkboxes["R1"].setChecked(True)
        dialog.bom_checkboxes["R2"].setChecked(True)
        dialog._on_apply_selection()
        dialog._commit_mappings()
        
        self.assertEqual(len(self.unit.components), 2)
        r1 = next(c for c in self.unit.components if c.position == "R1")
        r2 = next(c for c in self.unit.components if c.position == "R2")
        self.assertEqual(r1.fitted_status, "Fitted")
        self.assertEqual(r2.fitted_status, "Not Fitted")

    @patch("PyQt6.QtWidgets.QMessageBox.information")
    @patch("PyQt6.QtWidgets.QMessageBox.warning")
    def test_save_reopen_and_calculation_equality(self, mock_warn, mock_info):
        """Test atomic save, reload, and calculation equality with the integrated workspace."""
        temp_dir = tempfile.mkdtemp()
        try:
            proj_path = os.path.join(temp_dir, "workspace_mapped_project.json")
            
            bom_items = [
                BOMComponent(id=f"bom_c{i}", designator=f"C{i}", part_number="009988", value="100n", description="CAP 100nF", layer="TOP", is_fitted=True)
                for i in range(101, 114)  # 13 items: C101 to C113
            ]
            self.unit.bom_components = bom_items
            
            dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
            dialog.lib_search_input.setText("Capacitor")
            if dialog.lib_table.rowCount() > 0:
                dialog.lib_table.selectRow(0)
                
            for b in bom_items:
                cb = dialog.bom_checkboxes.get(b.designator.upper())
                if cb:
                    cb.setChecked(True)
                    
            dialog._on_apply_selection()
            dialog._commit_mappings()
            
            # Initial calculations
            calc1 = CalculationService.calculate_project(self.project)
            fit1 = self.project.lambda_total_gesamtgerat
            sff1 = self.project.sff_gesamtgerat
            self.assertGreater(fit1, 0.0)
            
            # Save project to JSON using ProjectService
            ProjectService.save_project_atomically(self.project, proj_path)
            self.assertTrue(os.path.exists(proj_path))
            
            # Reload project
            loaded_proj, _, _ = ProjectService.load_and_migrate_project(proj_path)
            self.assertEqual(len(loaded_proj.units), 1)
            loaded_unit = loaded_proj.units[0]
            self.assertEqual(len(loaded_unit.components), 13)
            
            # Recalculate on reloaded project
            calc2 = CalculationService.calculate_project(loaded_proj)
            self.assertAlmostEqual(loaded_proj.lambda_total_gesamtgerat, fit1, places=4)
            self.assertAlmostEqual(loaded_proj.sff_gesamtgerat, sff1, places=2)
            
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_component_library_column_widths_and_resize_mode(self):
        """Verify Display Label column width default, interactive resize mode, and persistence."""
        from PyQt6.QtWidgets import QHeaderView
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        
        hdr = dialog.lib_table.horizontalHeader()
        self.assertEqual(hdr.minimumSectionSize(), 75)
        self.assertEqual(hdr.sectionResizeMode(0), QHeaderView.ResizeMode.Interactive)
        self.assertEqual(hdr.sectionResizeMode(1), QHeaderView.ResizeMode.Stretch)
        self.assertEqual(hdr.sectionResizeMode(2), QHeaderView.ResizeMode.Interactive)
        self.assertEqual(hdr.sectionResizeMode(3), QHeaderView.ResizeMode.Interactive)
        self.assertGreaterEqual(dialog.lib_table.columnWidth(0), 180)
        
        # User resizes column 0
        dialog.lib_table.setColumnWidth(0, 260)
        # Search stroke
        dialog.lib_search_input.setText("Capacitor")
        self.assertEqual(dialog.lib_table.columnWidth(0), 260)

    @patch("PyQt6.QtWidgets.QMessageBox.information")
    @patch("PyQt6.QtWidgets.QMessageBox.warning")
    def test_current_mapping_column_shows_library_display_name(self, mock_warn, mock_info):
        """Verify BOM Positions table Column 8 displays library component display label (✓ CKP/CEL/etc.) and not BOM benennung."""
        bom_item = BOMComponent(
            id="bom_c1", designator="C1", part_number="001122",
            benennung="SCAP-VS", value="100n", description="Keramikkondensator",
            layer="TOP", is_fitted=True
        )
        self.unit.bom_components = [bom_item]
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        # Initial unmapped
        map_item = dialog.bom_table.item(0, 8)
        self.assertIn("Unmapped", map_item.text())
        
        # Select first library component
        if dialog.lib_table.rowCount() > 0:
            dialog.lib_table.selectRow(0)
            selected_disp_name = dialog.selected_template.display_name
            self.assertTrue(bool(selected_disp_name))
            
            dialog.bom_checkboxes["C1"].setChecked(True)
            dialog._on_apply_selection()
            
            # Verify Column 8 shows ✓ {selected_disp_name} and NOT "SCAP-VS"
            map_item_after = dialog.bom_table.item(0, 8)
            self.assertEqual(map_item_after.text(), f"✓ {selected_disp_name}")
            self.assertNotIn("SCAP-VS", map_item_after.text())
            
            # Commit mappings
            dialog._commit_mappings()
            
            # Reopen dialog for this unit and verify staged mapping retains library display label
            reopened_dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
            reopened_item = reopened_dialog.bom_table.item(0, 8)
            self.assertEqual(reopened_item.text(), f"✓ {selected_disp_name}")
            self.assertNotIn("SCAP-VS", reopened_item.text())

    @patch("PyQt6.QtWidgets.QMessageBox.information")
    @patch("PyQt6.QtWidgets.QMessageBox.warning")
    def test_fmeda_table_model_and_export_display_name_header_and_value(self, mock_warn, mock_info):
        """Verify FMEDA table model header is 'Display Name / Component Type' and renders library display label."""
        from fmeda_tool.ui.models.fmeda_table_model import FmedaTableModel, COLUMN_HEADERS
        self.assertEqual(COLUMN_HEADERS[5], "Display Name / Component Type")
        
        # Map a component
        self.unit.bom_components = [
            BOMComponent(id="bom_c1", designator="C1", benennung="SCAP-VS", value="100n", is_fitted=True)
        ]
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1", project=self.project)
        if dialog.lib_table.rowCount() > 0:
            dialog.lib_table.selectRow(0)
            lib_label = dialog.selected_template.display_name
            dialog.bom_checkboxes["C1"].setChecked(True)
            dialog._on_apply_selection()
            dialog._commit_mappings()
            
            model = FmedaTableModel(self.unit, self.project)
            self.assertEqual(model.columnCount(), 37)
            self.assertEqual(model.headerData(5, Qt.Orientation.Horizontal), "Display Name / Component Type")
            # Row 0 col 5 value
            cell_val = model.data(model.index(0, 5), Qt.ItemDataRole.DisplayRole)
            self.assertEqual(cell_val, lib_label)


if __name__ == "__main__":
    unittest.main()
