import unittest
from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment, SafetyContext
from fmeda_tool.services import CalculationService


class TestFMEDACalculations(unittest.TestCase):
    
    def test_calculate_row_split(self):
        # 10 FIT, 60% dangerous, 80% detection
        # dangerous FIT: 6.0, safe FIT: 4.0
        # dangerous detected: 6.0 * 0.8 = 4.8 FIT
        # dangerous undetected: 6.0 * 0.2 = 1.2 FIT
        # safe detected: 4.0 * 0.8 = 3.2 FIT
        # safe undetected: 4.0 * 0.2 = 0.8 FIT
        
        metrics = CalculationService.calculate_row(10.0, 60.0, 80.0)
        
        self.assertAlmostEqual(metrics["lambda_dd"], 4.8)
        self.assertAlmostEqual(metrics["lambda_du"], 1.2)
        self.assertAlmostEqual(metrics["lambda_sd"], 3.2)
        self.assertAlmostEqual(metrics["lambda_su"], 0.8)
        
    def test_calculate_unit_with_no_components(self):
        # Division-by-zero guard test
        unit = Unit(id="unit_empty", name="Empty", description="Empty unit")
        metrics = CalculationService.calculate_unit(unit)
        
        self.assertEqual(metrics["total_failure_rate"], 0.0)
        self.assertEqual(metrics["sff"], 0.0)
        self.assertEqual(metrics["dc"], 0.0)
        
    def test_calculate_project_safety_metrics(self):
        # Mock project
        project = Project(
            id="proj_calc_01",
            name="Control System",
            description="Control System FMEDA",
            test_interval=8760.0,             # 1 year
            diagnostic_test_interval=8.0      # 8 hours
        )
        
        # Unit 1: 10 FIT total
        # Component C1: 10 FIT, 50% FM1 distribution
        unit = Unit(
            id="unit_1",
            name="Sensor Input",
            description="Analog sensor board",
            included_in_safety_function=True,
            components=[
                Component(
                    id="comp_1",
                    position="R1",
                    name="Resistor",
                    type="Resistor",
                    failure_rate=100.0,
                    failure_modes={"Short": 50.0, "Open": 50.0},
                    failure_mode_assignments=[
                        # row 1: 50 FIT, 60% dangerous, 80% detection -> dd: 24 FIT, du: 6 FIT, safe: 20 FIT
                        FailureModeAssignment(
                            failure_mode_name="Short",
                            failure_rate_percentage=50.0,
                            dangerous_failure_percentage=60.0,
                            detection_percentage=80.0,
                            classification="dangerous_failure"
                        ),
                        # row 2: 50 FIT, 40% dangerous, 90% detection -> dd: 18 FIT, du: 2 FIT, safe: 30 FIT
                        FailureModeAssignment(
                            failure_mode_name="Open",
                            failure_rate_percentage=50.0,
                            dangerous_failure_percentage=40.0,
                            detection_percentage=90.0,
                            classification="dangerous_failure"
                        )
                    ]
                )
            ]
        )
        project.units.append(unit)
        
        CalculationService.calculate_project(project)
        
        # Totals verification
        # Total FIT: 100
        # Total DD: 24 + 18 = 42 FIT
        # Total DU: 6 + 2 = 8 FIT
        # Total Dangerous: 50 FIT
        # Total Safe: 50 FIT
        # SFF = (Safe + DD) / Total = (50 + 42) / 100 = 92%
        # DC = DD / (DD + DU) = 42 / 50 = 84%
        self.assertAlmostEqual(project.total_failure_rate, 100.0)
        self.assertAlmostEqual(project.sff, 92.0)
        
        # PFDavg (1oo1 standard)
        # PFDavg = (lambda_du_hour * t_proof / 2) + (lambda_dd_hour * t_diag)
        # lambda_du_hour = 8 * 10^-9 = 8e-9 / hour
        # lambda_dd_hour = 42 * 10^-9 = 42e-9 / hour
        # t_proof = 8760
        # t_diag = 8
        # PFDavg = (8e-9 * 8760 / 2) + (42e-9 * 8) = 0.00003504 + 0.000000336 = 3.5376e-5
        self.assertAlmostEqual(project.pfd_avg, 3.5376e-5)
        self.assertEqual(project.achieved_sil, "SIL 2")  # 90% <= SFF < 99%


if __name__ == "__main__":
    unittest.main()
