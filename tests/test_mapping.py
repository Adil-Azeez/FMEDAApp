import unittest
from fmeda_tool.models import BOMComponent, ComponentDB, ComponentMapping
from fmeda_tool.services import MappingService


class TestComponentMapping(unittest.TestCase):
    
    def setUp(self):
        # Create a database template library
        self.templates = [
            ComponentDB(
                id="temp_res_10k",
                display_name="Resistor 10k 0.1W",
                shortcut="RES_10K",
                fits=0.2,
                failure_modes={"Short": 50.0, "Open": 50.0}
            ),
            ComponentDB(
                id="temp_cap_1uf",
                display_name="Capacitor 1uF 50V",
                shortcut="CAP_1UF",
                fits=0.4,
                failure_modes={"Short": 80.0, "Open": 20.0}
            ),
            ComponentDB(
                id="temp_ic_opamp",
                display_name="Operational Amplifier Low Noise",
                shortcut="OPAMP_LN",
                fits=1.5,
                failure_modes={"Output Stuck High": 30.0, "Output Stuck Low": 30.0, "Drift": 40.0}
            )
        ]
        
    def test_exact_part_number_match(self):
        # BOM component matching exactly on template shortcut (ignoring case)
        bom = BOMComponent(
            id="bom_01",
            designator="R101",
            part_number="res_10k",  # exact match with RES_10K
            description="Metal film resistor"
        )
        
        score = MappingService.calculate_confidence(bom, self.templates[0])
        self.assertEqual(score, 1.0)
        
    def test_value_and_category_match(self):
        # Value matches, and description keywords match category "cap" / "capacitor"
        bom = BOMComponent(
            id="bom_02",
            designator="C101",
            value="1uF",
            description="Ceramic capacitor 0805"
        )
        
        score = MappingService.calculate_confidence(bom, self.templates[1])
        self.assertEqual(score, 0.90)
        
    def test_value_only_match(self):
        # Value matches, but no description keywords match category
        bom = BOMComponent(
            id="bom_03",
            designator="C102",
            value="1uF",
            description="Miscellaneous component"
        )
        
        score = MappingService.calculate_confidence(bom, self.templates[1])
        self.assertEqual(score, 0.70)
        
    def test_description_substring_match(self):
        # Description has opamp display name substring
        bom = BOMComponent(
            id="bom_04",
            designator="U101",
            description="Operational Amplifier Low Noise SOIC-8"
        )
        
        score = MappingService.calculate_confidence(bom, self.templates[2])
        self.assertEqual(score, 0.50)
        
    def test_get_suggestions_sorting(self):
        bom = BOMComponent(
            id="bom_05",
            designator="C103",
            value="1uF",
            description="decoupling capacitor"
        )
        
        suggestions = MappingService.get_suggestions(bom, self.templates)
        
        # Best match should be Cap 1uF
        best_match, best_score = suggestions[0]
        self.assertEqual(best_match.id, "temp_cap_1uf")
        self.assertEqual(best_score, 0.90)
        
    def test_auto_map_confirms_high_confidence(self):
        bom_list = [
            BOMComponent(id="bom_1", designator="R1", part_number="RES_10K"), # 1.0
            BOMComponent(id="bom_2", designator="C1", value="1uF", description="capacitor") # 0.9
        ]
        
        mappings = MappingService.auto_map_bom(bom_list, self.templates)
        self.assertEqual(len(mappings), 2)
        self.assertTrue(mappings[0].is_confirmed)
        self.assertTrue(mappings[1].is_confirmed)


if __name__ == "__main__":
    unittest.main()
