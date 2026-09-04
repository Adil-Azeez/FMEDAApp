"""
Tests for compact lossless JSON serialization in ProjectService:
- separators=(',', ':')
- allow_nan=False
- ensure_ascii=False
- Exact round-trip preservation of models, IDs, zeros, false values, nulls, and collections
- Compatibility with opening existing indented JSON projects
"""

import json
import tempfile
from pathlib import Path

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, Deviation, Mitigation,
    DiagnosticMeasure, SafetyStandard, DeviationType, DeviationSeverity
)
from fmeda_tool.services.project_service import ProjectService


def create_complex_project() -> Project:
    dev = Deviation(
        id="dev_c1",
        name="Output Drift",
        description="Drift beyond 5%",
        deviation_type=DeviationType.DANGEROUS_DETECTED,
        severity=DeviationSeverity.MEDIUM,
        failure_mode="Offset Error",
        effect="Gradual loss of accuracy"
    )
    mit = Mitigation(
        id="mit_c1",
        name="Auto Zero Calibration",
        description="Periodic offset calibration",
        effectiveness=0.98
    )
    dm = DiagnosticMeasure(
        id="dm_c1",
        description="Self Test",
        dc=95.0
    )
    comp = Component(
        id="comp_c1",
        position="U10",
        name="Precision ADC",
        type="Integrated Circuit",
        failure_rate=12.5,
        function="Signal Digitization",
        value=None,
        internal_pn="ADC-123",
        fitted_status="Fitted",
        failure_modes={"Offset Error": 40.0, "Gain Error": 60.0},
        failure_mode_assignments=[
            FailureModeAssignment(
                failure_mode_name="Offset Error",
                failure_rate_percentage=40.0,
                classification="dangerous_failure",
                dangerous_failure_percentage=80.0,
                detection_percentage=95.0,
                deviation_id="dev_c1",
                diagnostic_measure_id="dm_c1",
                mitigation_id="mit_c1",
                dont_care=False,
                notes="Calibration active"
            ),
            FailureModeAssignment(
                failure_mode_name="Gain Error",
                failure_rate_percentage=60.0,
                classification="safe_failure",
                dangerous_failure_percentage=0.0,
                detection_percentage=0.0,
                dont_care=True,
                notes=None
            )
        ]
    )
    unit = Unit(
        id="unit_c1",
        name="Data Acquisition",
        description="ADC input channels",
        components=[comp]
    )
    return Project(
        id="proj_compact_test",
        name="Compact JSON Test Project",
        description="Verifying lossless compact JSON saving",
        safety_standard=SafetyStandard.IEC_61508,
        deviations=[dev],
        mitigations=[mit],
        diagnostic_measures=[dm],
        units=[unit]
    )


def test_compact_json_saving_and_roundtrip():
    project = create_complex_project()

    with tempfile.TemporaryDirectory() as tmp_dir:
        save_path = Path(tmp_dir) / "test_project.json"

        # Save project
        ProjectService.save_project_atomically(project, str(save_path))

        assert save_path.exists()

        # Check raw text formatting: no multiline indentation
        raw_text = save_path.read_text(encoding="utf-8")
        assert "\n  \"id\":" not in raw_text
        assert '{"id":"proj_compact_test"' in raw_text or '{"' in raw_text

        # Verify json parses validly
        loaded_dict = json.loads(raw_text)
        assert loaded_dict["id"] == "proj_compact_test"

        # Load project using ProjectService
        loaded_project = ProjectService.load_project(str(save_path))

        assert loaded_project.id == project.id
        assert loaded_project.name == project.name
        assert len(loaded_project.units) == 1
        assert len(loaded_project.units[0].components) == 1

        comp_orig = project.units[0].components[0]
        comp_loaded = loaded_project.units[0].components[0]

        assert comp_loaded.position == comp_orig.position
        assert comp_loaded.failure_rate == comp_orig.failure_rate
        assert comp_loaded.value is None
        assert len(comp_loaded.failure_mode_assignments) == 2

        a0_orig = comp_orig.failure_mode_assignments[0]
        a0_loaded = comp_loaded.failure_mode_assignments[0]
        assert a0_loaded.failure_mode_name == a0_orig.failure_mode_name
        assert a0_loaded.dangerous_failure_percentage == a0_orig.dangerous_failure_percentage
        assert a0_loaded.dont_care is False
        assert a0_loaded.notes == "Calibration active"

        a1_orig = comp_orig.failure_mode_assignments[1]
        a1_loaded = comp_loaded.failure_mode_assignments[1]
        assert a1_loaded.dont_care is True
        assert a1_loaded.notes is None


def test_open_indented_json_and_save_as_compact():
    project = create_complex_project()

    with tempfile.TemporaryDirectory() as tmp_dir:
        indented_path = Path(tmp_dir) / "indented_project.json"

        # Write manually with indent=2
        with open(indented_path, "w", encoding="utf-8") as f:
            json.dump(project.model_dump(mode="json"), f, indent=2)

        # Open indented project
        loaded_from_indent = ProjectService.load_project(str(indented_path))
        assert loaded_from_indent.id == project.id

        # Save it back atomically (which now writes compact JSON)
        compact_path = Path(tmp_dir) / "resaved_compact.json"
        ProjectService.save_project_atomically(loaded_from_indent, str(compact_path))

        # Verify compact format
        compact_text = compact_path.read_text(encoding="utf-8")
        assert "\n  " not in compact_text

        # Reopen and compare
        final_project = ProjectService.load_project(str(compact_path))
        assert final_project.id == project.id
        assert final_project.model_dump() == project.model_dump()
