import unittest
import os
import tempfile
import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from fmeda_tool.models import Project, ProjectStatus, SafetyStandard, Unit, Component, FailureModeAssignment, BOMComponent, ComponentDB, ComponentMapping
from fmeda_tool.services import ImportService, MappingService, ProjectService, CalculationService
from fmeda_tool.services.import_service import format_value_description
from fmeda_tool.ui.dialogs.bom_import_dialog import BOMImportDialog
from fmeda_tool.ui.dialogs.component_mapping_dialog import ComponentMappingDialog
from fmeda_tool.ui.main_window import MainWindow

app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestBOMImportAndMapping(unittest.TestCase):
    
    def test_fixed_width_txt_parsing_basic(self):
        txt_content = """
Vs  Pos   MN          Benennung              Wert      Beschreibung                   Bemerkung            Lage
------------------------------------------------------------------------------------------------------------------
01  C101  00123456    KERAMIK-KONDENSATOR    1u        CAP-VS 1uF/6.3V 0402           SMD                  TOP
01  R101  00234567    WIDERSTAND             10k       RES 10k 1% 0603                SMD                  TOP
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 2)
        
        c101 = parsed[0]
        self.assertEqual(c101.designator, "C101")
        self.assertEqual(c101.part_number, "00123456")
        self.assertEqual(c101.internal_part_number, "00123456")
        self.assertEqual(c101.benennung, "KERAMIK-KONDENSATOR")
        self.assertEqual(c101.value, "1u")
        self.assertEqual(c101.description, "CAP-VS 1uF/6.3V 0402")
        self.assertEqual(c101.notes, "SMD")
        self.assertEqual(c101.layer, "TOP")
        self.assertEqual(c101.vs, "01")
        self.assertTrue(c101.is_fitted)

    def test_multi_word_beschreibung_and_bemerkung(self):
        txt_content = """
Pos   MN          Benennung              Wert      Beschreibung                                  Bemerkung                    Lage
----------------------------------------------------------------------------------------------------------------------------------
C102  00998877    KERAMIK KONDENSATOR    100n      CAP Ceramic Multi Layer 100nF 50V +/-10%     Special Temp Range -40..125C TOP
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].designator, "C102")
        self.assertEqual(parsed[0].description, "CAP Ceramic Multi Layer 100nF 50V +/-10%")
        self.assertEqual(parsed[0].notes, "Special Temp Range -40..125C")

    def test_metadata_revision_and_list_end_skipping(self):
        txt_content = """================================================================================
Projekt:         JUMO dTRANS T06 Safety FMEDA
Zeichnungsnr:    70707100T06Z000K000
Datum:           08.09.2026
Revision:        Rev 02.1 (Aenderung: Sicherheitsrelevante Baugruppen)
Author:          Safety Engineer
================================================================================

Vs  Pos   MN          Benennung              Wert      Beschreibung                   Bemerkung            Lage
----------------------------------------------------------------------------------------------------------------
01  R201  00554433    METALLSCHICHTWIDERST.  47k       RES 47k 0.1% 0805              SMD                  BOT
01  R202  00554434    METALLSCHICHTWIDERST.  100k      RES 100k 0.1% 0805             SMD                  BOT
----------------------------------------------------------------------------------------------------------------
LIST END
Summary: Total 2 components exported.
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].designator, "R201")
        self.assertEqual(parsed[1].designator, "R202")

    def test_german_characters_and_units_preservation(self):
        txt_content = """
Pos   MN          Benennung                  Wert      Beschreibung                             Bemerkung                 Lage
------------------------------------------------------------------------------------------------------------------------------
R301  00112233    PRÄZISIONS-WIDERSTAND      100Ω      Widerstand 100 Ohm ±0,1% 25ppm/°C        Überlastgeschützt         LÖTSEITE
C301  00112234    ELEKTROLYT-KONDENSATOR     10µF      Elko 10µF / 50V Low-ESR                  Prüfspannung 100V         BESTÜCKUNG
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].benennung, "PRÄZISIONS-WIDERSTAND")
        self.assertEqual(parsed[0].value, "100Ω")
        self.assertEqual(parsed[0].description, "Widerstand 100 Ohm ±0,1% 25ppm/°C")
        self.assertEqual(parsed[0].notes, "Überlastgeschützt")
        self.assertEqual(parsed[0].layer, "LÖTSEITE")
        
        self.assertEqual(parsed[1].value, "10µF")
        self.assertEqual(parsed[1].description, "Elko 10µF / 50V Low-ESR")
        self.assertEqual(parsed[1].notes, "Prüfspannung 100V")

    def test_value_and_description_combination_rules(self):
        # Both present
        res1 = format_value_description("100n", "CAP-VS 100nF/16V 0201")
        self.assertEqual(res1, "100n / CAP-VS 100nF/16V 0201")
        
        # Only Wert present
        res2 = format_value_description("10k", None)
        self.assertEqual(res2, "10k")
        res2b = format_value_description("10k", "")
        self.assertEqual(res2b, "10k")
        
        # Only Beschreibung present
        res3 = format_value_description(None, "Microcontroller STM32")
        self.assertEqual(res3, "Microcontroller STM32")
        res3b = format_value_description("", "Microcontroller STM32")
        self.assertEqual(res3b, "Microcontroller STM32")
        
        # Both absent
        res4 = format_value_description(None, None)
        self.assertEqual(res4, "")
        res4b = format_value_description("", "")
        self.assertEqual(res4b, "")
        
        # Literal "None" / "null" strings
        res5 = format_value_description("None", "null")
        self.assertEqual(res5, "")
        res5b = format_value_description("100n", "None")
        self.assertEqual(res5b, "100n")
        
        # Deduplication when Beschreibung already starts with exact value
        res6 = format_value_description("10k", "10k 1% 0603 Thick Film")
        self.assertEqual(res6, "10k 1% 0603 Thick Film")

    def test_nicht_bestueckt_handling(self):
        txt_content = """
Pos   MN          Benennung              Wert      Beschreibung                   Bemerkung            Lage
-------------------------------------------------------------------------------------------------------------
R101  00123456    WIDERSTAND             10k       RES 10k 1% 0603                SMD                  TOP
R102  00123457    WIDERSTAND             10k       RES 10k 1% 0603                nicht bestueckt      BOT
R103  00123458    WIDERSTAND             10k       RES 10k 1% 0603                nicht bestückt       BOT
R104  00123459    WIDERSTAND             10k       RES 10k 1% 0603                DNP                  TOP
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 4)
        
        self.assertTrue(parsed[0].is_fitted)
        self.assertFalse(parsed[1].is_fitted)
        self.assertFalse(parsed[2].is_fitted)
        self.assertFalse(parsed[3].is_fitted)
        
        self.assertTrue(any("R102" in w and "Not Fitted" in w for w in warnings))
        self.assertTrue(any("R103" in w and "Not Fitted" in w for w in warnings))

    def test_duplicate_pos_in_txt(self):
        txt_content = """
Pos   MN          Benennung              Wert      Beschreibung                   Bemerkung            Lage
-------------------------------------------------------------------------------------------------------------
C101  00123456    KERAMIK-KONDENSATOR    1u        CAP-VS 1uF/6.3V 0402           SMD                  TOP
C101  00123499    KERAMIK-KONDENSATOR    100n      CAP-VS 100nF/50V 0603          SMD                  BOT
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_content)
        self.assertEqual(len(errors), 1)
        self.assertIn("Duplicate Pos 'C101' found", errors[0])
        self.assertIn("Previous instance at Line 4", errors[0])
        self.assertIn("00123456", errors[0])

    def test_duplicate_pos_against_existing_functional_group(self):
        txt_content = """
Pos   MN          Benennung              Wert      Beschreibung                   Bemerkung            Lage
-------------------------------------------------------------------------------------------------------------
C101  00123456    KERAMIK-KONDENSATOR    1u        CAP-VS 1uF/6.3V 0402           SMD                  TOP
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_content, existing_designators=["C101"])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed), 1)
        self.assertTrue(any("Duplicate Pos 'C101' against existing functional-group data" in w for w in warnings))

    def test_missing_pos_header_error(self):
        txt_content = """
Wert      Beschreibung                   Bemerkung
1u        CAP-VS 1uF/6.3V 0402           SMD
"""
        parsed, errors, warnings = ImportService.parse_bom_txt(txt_content)
        self.assertEqual(len(errors), 1)
        self.assertIn("Missing fixed-width header row with 'Pos' column", errors[0])

    def test_empty_txt_error(self):
        parsed, errors, warnings = ImportService.parse_bom_txt("")
        self.assertEqual(len(errors), 1)
        self.assertIn("Empty BOM text file", errors[0])

    def test_approved_mn_mapping_priority(self):
        templates = [
            ComponentDB(id="temp_cap_01", display_name="Ceramic Capacitor SMD", shortcut="CAP_CER", fits=0.5),
            ComponentDB(id="temp_cap_02", display_name="Tantalum Capacitor SMD", shortcut="CAP_TAN", fits=1.2)
        ]
        bom = BOMComponent(id="bom_01", designator="C3", part_number="00123456", internal_part_number="00123456")
        
        # Approved mapping maps 00123456 -> temp_cap_02
        approved_map = {"00123456": "temp_cap_02"}
        
        suggestions = MappingService.get_suggestions(bom, templates, approved_mn_mappings=approved_map)
        self.assertEqual(suggestions[0][0].id, "temp_cap_02")
        self.assertEqual(suggestions[0][1], 1.0)

    def test_multiple_failure_modes_single_component_instance(self):
        unit = Unit(id="unit_test_01", name="Test Unit", description="Unit Description", components=[], bom_components=[])
        bom = BOMComponent(
            id="bom_c3",
            designator="C3",
            part_number="00123456",
            value="100n",
            description="CAP-VS 100nF/16V 0201",
            layer="TOP",
            is_fitted=True
        )
        unit.bom_components = [bom]
        
        dialog = ComponentMappingDialog(unit, project_profile="Profile 1")
        # Template with 3 failure modes
        test_template = ComponentDB(
            id="test_cap",
            display_name="Capacitor Ceramic",
            fits=2.0,
            database="exida",
            failure_modes={"Short Circuit": 50.0, "Open Circuit": 30.0, "Change in Value": 20.0}
        )
        dialog.db_templates = [test_template]
        dialog.mappings = [
            ComponentMapping(bom_component_id="bom_c3", component_db_id="test_cap", confidence=1.0, is_confirmed=True)
        ]
        dialog._generate_fmeda_rows()
        
        # Verify single Component instance created
        self.assertEqual(len(unit.components), 1)
        comp = unit.components[0]
        self.assertEqual(comp.position, "C3")
        self.assertEqual(comp.value, "100n / CAP-VS 100nF/16V 0201")
        self.assertEqual(comp.internal_pn, "00123456")
        self.assertEqual(comp.layer, "TOP")
        self.assertEqual(comp.fitted_status, "Fitted")
        
        # Verify 3 failure mode assignments grouped under the same component
        self.assertEqual(len(comp.failure_mode_assignments), 3)
        mode_names = [a.failure_mode_name for a in comp.failure_mode_assignments]
        self.assertIn("Short Circuit", mode_names)
        self.assertIn("Open Circuit", mode_names)
        self.assertIn("Change in Value", mode_names)

    def test_save_reopen_and_calculation_equality(self):
        temp_dir = tempfile.mkdtemp()
        try:
            proj_path = os.path.join(temp_dir, "test_txt_bom_project.json")
            unit = Unit(id="unit_sensor_01", name="Sensor Channel", description="Sensor Group", components=[], bom_components=[])
            bom1 = BOMComponent(
                id="bom_r1",
                designator="R1",
                part_number="00998811",
                value="10k",
                description="RES 10k 1% 0603",
                layer="TOP",
                is_fitted=True
            )
            bom2 = BOMComponent(
                id="bom_r2",
                designator="R2",
                part_number="00998812",
                value="20k",
                description="RES 20k 1% 0603",
                layer="BOT",
                is_fitted=False,
                notes="nicht bestueckt"
            )
            unit.bom_components = [bom1, bom2]
            
            project = Project(
                id="proj_test_bom",
                name="BOM TXT Test Project",
                description="BOM TXT Test Project Description",
                status=ProjectStatus.DRAFT,
                safety_standard=SafetyStandard.IEC_61508,
                target_sil="SIL 2",
                selected_profile="Profile 1",
                units=[unit]
            )
            
            # Create FMEDA component for R1
            comp_r1 = Component(
                id="comp_r1",
                position="R1",
                name="Resistor Metal Film",
                type="Resistor Metal Film",
                failure_rate=5.0,
                value=format_value_description(bom1.value, bom1.description),
                internal_pn=bom1.part_number,
                layer=bom1.layer,
                fitted_status="Fitted",
                failure_modes={"Open": 60.0, "Short": 40.0},
                failure_mode_assignments=[
                    FailureModeAssignment(failure_mode_name="Open", failure_rate_percentage=60.0, classification="dangerous_failure", dangerous_failure_percentage=100.0, detection_percentage=90.0),
                    FailureModeAssignment(failure_mode_name="Short", failure_rate_percentage=40.0, classification="safe_failure", dangerous_failure_percentage=0.0, detection_percentage=0.0)
                ]
            )
            unit.components = [comp_r1]
            
            # Calculate before save
            res_before = CalculationService.calculate_project(project)
            
            # Save project
            ProjectService.save_project_atomically(project, proj_path)
            self.assertTrue(os.path.exists(proj_path))
            
            # Reopen project
            reopened, _, _ = ProjectService.load_and_migrate_project(proj_path)
            self.assertEqual(len(reopened.units), 1)
            self.assertEqual(len(reopened.units[0].bom_components), 2)
            self.assertEqual(reopened.units[0].bom_components[0].designator, "R1")
            self.assertEqual(reopened.units[0].bom_components[0].value, "10k")
            self.assertEqual(reopened.units[0].bom_components[1].designator, "R2")
            self.assertFalse(reopened.units[0].bom_components[1].is_fitted)
            
            # Calculate after load
            res_after = CalculationService.calculate_project(reopened)
            
            self.assertEqual(res_before["gesamtgerat"]["lambda"], res_after["gesamtgerat"]["lambda"])
            self.assertEqual(res_before["sicherheitskanal"]["sff"], res_after["sicherheitskanal"]["sff"])
            self.assertEqual(res_before["sicherheitskanal"]["dc"], res_after["sicherheitskanal"]["dc"])
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
