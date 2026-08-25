import unittest
from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment, BOMComponent
from fmeda_tool.services import ValidationService


class TestValidationEngine(unittest.TestCase):
    
    def test_missing_deviation_dangerous_failure(self):
        comp = Component(
            id="comp_test_val",
            position="U1",
            name="Processor",
            type="IC",
            failure_rate=50.0,
            failure_modes={"Latchup": 100.0}
        )
        
        assignment = FailureModeAssignment(
            failure_mode_name="Latchup",
            failure_rate_percentage=100.0,
            classification="dangerous_failure",
            deviation_id=None  # missing!
        )
        
        status, msgs = ValidationService.validate_row(assignment, comp)
        self.assertEqual(status, "error")
        self.assertTrue(any("missing a deviation" in m for m in msgs))
        
    def test_blank_comments_warning(self):
        comp = Component(
            id="comp_test_val",
            position="U1",
            name="Processor",
            type="IC",
            failure_rate=50.0,
            failure_modes={"Latchup": 100.0}
        )
        
        assignment = FailureModeAssignment(
            failure_mode_name="Latchup",
            failure_rate_percentage=100.0,
            classification="dangerous_failure",
            deviation_id="dev_001",
            notes=""  # blank comment when deviation is assigned!
        )
        
        status, msgs = ValidationService.validate_row(assignment, comp)
        self.assertEqual(status, "warning")
        self.assertTrue(any("Comment/Justification is blank" in m for m in msgs))
        
    def test_failure_modes_distribution_warning(self):
        comp = Component(
            id="comp_test_val",
            position="U1",
            name="Processor",
            type="IC",
            failure_rate=50.0,
            failure_modes={"Latchup": 80.0}  # total 80% instead of 100%!
        )
        
        status, msgs = ValidationService.validate_component(comp)
        self.assertEqual(status, "warning")
        self.assertTrue(any("does not equal 100%" in m for m in msgs))
        
    def test_unmapped_bom_component_warning(self):
        project = Project(id="proj_val_01", name="Test Val", description="Desc")
        unit = Unit(
            id="unit_val_01",
            name="Controller Unit",
            description="Unit desc",
            bom_components=[
                BOMComponent(id="bom_c1", designator="C1", part_number="CAP-123", quantity=1),
                BOMComponent(id="bom_c2", designator="R2", part_number="RES-456", quantity=1)
            ],
            components=[
                Component(
                    id="comp_c1",
                    position="C1",
                    name="Capacitor",
                    type="Capacitor",
                    failure_rate=0.1,
                    failure_modes={"Short": 100.0}
                )
                # R2 is unmapped!
            ]
        )
        project.units.append(unit)
        
        alerts = ValidationService.validate_project(project)
        unmapped_alerts = [a for a in alerts if "has not been mapped" in a["message"]]
        self.assertEqual(len(unmapped_alerts), 1)
        self.assertEqual(unmapped_alerts[0]["item"], "R2")
        
    def test_sil_target_mismatch(self):
        project = Project(
            id="proj_val_01",
            name="Test Val",
            description="Desc",
            target_sil="SIL 3",
            achieved_sil="SIL 2"  # Achieved < Target
        )
        alerts = ValidationService.validate_project(project)
        sil_alerts = [a for a in alerts if "Target SIL is SIL 3" in a["message"]]
        self.assertEqual(len(sil_alerts), 1)
        self.assertEqual(sil_alerts[0]["severity"], "Error")


if __name__ == "__main__":
    unittest.main()
