import unittest
from fmeda_tool.models import BOMComponent
from fmeda_tool.services import ImportService


class TestBOMImport(unittest.TestCase):
    
    def test_parse_valid_bom_txt(self):
        valid_txt = """
Pos   MN               Benennung               Wert      Beschreibung               Bemerkung         Lage
----------------------------------------------------------------------------------------------------------
C101  CAP_0805_1UF     KONDENSATOR             1uF       Capacitor 1uF 50V          Decoupling cap    Top
R101  RES_0603_10K     WIDERSTAND              10k       Resistor 10k 1%            nicht bestueckt   Bottom
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(valid_txt)
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 2)
        
        c101 = parsed[0]
        self.assertEqual(c101.designator, "C101")
        self.assertEqual(c101.part_number, "CAP_0805_1UF")
        self.assertEqual(c101.value, "1uF")
        self.assertTrue(c101.is_fitted)
        self.assertEqual(c101.layer, "Top")
        
        r101 = parsed[1]
        self.assertEqual(r101.designator, "R101")
        self.assertEqual(r101.part_number, "RES_0603_10K")
        self.assertEqual(r101.value, "10k")
        self.assertFalse(r101.is_fitted)
        self.assertEqual(r101.layer, "Bottom")
        
    def test_parse_invalid_txt_format(self):
        # Missing Pos column header
        invalid_txt = """
MN          Beschreibung
RES_10K     Resistor
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(invalid_txt)
        self.assertTrue(len(errors) > 0)
        self.assertEqual(len(parsed), 0)
        
    def test_parse_missing_pos_value(self):
        # Header present, but row missing Pos value
        missing_pos_txt = """
Pos   MN          Wert      Beschreibung
      RES_10K     10k       Resistor 10k
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(missing_pos_txt)
        self.assertEqual(len(parsed), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("Missing required Pos value", errors[0])
        
    def test_parse_duplicate_designators_in_file(self):
        duplicate_txt = """
Pos   MN          Beschreibung
R101  RES_1       Resistor 1
R101  RES_2       Resistor 2
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(duplicate_txt)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(parsed), 1)
        self.assertIn("Duplicate Pos 'R101' found", errors[0])
        
    def test_parse_conflict_with_existing_designators(self):
        txt_data = """
Pos   MN          Beschreibung
C101  CAP_1       Capacitor 1
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_data, existing_designators=["C101"])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 1)
        self.assertTrue(any("Duplicate Pos 'C101' against existing functional-group data" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()

