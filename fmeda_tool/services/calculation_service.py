from typing import Dict, Any, List, Optional
from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment


class CalculationService:
    """Service to handle FMEDA and reliability calculations for rows, components, units, and projects"""
    
    @staticmethod
    def calculate_row_detailed(local_fit: float, classification: str, dangerous_pct: float, detection_pct: float) -> Dict[str, float]:
        """
        Calculates detailed failure rates (FIT) for a single failure mode row.
        
        All rates (lambda_safe, lambda_dangerous, lambda_sd, lambda_su, lambda_dd, lambda_du)
        are derived strictly from %dang (dangerous_pct) and %safe (100 - dangerous_pct).
        """
        dp = dangerous_pct if dangerous_pct is not None else 100.0
        sp = 100.0 - dp
        det = detection_pct if detection_pct is not None else 0.0
        
        d_frac = dp / 100.0
        s_frac = sp / 100.0
        det_frac = det / 100.0
        
        ld = local_fit * d_frac
        ls = local_fit * s_frac
        
        ldd = ld * det_frac
        ldu = ld * (1.0 - det_frac)
        lsd = ls * det_frac
        lsu = ls * (1.0 - det_frac)
        
        row_dc = det
        row_sff = ((ls + ldd) / local_fit * 100.0) if local_fit > 0.0 else 0.0
        
        # MTBF & MTTFd (hours) per row
        row_mtbf = 1.0 / (local_fit * 10**-9) if local_fit > 0.0 else 0.0
        row_mttfd = 1.0 / (ldu * 10**-9) if ldu > 0.0 else 0.0
        row_mttfd_years = row_mttfd / 8760.0 if row_mttfd > 0.0 else 0.0
        
        return {
            "lambda": local_fit,
            "lambda_safe": ls,
            "lambda_dangerous": ld,
            "lambda_sd": lsd,
            "lambda_su": lsu,
            "lambda_dd": ldd,
            "lambda_du": ldu,
            "lambda_no_part": 0.0,
            "lambda_no_effect": 0.0,
            "dc": row_dc,
            "sff": row_sff,
            "mtbf": row_mtbf,
            "mttfd": row_mttfd_years
        }

    @staticmethod
    def calculate_row(failure_rate_fit: float, dangerous_pct: float, detection_pct: float) -> Dict[str, float]:
        """Legacy compatibility wrapper"""
        return CalculationService.calculate_row_detailed(failure_rate_fit, "dangerous_failure", dangerous_pct, detection_pct)

    @staticmethod
    def calculate_component(component: Component) -> Dict[str, Any]:
        """
        Calculates failure rates for a single component, returning both
        Gesamtgeraet and Sicherheitskanal scopes.
        """
        comp_fit = component.failure_rate or 0.0
        
        # Gesamtgeraet sums
        gg_fit = 0.0
        gg_safe = 0.0
        gg_dangerous = 0.0
        gg_sd = 0.0
        gg_su = 0.0
        gg_dd = 0.0
        gg_du = 0.0
        
        # Sicherheitskanal sums
        sk_fit = 0.0
        sk_safe = 0.0
        sk_dangerous = 0.0
        sk_sd = 0.0
        sk_su = 0.0
        sk_dd = 0.0
        sk_du = 0.0
        
        for assignment in component.failure_mode_assignments:
            fm_name = assignment.failure_mode_name
            fm_pct = component.failure_modes.get(fm_name, 0.0)
            local_fit = comp_fit * (fm_pct / 100.0)
            
            dp = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage is not None else 100.0
            det = assignment.detection_percentage if assignment.detection_percentage is not None else 0.0
            dc_flag = getattr(assignment, "dont_care", False) or False
            
            # Row calculations
            row_metrics = CalculationService.calculate_row_detailed(
                local_fit, getattr(assignment, "classification", "not_evaluated"), dp, det
            )
            
            # Gesamtgeraet
            gg_fit += row_metrics["lambda"]
            gg_safe += row_metrics["lambda_safe"]
            gg_dangerous += row_metrics["lambda_dangerous"]
            gg_sd += row_metrics["lambda_sd"]
            gg_su += row_metrics["lambda_su"]
            gg_dd += row_metrics["lambda_dd"]
            gg_du += row_metrics["lambda_du"]
            
            # Sicherheitskanal (only if dont_care is False)
            if not dc_flag:
                sk_fit += row_metrics["lambda"]
                sk_safe += row_metrics["lambda_safe"]
                sk_dangerous += row_metrics["lambda_dangerous"]
                sk_sd += row_metrics["lambda_sd"]
                sk_su += row_metrics["lambda_su"]
                sk_dd += row_metrics["lambda_dd"]
                sk_du += row_metrics["lambda_du"]
                
        # Legacy dictionary elements for backward compatibility
        legacy_dict = {
            "total_failure_rate": comp_fit,
            "relevant_failure_rate": gg_sd + gg_su + gg_dd + gg_du,
            "safe_failure_rate": gg_safe,
            "dangerous_detected_rate": gg_dd,
            "dangerous_undetected_rate": gg_du,
            "lambda_sd": gg_sd,
            "lambda_su": gg_su,
            "lambda_no_part": 0.0,
            "lambda_no_effect": 0.0
        }
        
        return {
            **legacy_dict,
            "gesamtgerat": {
                "lambda": gg_fit,
                "lambda_safe": gg_safe,
                "lambda_dangerous": gg_dangerous,
                "lambda_sd": gg_sd,
                "lambda_su": gg_su,
                "lambda_dd": gg_dd,
                "lambda_du": gg_du
            },
            "sicherheitskanal": {
                "lambda": sk_fit,
                "lambda_safe": sk_safe,
                "lambda_dangerous": sk_dangerous,
                "lambda_sd": sk_sd,
                "lambda_su": sk_su,
                "lambda_dd": sk_dd,
                "lambda_du": sk_du
            }
        }

    @staticmethod
    def calculate_unit(unit: Unit) -> Dict[str, Any]:
        """
        Calculates failure-rate totals, SFF, and DC for one functional group.
        """
        gg_fit = 0.0
        gg_safe = 0.0
        gg_dangerous = 0.0
        gg_sd = 0.0
        gg_su = 0.0
        gg_dd = 0.0
        gg_du = 0.0
        
        sk_fit = 0.0
        sk_safe = 0.0
        sk_dangerous = 0.0
        sk_sd = 0.0
        sk_su = 0.0
        sk_dd = 0.0
        sk_du = 0.0
        
        for component in unit.components:
            comp_metrics = CalculationService.calculate_component(component)
            
            # Gesamtgeraet
            gg_fit += comp_metrics["gesamtgerat"]["lambda"]
            gg_safe += comp_metrics["gesamtgerat"]["lambda_safe"]
            gg_dangerous += comp_metrics["gesamtgerat"]["lambda_dangerous"]
            gg_sd += comp_metrics["gesamtgerat"]["lambda_sd"]
            gg_su += comp_metrics["gesamtgerat"]["lambda_su"]
            gg_dd += comp_metrics["gesamtgerat"]["lambda_dd"]
            gg_du += comp_metrics["gesamtgerat"]["lambda_du"]
            
            # Sicherheitskanal
            sk_fit += comp_metrics["sicherheitskanal"]["lambda"]
            sk_safe += comp_metrics["sicherheitskanal"]["lambda_safe"]
            sk_dangerous += comp_metrics["sicherheitskanal"]["lambda_dangerous"]
            sk_sd += comp_metrics["sicherheitskanal"]["lambda_sd"]
            sk_su += comp_metrics["sicherheitskanal"]["lambda_su"]
            sk_dd += comp_metrics["sicherheitskanal"]["lambda_dd"]
            sk_du += comp_metrics["sicherheitskanal"]["lambda_du"]
            
        # SFF & DC Gesamtgeraet
        gg_sff = ((gg_safe + gg_dd) / gg_fit * 100.0) if gg_fit > 0.0 else 0.0
        gg_dc = (gg_dd / gg_dangerous * 100.0) if gg_dangerous > 0.0 else 0.0
        
        # SFF & DC Sicherheitskanal
        sk_sff_denom = sk_sd + sk_su + sk_dd + sk_du
        sk_sff = ((sk_sd + sk_su + sk_dd) / sk_sff_denom * 100.0) if sk_sff_denom > 0.0 else 0.0
        sk_dc_denom = sk_dd + sk_du
        sk_dc = (sk_dd / sk_dc_denom * 100.0) if sk_dc_denom > 0.0 else 0.0
        
        # Save SFF and DC on Unit (using Sicherheitskanal by default for safety function)
        unit.total_failure_rate = gg_fit
        unit.safe_failure_fraction = sk_sff
        unit.diagnostic_coverage = sk_dc
        unit.dangerous_detected_fraction = sk_dd
        unit.dangerous_undetected_fraction = sk_du
        
        # Legacy dict return
        legacy_res = {
            "total_failure_rate": gg_fit,
            "relevant_failure_rate": sk_sd + sk_su + sk_dd + sk_du,
            "safe_failure_rate": sk_safe,
            "dangerous_detected_rate": sk_dd,
            "dangerous_undetected_rate": sk_du,
            "lambda_sd": sk_sd,
            "lambda_su": sk_su,
            "lambda_no_part": 0.0,
            "lambda_no_effect": 0.0,
            "sff": sk_sff,
            "dc": sk_dc
        }
        
        return {
            **legacy_res,
            "gesamtgerat": {
                "lambda": gg_fit,
                "lambda_safe": gg_safe,
                "lambda_dangerous": gg_dangerous,
                "lambda_sd": gg_sd,
                "lambda_su": gg_su,
                "lambda_dd": gg_dd,
                "lambda_du": gg_du,
                "sff": gg_sff,
                "dc": gg_dc
            },
            "sicherheitskanal": {
                "lambda": sk_fit,
                "lambda_safe": sk_safe,
                "lambda_dangerous": sk_dangerous,
                "lambda_sd": sk_sd,
                "lambda_su": sk_su,
                "lambda_dd": sk_dd,
                "lambda_du": sk_du,
                "sff": sk_sff,
                "dc": sk_dc
            }
        }

    @staticmethod
    def calculate_project(project: Project):
        """
        Calculates global project totals and safety parameters for both
        Gesamtgeraet and Sicherheitskanal scopes.
        """
        gg_fit = 0.0
        gg_safe = 0.0
        gg_dangerous = 0.0
        gg_sd = 0.0
        gg_su = 0.0
        gg_dd = 0.0
        gg_du = 0.0
        
        sk_fit = 0.0
        sk_safe = 0.0
        sk_dangerous = 0.0
        sk_sd = 0.0
        sk_su = 0.0
        sk_dd = 0.0
        sk_du = 0.0
        
        for unit in project.units:
            unit_metrics = CalculationService.calculate_unit(unit)
            if unit.included_in_safety_function:
                # Gesamtgeraet
                gg_fit += unit_metrics["gesamtgerat"]["lambda"]
                gg_safe += unit_metrics["gesamtgerat"]["lambda_safe"]
                gg_dangerous += unit_metrics["gesamtgerat"]["lambda_dangerous"]
                gg_sd += unit_metrics["gesamtgerat"]["lambda_sd"]
                gg_su += unit_metrics["gesamtgerat"]["lambda_su"]
                gg_dd += unit_metrics["gesamtgerat"]["lambda_dd"]
                gg_du += unit_metrics["gesamtgerat"]["lambda_du"]
                
                # Sicherheitskanal
                sk_fit += unit_metrics["sicherheitskanal"]["lambda"]
                sk_safe += unit_metrics["sicherheitskanal"]["lambda_safe"]
                sk_dangerous += unit_metrics["sicherheitskanal"]["lambda_dangerous"]
                sk_sd += unit_metrics["sicherheitskanal"]["lambda_sd"]
                sk_su += unit_metrics["sicherheitskanal"]["lambda_su"]
                sk_dd += unit_metrics["sicherheitskanal"]["lambda_dd"]
                sk_du += unit_metrics["sicherheitskanal"]["lambda_du"]
                
        # SFF Gesamtgeraet
        gg_sff = ((gg_safe + gg_dd) / gg_fit * 100.0) if gg_fit > 0.0 else 0.0
        gg_dc = (gg_dd / gg_dangerous * 100.0) if gg_dangerous > 0.0 else 0.0
        
        # SFF & DC Sicherheitskanal
        sk_sff_denom = sk_sd + sk_su + sk_dd + sk_du
        sk_sff = ((sk_sd + sk_su + sk_dd) / sk_sff_denom * 100.0) if sk_sff_denom > 0.0 else 0.0
        sk_dc_denom = sk_dd + sk_du
        sk_dc = (sk_dd / sk_dc_denom * 100.0) if sk_dc_denom > 0.0 else 0.0
        
        # MTTFd Sicherheitskanal (in years)
        sk_dangerous_sum = sk_dd + sk_du
        sk_mttfd = 10**9 / (sk_dangerous_sum * 8760.0) if sk_dangerous_sum > 0.0 else 0.0
        
        # Store metrics on project model
        project.lambda_total_gesamtgerat = gg_fit
        project.lambda_safe_gesamtgerat = gg_safe
        project.lambda_dangerous_gesamtgerat = gg_dangerous
        project.lambda_sd_gesamtgerat = gg_sd
        project.lambda_su_gesamtgerat = gg_su
        project.lambda_dd_gesamtgerat = gg_dd
        project.lambda_du_gesamtgerat = gg_du
        project.sff_gesamtgerat = gg_sff
        
        project.lambda_total_sicherheitskanal = sk_fit
        project.lambda_safe_sicherheitskanal = sk_safe
        project.lambda_dangerous_sicherheitskanal = sk_dangerous
        project.lambda_sd_sicherheitskanal = sk_sd
        project.lambda_su_sicherheitskanal = sk_su
        project.lambda_dd_sicherheitskanal = sk_dd
        project.lambda_du_sicherheitskanal = sk_du
        project.sff_sicherheitskanal = sk_sff
        project.dc_sicherheitskanal = sk_dc
        project.mttfd_sicherheitskanal = sk_mttfd
        
        # Legacy properties (Sicherheitskanal is chosen as explicit SFF scope for Achieved SIL)
        project.total_failure_rate = sk_fit
        project.safe_failure_rate = sk_safe
        project.dangerous_detected_rate = sk_dd
        project.dangerous_undetected_rate = sk_du
        project.sff = sk_sff
        
        # PFDavg / PFHd
        t_proof = project.test_interval or 8760.0
        t_diag = project.diagnostic_test_interval or 8.0
        
        lambda_du_hour = sk_du * 10**-9
        lambda_dd_hour = sk_dd * 10**-9
        
        arch = "1oo1"
        if project.safety_context:
            arch = project.safety_context.safety_architecture
            
        pfhd = 0.0
        pfdavg = 0.0
        
        if arch == "1oo2":
            pfhd = lambda_du_hour
            pfdavg = (lambda_du_hour**2 * t_proof**2) / 3.0
        elif arch == "2oo2":
            pfhd = 2.0 * lambda_du_hour
            pfdavg = lambda_du_hour * t_proof
        else:  # 1oo1, 1oo1D, Other
            pfhd = lambda_du_hour
            pfdavg = (lambda_du_hour * t_proof / 2.0) + (lambda_dd_hour * t_diag)
            
        achieved_sil = "SIL 0"
        if sk_sff < 60.0:
            achieved_sil = "SIL 0"
        elif 60.0 <= sk_sff < 90.0:
            achieved_sil = "SIL 1"
        elif 90.0 <= sk_sff < 99.0:
            achieved_sil = "SIL 2"
        elif sk_sff >= 99.0:
            achieved_sil = "SIL 3"
            
        project.pfd_avg = pfdavg
        project.pfd_max = pfhd
        project.achieved_sil = achieved_sil
