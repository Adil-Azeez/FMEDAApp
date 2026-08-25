import unittest
from fmeda_tool.models import BOMComponent
from fmeda_tool.services import ImportService


class TestBOMImport(unittest.TestCase):
    
    def test_parse_valid_bom_csv(self):
        valid_csv = """designator,part_number,description,value,layer,fitted,notes
C101,CAP_0805_1UF,Capacitor 1uF 50V,1uF,Top,true,Decoupling cap
R101,RES_0603_10K,Resistor 10k 1%,10k,Bottom,false,Pull-up resistor
"""
        parsed, errors, warnings = ImportService.parse_bom_csv(valid_csv)
        
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
        
    def test_parse_invalid_csv_format(self):
        # Test missing designator column
        invalid_csv = """part_number,description
RES_10K,Resistor
"""
        parsed, errors, warnings = ImportService.parse_bom_csv(invalid_csv)
        self.assertTrue(len(errors) > 0)
        self.assertEqual(len(parsed), 0)
        
    def test_parse_missing_designator(self):
        missing_designator_csv = """part_number,value
RES_10K,10k
"""
        parsed, errors, warnings = ImportService.parse_bom_csv(missing_designator_csv)
        
        self.assertEqual(len(parsed), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("Missing designator column", errors[0])
        
    def test_parse_duplicate_designators_in_file(self):
        duplicate_csv = """designator,part_number
R101,RES_1
R101,RES_2
"""
        parsed, errors, warnings = ImportService.parse_bom_csv(duplicate_csv)
        
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(parsed), 2)
        self.assertIn("Duplicate designator 'R101' found inside the CSV", errors[0])
        
    def test_parse_conflict_with_existing_designators(self):
        csv_data = """designator,part_number
C101,CAP_1
"""
        parsed, errors, warnings = ImportService.parse_bom_csv(csv_data, existing_designators=["C101"])
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 1)
        self.assertTrue(any("Duplicate designator 'C101' against existing functional-group data" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
