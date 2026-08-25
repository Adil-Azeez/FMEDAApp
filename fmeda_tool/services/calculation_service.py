from typing import Dict, Any, List, Optional
from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment


class CalculationService:
    """Service to handle FMEDA and reliability calculations for rows, components, units, and projects"""
    
    @staticmethod
    def calculate_row_detailed(local_fit: float, classification: str, dangerous_pct: float, detection_pct: float) -> Dict[str, float]:
        """
        Calculates detailed failure rates (FIT) for a single failure mode row.
        
        Supports classifications:
            - safe_failure
            - dangerous_failure
            - no_effect_failure
            - no_part_failure
            - diagnostic_function_failure
            - not_evaluated
        """
        ld = 0.0
        ls = 0.0
        ldd = 0.0
        ldu = 0.0
        lsd = 0.0
        lsu = 0.0
        l_no_part = 0.0
        l_no_effect = 0.0
        
        d_frac = dangerous_pct / 100.0
        det_frac = detection_pct / 100.0
        
        # if classification == "no_part_failure":
        #     l_no_part = local_fit
        # elif classification == "no_effect_failure":
        #     l_no_effect = local_fit
        # elif classification == "diagnostic_function_failure":
        #     l_no_effect = local_fit
        # elif classification == "safe_failure":
        #     ls = local_fit
        #     lsd = ls * det_frac
        #     lsu = ls * (1.0 - det_frac)
        # else: # dangerous_failure or not_evaluated
        #     # Split into dangerous vs safe based on dangerous_pct
        #     ld = local_fit * d_frac
        #     ldd = ld * det_frac
        #     ldu = ld * (1.0 - det_frac)
        #
        #     ls = local_fit * (1.0 - d_frac)
        #     lsd = ls * det_frac
        #     lsu = ls * (1.0 - det_frac)
        

        classification = str(classification).strip().lower()

        if classification == "no_part_failure":
            l_no_part = local_fit

        elif classification == "no_effect_failure":
            l_no_effect = local_fit

        elif classification == "diagnostic_function_failure":
            l_no_effect = local_fit

        elif classification == "safe_failure":
            ls = local_fit
            lsd = ls * det_frac
            lsu = ls * (1.0 - det_frac)

        elif classification == "dangerous_failure":
            ld = local_fit * d_frac

            ldd = ld * det_frac
            ldu = ld * (1.0 - det_frac)

            # Remaining part is safe when Dangerous % is below 100%.
            ls = local_fit * (1.0 - d_frac)
            lsd = ls * det_frac
            lsu = ls * (1.0 - det_frac)

        elif classification == "not_evaluated":
            # Do not assign unevaluated failures to any category.
            pass

        else:
            raise ValueError(
                f"Unsupported failure classification: {classification!r}"
            )

            
        row_dc = (ldd / ld * 100.0) if ld > 0.0 else 0.0
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
            "lambda_no_part": l_no_part,
            "lambda_no_effect": l_no_effect,
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
    def calculate_component(component: Component) -> Dict[str, float]:
        """
        Calculates failure rates for a single component by summing up its failure modes.
        """
        comp_fit = component.failure_rate or 0.0
        
        tot_dd = 0.0
        tot_du = 0.0
        tot_sd = 0.0
        tot_su = 0.0
        tot_safe = 0.0
        tot_no_part = 0.0
        tot_no_effect = 0.0
        
        for assignment in component.failure_mode_assignments:
            fm_name = assignment.failure_mode_name
            fm_pct = component.failure_modes.get(fm_name, 0.0)
            local_fit = comp_fit * (fm_pct / 100.0)
            
            classif = getattr(assignment, "classification", "not_evaluated")
            dp = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage is not None else 100.0
            det = assignment.detection_percentage if assignment.detection_percentage is not None else 0.0
            
            row_metrics = CalculationService.calculate_row_detailed(local_fit, classif, dp, det)
            
            tot_dd += row_metrics["lambda_dd"]
            tot_du += row_metrics["lambda_du"]
            tot_sd += row_metrics["lambda_sd"]
            tot_su += row_metrics["lambda_su"]
            tot_safe += row_metrics["lambda_safe"]
            tot_no_part += row_metrics["lambda_no_part"]
            tot_no_effect += row_metrics["lambda_no_effect"]
            
        tot_safe_sum = tot_safe
        
        return {
            "total_failure_rate": comp_fit,
            "safe_failure_rate": tot_safe_sum,
            "dangerous_detected_rate": tot_dd,
            "dangerous_undetected_rate": tot_du,
            "lambda_sd": tot_sd,
            "lambda_su": tot_su,
            "lambda_no_part": tot_no_part,
            "lambda_no_effect": tot_no_effect
        }

    @staticmethod
    def calculate_unit(unit: Unit) -> Dict[str, float]:
        """
        Calculates failure rate totals, SFF, and DC for a single functional group (Unit).
        """
        tot_fit = 0.0
        tot_safe = 0.0
        tot_dd = 0.0
        tot_du = 0.0
        
        for component in unit.components:
            metrics = CalculationService.calculate_component(component)
            
            tot_fit += metrics["total_failure_rate"]
            tot_safe += metrics["safe_failure_rate"]
            tot_dd += metrics["dangerous_detected_rate"]
            tot_du += metrics["dangerous_undetected_rate"]
            
        tot_dangerous = tot_dd + tot_du
        dc = (tot_dd / tot_dangerous * 100.0) if tot_dangerous > 0.0 else 0.0
        sff = ((tot_safe + tot_dd) / tot_fit * 100.0) if tot_fit > 0.0 else 0.0
        
        unit.total_failure_rate = tot_fit
        unit.safe_failure_fraction = sff
        unit.diagnostic_coverage = dc
        
        return {
            "total_failure_rate": tot_fit,
            "safe_failure_rate": tot_safe,
            "dangerous_detected_rate": tot_dd,
            "dangerous_undetected_rate": tot_du,
            "sff": sff,
            "dc": dc
        }

    @staticmethod
    def calculate_project(project: Project):
        """
        Calculates global project totals and safety parameters (SFF, DC, MTTFd, PFHd, PFDavg, Achieved SIL).
        """
        proj_fit = 0.0
        proj_safe = 0.0
        proj_dd = 0.0
        proj_du = 0.0
        
        for unit in project.units:
            unit_metrics = CalculationService.calculate_unit(unit)
            if unit.included_in_safety_function:
                proj_fit += unit_metrics["total_failure_rate"]
                proj_safe += unit_metrics["safe_failure_rate"]
                proj_dd += unit_metrics["dangerous_detected_rate"]
                proj_du += unit_metrics["dangerous_undetected_rate"]
                
        proj_dangerous = proj_dd + proj_du
        overall_dc = (proj_dd / proj_dangerous * 100.0) if proj_dangerous > 0.0 else 0.0
        overall_sff = ((proj_safe + proj_dd) / proj_fit * 100.0) if proj_fit > 0.0 else 0.0
        mttfd_years = 10**9 / (proj_dangerous * 8760.0) if proj_dangerous > 0.0 else 0.0
        
        t_proof = project.test_interval or 8760.0
        t_diag = project.diagnostic_test_interval or 8.0
        
        lambda_du_hour = proj_du * 10**-9
        lambda_dd_hour = proj_dd * 10**-9
        
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
        if overall_sff < 60.0:
            achieved_sil = "SIL 0"
        elif 60.0 <= overall_sff < 90.0:
            achieved_sil = "SIL 1"
        elif 90.0 <= overall_sff < 99.0:
            achieved_sil = "SIL 2"
        elif overall_sff >= 99.0:
            achieved_sil = "SIL 3"
            
        project.total_failure_rate = proj_fit
        project.safe_failure_rate = proj_safe
        project.dangerous_detected_rate = proj_dd
        project.dangerous_undetected_rate = proj_du
        project.sff = overall_sff
        project.pfd_avg = pfdavg
        project.pfd_max = pfhd
        project.achieved_sil = achieved_sil
