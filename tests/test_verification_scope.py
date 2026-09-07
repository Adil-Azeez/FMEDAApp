"""
Unit and integration tests for Page 3 Project Verification functional-group scope calculations,
five summary cards synchronization, Detailed Scope Comparison table, non-percentage averaging,
dont_care exclusions, zero-denominator handling, and selection workflow guards.
"""

import json
import pytest
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt

from fmeda_tool.models import (
    Project, Unit, Component, FailureModeAssignment, SafetyStandard, SafetyContext
)
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.ui.verification_view import VerificationView


@pytest.fixture(scope="session")
def qapp():
    """Ensure QApplication instance exists for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def load_real_reference_projects():
    """Loads real multi-group and single-group reference project files."""
    proj_dir = Path("data/projects")
    
    file_both = proj_dir / "proj_87bb2a1d_Zertifizierung_des_JUMO_dTRANS_T06_SFTY_ADC_CPU_and_SFTY_AO_complete.json"
    file_adc_cpu = proj_dir / "proj_87bb2a1d_SFTY_ADC_CPU_corrected_classification.json"
    file_ao = proj_dir / "proj_87bb2a1d_SFTY_AO_complete.json"
    
    with open(file_both, "r", encoding="utf-8") as f:
        proj_both = Project.model_validate(json.load(f))
        
    with open(file_adc_cpu, "r", encoding="utf-8") as f:
        proj_adc_cpu = Project.model_validate(json.load(f))
        
    with open(file_ao, "r", encoding="utf-8") as f:
        proj_ao = Project.model_validate(json.load(f))
        
    CalculationService.calculate_project(proj_both)
    CalculationService.calculate_project(proj_adc_cpu)
    CalculationService.calculate_project(proj_ao)
        
    return proj_both, proj_adc_cpu, proj_ao


def create_two_group_synthetic_project():
    """Creates a synthetic 2-group project with known failure rates and SIL thresholds."""
    u1 = Unit(
        id="unit_u1",
        name="SFTY-ADC-CPU",
        description="Analog to Digital Converter and CPU Processing Unit",
        included_in_safety_function=True,
        components=[
            Component(
                id="c1",
                name="MCU",
                position="U1",
                type="Microcontroller",
                failure_rate=100.0,
                failure_modes={"Short": 50.0, "Open": 50.0},
                failure_mode_assignments=[
                    FailureModeAssignment(
                        failure_mode_name="Short",
                        failure_rate_percentage=50.0,
                        classification="dangerous_failure",
                        dangerous_failure_percentage=100.0,
                        detection_percentage=90.0
                    ),
                    FailureModeAssignment(
                        failure_mode_name="Open",
                        failure_rate_percentage=50.0,
                        classification="safe_failure",
                        dangerous_failure_percentage=0.0,
                        detection_percentage=0.0
                    )
                ]
            )
        ]
    )
    
    u2 = Unit(
        id="unit_u2",
        name="SFTY-AO",
        description="Analog Output Driver Stage",
        included_in_safety_function=True,
        components=[
            Component(
                id="c2",
                name="OpAmp",
                position="U2",
                type="Integrated Circuit",
                failure_rate=200.0,
                failure_modes={"Drift": 50.0, "Short": 50.0},
                failure_mode_assignments=[
                    FailureModeAssignment(
                        failure_mode_name="Drift",
                        failure_rate_percentage=50.0,
                        classification="dangerous_failure",
                        dangerous_failure_percentage=100.0,
                        detection_percentage=50.0
                    ),
                    FailureModeAssignment(
                        failure_mode_name="Short",
                        failure_rate_percentage=50.0,
                        classification="dangerous_failure",
                        dangerous_failure_percentage=100.0,
                        detection_percentage=50.0
                    )
                ]
            )
        ]
    )
    
    project = Project(
        id="proj_synth_2g",
        name="Synthetic 2-Group Project",
        description="Synthetic project with two functional groups",
        target_sil="SIL 2",
        safety_standard=SafetyStandard.IEC_61508,
        units=[u1, u2]
    )
    return project


def test_calculate_scope_single_group():
    """Test CalculationService.calculate_scope on a single functional group."""
    proj = create_two_group_synthetic_project()
    res_u1 = CalculationService.calculate_scope([proj.units[0]], proj)
    
    assert res_u1["gesamtgerat"]["lambda"] == pytest.approx(100.0)
    assert res_u1["sicherheitskanal"]["lambda"] == pytest.approx(100.0)
    assert res_u1["sicherheitskanal"]["sff"] == pytest.approx(95.0)
    assert res_u1["sicherheitskanal"]["dc"] == pytest.approx(90.0)
    assert res_u1["achieved_sil"] == "SIL 2"
    assert res_u1["target_sil"] == "SIL 2"


def test_calculate_scope_combined_not_averaged():
    """Test that combined metrics sum failure rates before deriving SFF/DC/MTTFd."""
    proj = create_two_group_synthetic_project()
    res_both = CalculationService.calculate_scope(proj.units, proj)
    
    assert res_both["gesamtgerat"]["lambda"] == pytest.approx(300.0)
    assert res_both["sicherheitskanal"]["lambda"] == pytest.approx(300.0)
    assert res_both["sicherheitskanal"]["sff"] == pytest.approx(65.0)
    assert res_both["sicherheitskanal"]["sff"] != pytest.approx(72.5)
    assert res_both["achieved_sil"] == "SIL 1"


def test_calculate_scope_dont_care_exclusion():
    """Test that dont_care failure modes are excluded from Sicherheitskanal in calculate_scope."""
    proj = create_two_group_synthetic_project()
    proj.units[0].components[0].failure_mode_assignments[0].dont_care = True
    
    res = CalculationService.calculate_scope([proj.units[0]], proj)
    
    assert res["gesamtgerat"]["lambda"] == pytest.approx(100.0)
    assert res["sicherheitskanal"]["lambda"] == pytest.approx(50.0)
    assert res["sicherheitskanal"]["lambda_safe"] == pytest.approx(50.0)
    assert res["sicherheitskanal"]["lambda_dangerous"] == pytest.approx(0.0)


def test_calculate_scope_non_safety_unit_exclusion():
    """Test that units with included_in_safety_function=False are excluded from Sicherheitskanal."""
    proj = create_two_group_synthetic_project()
    proj.units[1].included_in_safety_function = False
    
    res = CalculationService.calculate_scope(proj.units, proj)
    
    assert res["gesamtgerat"]["lambda"] == pytest.approx(300.0)
    assert res["sicherheitskanal"]["lambda"] == pytest.approx(100.0)
    assert res["sicherheitskanal"]["sff"] == pytest.approx(95.0)
    assert res["achieved_sil"] == "SIL 2"


def test_calculate_scope_zero_denominator_and_empty():
    """Test zero-denominator handling returns None/NA without throwing exceptions."""
    empty_unit = Unit(id="u_empty", name="Empty Unit", description="Empty Unit Description", components=[])
    res = CalculationService.calculate_scope([empty_unit])
    
    assert res["gesamtgerat"]["lambda"] == 0.0
    assert res["sicherheitskanal"]["sff"] is None
    assert res["sicherheitskanal"]["dc"] is None
    assert res["sicherheitskanal"]["mttfd"] is None
    assert res["achieved_sil"] == "SIL 0"


def test_page3_initial_scope_all_selected(qapp):
    """Test that Page 3 initially selects all functional groups and updates top cards."""
    proj_both, proj_adc, proj_ao = load_real_reference_projects()
    
    view = VerificationView()
    view.load_project(proj_both)
    
    assert len(view.selected_unit_ids) == 2
    assert "SFTY-ADC-CPU" in view.scope_indicator_label.text()
    assert "SFTY-AO" in view.scope_indicator_label.text()
    
    assert view.card_val_sil.text() == "SIL 2"
    assert view.card_val_target.text() == (proj_both.target_sil or "N/A")
    assert view.card_val_sff.text() == f"{proj_both.sff_sicherheitskanal:.2f}%"
    assert view.card_val_dc.text() == f"{proj_both.dc_sicherheitskanal:.2f}%"
    assert view.card_val_mttfd.text() == f"{proj_both.mttfd_sicherheitskanal:.1f} years"


def test_page3_only_adc_cpu_selected(qapp):
    """Test unchecking SFTY-AO updates top cards and secondary table to SFTY-ADC-CPU alone."""
    proj_both, proj_adc, proj_ao = load_real_reference_projects()
    
    view = VerificationView()
    view.load_project(proj_both)
    
    uid_adc = proj_both.units[0].id
    uid_ao = proj_both.units[1].id
    
    cb_ao = view.unit_checkboxes[uid_ao]
    cb_ao.setChecked(False)
    
    assert view.selected_unit_ids == {uid_adc}
    assert view.scope_indicator_label.text() == "Scope: SFTY-ADC-CPU"
    
    assert view.card_val_sil.text() == "SIL 2"
    assert view.card_val_sff.text() == f"{proj_adc.sff_sicherheitskanal:.2f}%"
    assert view.card_val_dc.text() == f"{proj_adc.dc_sicherheitskanal:.2f}%"
    assert view.card_val_mttfd.text() == f"{proj_adc.mttfd_sicherheitskanal:.1f} years"
    
    item_gg_fit = view.secondary_table.item(0, 1).text()
    item_sk_fit = view.secondary_table.item(0, 2).text()
    assert f"{proj_adc.lambda_total_gesamtgerat:.4f} FIT" in item_gg_fit
    assert f"{proj_adc.lambda_total_sicherheitskanal:.4f} FIT" in item_sk_fit


def test_page3_only_ao_selected(qapp):
    """Test switching selection to SFTY-AO alone updates top cards and secondary table."""
    proj_both, proj_adc, proj_ao = load_real_reference_projects()
    
    view = VerificationView()
    view.load_project(proj_both)
    
    uid_adc = proj_both.units[0].id
    uid_ao = proj_both.units[1].id
    
    view.unit_checkboxes[uid_ao].setChecked(True)
    view.unit_checkboxes[uid_adc].setChecked(False)
    
    assert view.selected_unit_ids == {uid_ao}
    assert view.scope_indicator_label.text() == "Scope: SFTY-AO"
    
    assert view.card_val_sil.text() == "SIL 2"
    assert view.card_val_sff.text() == f"{proj_ao.sff_sicherheitskanal:.2f}%"
    assert view.card_val_dc.text() == f"{proj_ao.dc_sicherheitskanal:.2f}%"
    assert view.card_val_mttfd.text() == f"{proj_ao.mttfd_sicherheitskanal:.1f} years"
    
    item_gg_fit = view.secondary_table.item(0, 1).text()
    item_sk_fit = view.secondary_table.item(0, 2).text()
    assert f"{proj_ao.lambda_total_gesamtgerat:.4f} FIT" in item_gg_fit
    assert f"{proj_ao.lambda_total_sicherheitskanal:.4f} FIT" in item_sk_fit


def test_page3_select_all_button(qapp):
    """Test Select All button checks all boxes and updates cards & table to full scope."""
    proj_both, proj_adc, proj_ao = load_real_reference_projects()
    
    view = VerificationView()
    view.load_project(proj_both)
    
    uid_adc = proj_both.units[0].id
    uid_ao = proj_both.units[1].id
    view.unit_checkboxes[uid_ao].setChecked(False)
    assert len(view.selected_unit_ids) == 1
    
    view.select_all_btn.click()
    
    assert len(view.selected_unit_ids) == 2
    assert view.unit_checkboxes[uid_adc].isChecked()
    assert view.unit_checkboxes[uid_ao].isChecked()
    assert view.card_val_sff.text() == f"{proj_both.sff_sicherheitskanal:.2f}%"
    assert view.card_val_mttfd.text() == f"{proj_both.mttfd_sicherheitskanal:.1f} years"


def test_page3_clear_all_button_and_minimum_selection_guard(qapp, monkeypatch):
    """Test Clear All keeps 1 unit selected, and attempting to uncheck the last unit warns user."""
    proj_both, proj_adc, proj_ao = load_real_reference_projects()
    
    view = VerificationView()
    view.load_project(proj_both)
    
    uid_adc = proj_both.units[0].id
    uid_ao = proj_both.units[1].id
    
    view.clear_all_btn.click()
    assert view.selected_unit_ids == {uid_adc}
    assert view.unit_checkboxes[uid_adc].isChecked()
    assert not view.unit_checkboxes[uid_ao].isChecked()
    assert view.card_val_sff.text() == f"{proj_adc.sff_sicherheitskanal:.2f}%"
    
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warned.append(text))
    
    view.unit_checkboxes[uid_adc].setChecked(False)
    
    assert len(warned) == 1
    assert "At least one functional group must remain selected" in warned[0]
    assert view.selected_unit_ids == {uid_adc}
    assert view.unit_checkboxes[uid_adc].isChecked()


def test_page3_switching_repeatedly_between_selections(qapp):
    """Test switching repeatedly between selections maintains mathematical consistency without drift."""
    proj_both, proj_adc, proj_ao = load_real_reference_projects()
    
    view = VerificationView()
    view.load_project(proj_both)
    
    uid_adc = proj_both.units[0].id
    uid_ao = proj_both.units[1].id
    
    for _ in range(5):
        view.unit_checkboxes[uid_ao].setChecked(False)
        assert view.card_val_sff.text() == f"{proj_adc.sff_sicherheitskanal:.2f}%"
        assert view.card_val_mttfd.text() == f"{proj_adc.mttfd_sicherheitskanal:.1f} years"
        
        view.unit_checkboxes[uid_ao].setChecked(True)
        view.unit_checkboxes[uid_adc].setChecked(False)
        assert view.card_val_sff.text() == f"{proj_ao.sff_sicherheitskanal:.2f}%"
        assert view.card_val_mttfd.text() == f"{proj_ao.mttfd_sicherheitskanal:.1f} years"
        
        view.unit_checkboxes[uid_adc].setChecked(True)
        assert view.card_val_sff.text() == f"{proj_both.sff_sicherheitskanal:.2f}%"
        assert view.card_val_mttfd.text() == f"{proj_both.mttfd_sicherheitskanal:.1f} years"


def test_page3_dynamic_achieved_sil_change(qapp):
    """Test that Achieved SIL card dynamically updates based on the selected scope's SFF."""
    proj = create_two_group_synthetic_project()
    
    view = VerificationView()
    view.load_project(proj)
    
    uid_u1 = proj.units[0].id
    uid_u2 = proj.units[1].id
    
    assert view.card_val_sil.text() == "SIL 1"
    
    view.unit_checkboxes[uid_u2].setChecked(False)
    assert view.card_val_sil.text() == "SIL 2"
    
    view.unit_checkboxes[uid_u2].setChecked(True)
    view.unit_checkboxes[uid_u1].setChecked(False)
    assert view.card_val_sil.text() == "SIL 0"
