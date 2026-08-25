import unittest
import os
import tempfile
import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from fmeda_tool.models import Project, ProjectStatus, SafetyStandard, Unit, Component, FailureModeAssignment, BOMComponent, ComponentDB
from fmeda_tool.services import ImportService, MappingService, ProjectService, CalculationService
from fmeda_tool.ui.dialogs.bom_import_dialog import BOMImportDialog
from fmeda_tool.ui.unit_editor_view import FunctionalGroupTab
from fmeda_tool.ui.main_window import MainWindow

app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestBOMImportAndMapping(unittest.TestCase):
    
    def test_comma_separated_csv(self):
        csv_content = "designator,value,description\nC101,10u,Capacitor\nR101,10k,Resistor"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].designator, "C101")
        self.assertEqual(parsed[1].designator, "R101")
        
    def test_semicolon_separated_csv(self):
        csv_content = "designator;value;description\nC101;10u;Capacitor\nR101;10k;Resistor"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].designator, "C101")
        
    def test_utf8_with_bom(self):
        # Simulate BOM by prepending \ufeff
        csv_content = "\ufeffdesignator,value\nC101,10u"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].designator, "C101")
        
    def test_english_headers_and_german_aliases(self):
        csv_content = "bauteil,wert,beschreibung,status\nC101,10u,Capacitor,bestückt"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0].designator, "C101")
        self.assertEqual(parsed[0].value, "10u")
        self.assertTrue(parsed[0].is_fitted)
        
    def test_quoted_commas_and_semicolons(self):
        csv_content = 'designator,description\nC101,"Capacitor, 10uF; 50V"'
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0].description, "Capacitor, 10uF; 50V")
        
    def test_fitted_normalization(self):
        # True options
        for val in ["true", "yes", "1", "fitted", "bestückt", "bestueckt", ""]:
            csv_content = f"designator,fitted\nC101,{val}"
            parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
            self.assertTrue(parsed[0].is_fitted)
            
        # False options
        for val in ["false", "no", "0", "not fitted", "not_fitted", "nicht bestückt", "nicht bestueckt", "dnp", "do not populate"]:
            csv_content = f"designator,fitted\nC101,{val}"
            parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
            self.assertFalse(parsed[0].is_fitted)
            
        # Unknown fitted value warning
        csv_content = "designator,fitted\nC101,maybe"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertTrue(parsed[0].is_fitted)
        self.assertTrue(any("Unrecognized fitted value" in w for w in warnings))
        
    def test_missing_designator_header(self):
        csv_content = "value,description\n10u,Capacitor"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 1)
        self.assertIn("Missing designator column", errors[0])
        
    def test_empty_designator_row(self):
        csv_content = "designator,value\n,10u"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 1)
        self.assertIn("Empty designator in a data row", errors[0])
        
    def test_duplicate_designators_in_csv(self):
        csv_content = "designator,value\nC101,10u\nC101,100n"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 1)
        self.assertIn("Duplicate designator 'C101' found inside the CSV", errors[0])
        
    def test_duplicate_against_existing_functional_group_data(self):
        csv_content = "designator,value\nC101,10u"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content, existing_designators=["C101"])
        self.assertEqual(len(errors), 0)
        self.assertTrue(any("existing functional-group data" in w for w in warnings))
        
    def test_empty_csv(self):
        parsed, errors, warnings = ImportService.parse_bom_csv("")
        self.assertEqual(len(errors), 1)
        self.assertIn("Empty CSV", errors[0])
        
    def test_invalid_csv_structure(self):
        csv_content = "designator,value\nC101,10u,extra"
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_content)
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid CSV structure", errors[0])
        
    def test_mapping_service_suggestions(self):
        templates = [
            ComponentDB(id="db_cap", display_name="Capacitor", shortcut="C", fits=0.5),
            ComponentDB(id="db_res", display_name="Resistor", shortcut="R", fits=0.2)
        ]
        bom_cap = BOMComponent(id="bom_c", designator="C501", part_number="UNKNOWN")
        suggestions = MappingService.get_suggestions(bom_cap, templates)
        self.assertEqual(suggestions[0][0].id, "db_cap")


if __name__ == "__main__":
    unittest.main()
