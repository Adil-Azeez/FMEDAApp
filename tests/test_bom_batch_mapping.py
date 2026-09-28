import unittest
import os
import tempfile
from typing import List, Dict

from fmeda_tool.models import (
    Project, Unit, Component, BOMComponent, ComponentDB, ComponentMapping,
    FailureModeAssignment, SafetyStandard, ProjectStatus
)
from fmeda_tool.services import CalculationService, ProjectService, ImportService
from PyQt6.QtWidgets import QApplication
from fmeda_tool.ui.dialogs.component_mapping_dialog import (
    ComponentMappingDialog, parse_range_expression, format_position_ranges
)

app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestBOMBatchMapping(unittest.TestCase):
    """
    Test suite for batch BOM mapping architecture in FMEDA Tool.
    Verifies separation of component templates from instances, multi-position mapping,
    range parsing, remapping, idempotency, and calculation consistency.
    """
    
    def setUp(self):
        self.unit = Unit(
            id="unit_afe",
            name="Analog Front End",
            description="AFE Subsystem",
            components=[],
            bom_components=[],
            component_templates=[]
        )
        self.project = Project(
            id="proj_batch_test",
            name="Batch Mapping Test Project",
            description="Project for verifying batch BOM mapping",
            status=ProjectStatus.DRAFT,
            safety_standard=SafetyStandard.IEC_61508,
            target_sil="SIL 2",
            selected_profile="Profile 1",
            units=[self.unit]
        )
        
        # Standard templates
        self.ckp_template = ComponentDB(
            id="tmpl_ckp_01",
            display_name="CKP Ceramic Capacitor",
            shortcut="CKP",
            material="Capacitor Ceramic",
            fits=0.4,
            database="exida",
            failure_modes={"Short Circuit": 50.0, "Open Circuit": 30.0, "Change in Value": 20.0}
        )
        
        self.res_template = ComponentDB(
            id="tmpl_res_01",
            display_name="Resistor Metal Film",
            shortcut="RES_MF",
            material="Resistor Metal Film",
            fits=5.0,
            database="exida",
            failure_modes={"Open Circuit": 60.0, "Short Circuit": 40.0}
        )
        
        self.tantal_template = ComponentDB(
            id="tmpl_tantal_01",
            display_name="Tantalum Capacitor",
            shortcut="CAP_TANTAL",
            material="Capacitor Tantalum",
            fits=1.5,
            database="Legacy",
            failure_modes={"Short Circuit": 70.0, "Open Circuit": 30.0}
        )

    def test_range_parser_and_range_formatter(self):
        """Test parse_range_expression and format_position_ranges utilities."""
        available = [f"C{i}" for i in range(1, 30)] + [f"R{i}" for i in range(1, 20)] + ["V1", "V2", "IC1"]
        
        # Continuous range C3-C15
        matched = parse_range_expression("C3-C15", available)
        self.assertEqual(len(matched), 13)
        self.assertEqual(matched[0], "C3")
        self.assertEqual(matched[-1], "C15")
        
        # Range with comma and mixed designators
        matched_mixed = parse_range_expression("C3-C5, R1-R3, V2", available)
        self.assertEqual(matched_mixed, ["C3", "C4", "C5", "R1", "R2", "R3", "V2"])
        
        # Range formatter
        fmt = format_position_ranges(["C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13", "C14", "C15"])
        self.assertEqual(fmt, "C3-C15")

    def test_add_component_type_creates_no_calculated_duplicate(self):
        """Adding a component type template adds to component_templates and contributes 0 FIT to calculations."""
        self.unit.component_templates.append(self.ckp_template)
        
        # No physical components exist yet
        self.assertEqual(len(self.unit.components), 0)
        self.assertEqual(len(self.unit.component_templates), 1)
        
        # FMEDA calculations yield 0 FIT
        res = CalculationService.calculate_project(self.project)
        self.assertEqual(self.project.lambda_total_gesamtgerat, 0.0)
        self.assertEqual(self.project.lambda_total_sicherheitskanal, 0.0)

    def test_mapping_single_pos(self):
        """Test mapping a single BOM position."""
        bom = BOMComponent(
            id="bom_c1",
            designator="C1",
            part_number="00112233",
            benennung="KERAMIK KONDENSATOR",
            value="100n",
            description="CAP Ceramic 100nF 50V",
            layer="TOP",
            is_fitted=True
        )
        self.unit.bom_components = [bom]
        self.unit.component_templates = [self.ckp_template]
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1")
        dialog.staged_mappings["C1"] = self.ckp_template
        dialog._commit_mappings()
        
        self.assertEqual(len(self.unit.components), 1)
        c1 = self.unit.components[0]
        self.assertEqual(c1.position, "C1")
        self.assertEqual(c1.internal_pn, "00112233")
        self.assertEqual(c1.value, "100n / CAP Ceramic 100nF 50V")
        self.assertEqual(c1.failure_rate, 0.4)
        self.assertEqual(len(c1.failure_mode_assignments), 3)

    def test_batch_mapping_c3_through_c15(self):
        """Test batch mapping 13 capacitor positions (C3-C15) in one operation."""
        bom_items = []
        for i in range(3, 16):
            bom_items.append(BOMComponent(
                id=f"bom_c{i}",
                designator=f"C{i}",
                part_number="00998811",
                benennung="KERAMIK-KONDENSATOR",
                value="100n",
                description="CAP-VS 100nF/16V 0201",
                layer="TOP",
                is_fitted=True
            ))
        self.unit.bom_components = bom_items
        self.unit.component_templates = [self.ckp_template]
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1")
        
        # Stage all C3-C15 to CKP template
        for i in range(3, 16):
            dialog.staged_mappings[f"C{i}"] = self.ckp_template
            
        dialog._commit_mappings()
        
        # Verify exactly 13 component instances created
        self.assertEqual(len(self.unit.components), 13)
        
        # Verify no unmapped template remains
        self.assertFalse(any(c.position in ("Mapping Template", "Template") for c in self.unit.components))
        
        for idx, i in enumerate(range(3, 16)):
            comp = self.unit.components[idx]
            self.assertEqual(comp.position, f"C{i}")
            self.assertEqual(comp.internal_pn, "00998811")
            self.assertEqual(comp.value, "100n / CAP-VS 100nF/16V 0201")
            self.assertEqual(comp.layer, "TOP")
            self.assertEqual(comp.fitted_status, "Fitted")
            self.assertEqual(comp.failure_rate, 0.4)
            self.assertEqual(len(comp.failure_mode_assignments), 3)
            
        # Calculation verification: 13 * 0.4 FIT = 5.2 FIT
        CalculationService.calculate_project(self.project)
        self.assertAlmostEqual(self.project.lambda_total_gesamtgerat, 5.2, places=4)

    def test_mapping_several_component_types_in_one_session(self):
        """Test assigning C3-C6 to CKP and R1-R4 to Resistor in the same mapping session."""
        bom_c = [
            BOMComponent(id=f"bom_c{i}", designator=f"C{i}", part_number="0011", value="10n", description="CAP 10nF", layer="TOP", is_fitted=True)
            for i in range(3, 7)
        ]
        bom_r = [
            BOMComponent(id=f"bom_r{i}", designator=f"R{i}", part_number="0022", value="10k", description="RES 10k 1%", layer="BOT", is_fitted=True)
            for i in range(1, 5)
        ]
        self.unit.bom_components = bom_c + bom_r
        self.unit.component_templates = [self.ckp_template, self.res_template]
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1")
        for i in range(3, 7):
            dialog.staged_mappings[f"C{i}"] = self.ckp_template
        for i in range(1, 5):
            dialog.staged_mappings[f"R{i}"] = self.res_template
            
        dialog._commit_mappings()
        
        self.assertEqual(len(self.unit.components), 8)
        
        caps = [c for c in self.unit.components if c.position.startswith("C")]
        resistors = [c for c in self.unit.components if c.position.startswith("R")]
        
        self.assertEqual(len(caps), 4)
        self.assertEqual(len(resistors), 4)
        
        for c in caps:
            self.assertEqual(c.failure_rate, 0.4)
        for r in resistors:
            self.assertEqual(r.failure_rate, 5.0)

    def test_only_added_types_appear_as_mapping_targets(self):
        """Map BOM shows only component types added to the functional group, not all SQLite templates."""
        self.unit.component_templates = [self.ckp_template, self.res_template]
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1")
        
        # Only the 2 added templates should be present in available_templates
        self.assertEqual(len(dialog.available_templates), 2)
        target_ids = [t.id for t in dialog.available_templates]
        self.assertIn("tmpl_ckp_01", target_ids)
        self.assertIn("tmpl_res_01", target_ids)
        self.assertNotIn("tmpl_tantal_01", target_ids)

    def test_idempotency_save_twice_creates_no_duplicates(self):
        """Calling save / commit mappings twice does not duplicate component instances."""
        bom = BOMComponent(id="bom_c1", designator="C1", part_number="0011", value="100n", description="CAP 100nF", layer="TOP", is_fitted=True)
        self.unit.bom_components = [bom]
        self.unit.component_templates = [self.ckp_template]
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1")
        dialog.staged_mappings["C1"] = self.ckp_template
        dialog._commit_mappings()
        self.assertEqual(len(self.unit.components), 1)
        
        # Second commit
        dialog._commit_mappings()
        self.assertEqual(len(self.unit.components), 1)
        self.assertEqual(self.unit.components[0].position, "C1")

    def test_unmap_and_remap_position(self):
        """Remapping an existing position replaces the reliability model and preserves BOM fields."""
        bom = BOMComponent(id="bom_c1", designator="C1", part_number="0011", value="10u", description="TANTAL CAP 10uF", layer="TOP", is_fitted=True)
        self.unit.bom_components = [bom]
        self.unit.component_templates = [self.ckp_template, self.tantal_template]
        
        # 1. Map to CKP (0.4 FIT)
        dialog1 = ComponentMappingDialog(self.unit, project_profile="Profile 1")
        dialog1.staged_mappings["C1"] = self.ckp_template
        dialog1._commit_mappings()
        
        self.assertEqual(self.unit.components[0].failure_rate, 0.4)
        self.assertEqual(self.unit.components[0].value, "10u / TANTAL CAP 10uF")
        
        # 2. Remap to Tantalum (1.5 FIT)
        dialog2 = ComponentMappingDialog(self.unit, project_profile="Profile 1")
        dialog2.staged_mappings["C1"] = self.tantal_template
        dialog2._commit_mappings()
        
        self.assertEqual(len(self.unit.components), 1)
        c1 = self.unit.components[0]
        self.assertEqual(c1.position, "C1")
        self.assertEqual(c1.failure_rate, 1.5)
        self.assertEqual(c1.value, "10u / TANTAL CAP 10uF")
        self.assertEqual(c1.library_component_id, "tmpl_tantal_01")

    def test_not_fitted_handling_in_mapping(self):
        """Components with 'nicht bestueckt' in notes are mapped with fitted_status = 'Not Fitted'."""
        bom_fitted = BOMComponent(id="bom_r1", designator="R1", part_number="0011", value="10k", description="RES 10k", layer="TOP", is_fitted=True)
        bom_unfitted = BOMComponent(id="bom_r2", designator="R2", part_number="0012", value="20k", description="RES 20k", layer="BOT", is_fitted=False, notes="nicht bestueckt")
        
        self.unit.bom_components = [bom_fitted, bom_unfitted]
        self.unit.component_templates = [self.res_template]
        
        dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1")
        dialog.staged_mappings["R1"] = self.res_template
        dialog.staged_mappings["R2"] = self.res_template
        dialog._commit_mappings()
        
        self.assertEqual(len(self.unit.components), 2)
        r1 = next(c for c in self.unit.components if c.position == "R1")
        r2 = next(c for c in self.unit.components if c.position == "R2")
        
        self.assertEqual(r1.fitted_status, "Fitted")
        self.assertEqual(r2.fitted_status, "Not Fitted")

    def test_save_reopen_and_calculation_equality(self):
        """Test atomic project save, reload, and calculation equality with batch-mapped components."""
        temp_dir = tempfile.mkdtemp()
        try:
            proj_path = os.path.join(temp_dir, "batch_mapped_project.json")
            
            bom_items = [
                BOMComponent(id=f"bom_c{i}", designator=f"C{i}", part_number="009988", value="100n", description="CAP 100nF", layer="TOP", is_fitted=True)
                for i in range(101, 114)  # 13 items: C101 to C113
            ]
            self.unit.bom_components = bom_items
            self.unit.component_templates = [self.ckp_template]
            
            dialog = ComponentMappingDialog(self.unit, project_profile="Profile 1")
            for b in bom_items:
                dialog.staged_mappings[b.designator.upper()] = self.ckp_template
            dialog._commit_mappings()
            
            # Calculate before save
            res_before = CalculationService.calculate_project(self.project)
            
            # Atomic save
            ProjectService.save_project_atomically(self.project, proj_path)
            self.assertTrue(os.path.exists(proj_path))
            
            # Reload
            reopened, _, _ = ProjectService.load_and_migrate_project(proj_path)
            self.assertEqual(len(reopened.units), 1)
            self.assertEqual(len(reopened.units[0].components), 13)
            self.assertEqual(len(reopened.units[0].component_templates), 1)
            
            # Calculate after reload
            res_after = CalculationService.calculate_project(reopened)
            
            self.assertAlmostEqual(res_before["gesamtgerat"]["lambda"], res_after["gesamtgerat"]["lambda"], places=5)
            self.assertAlmostEqual(res_before["sicherheitskanal"]["lambda"], res_after["sicherheitskanal"]["lambda"], places=5)
            self.assertAlmostEqual(res_before["sicherheitskanal"]["sff"], res_after["sicherheitskanal"]["sff"], places=4)
            self.assertAlmostEqual(res_before["sicherheitskanal"]["dc"], res_after["sicherheitskanal"]["dc"], places=4)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
