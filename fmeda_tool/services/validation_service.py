from typing import List, Dict, Tuple, Any, Optional
import re
from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment


class ValidationService:
    """Service to validate FMEDA rows and project configurations, returning status codes and messages"""
    
    @staticmethod
    def validate_row(assignment: FailureModeAssignment, component: Component) -> Tuple[str, List[str]]:
        """
        Validates a single failure mode row (assignment).
        
        Returns:
            A tuple of (status_code, messages)
            status_code can be: 'valid' (green), 'warning' (yellow), 'error' (red)
        """
        errors = []
        warnings = []
        
        classification = getattr(assignment, "classification", "not_evaluated")
        
        # 1. Missing deviation assignment for dangerous failures
        if classification == "dangerous_failure" and not assignment.deviation_id:
            errors.append("Dangerous failure mode is missing a deviation (failure effect) assignment.")
        elif not assignment.deviation_id:
            warnings.append("Missing deviation assignment.")
            
        # 2. Check dangerous percentage bounds
        dp = assignment.dangerous_failure_percentage
        if dp is not None:
            if dp < 0.0 or dp > 100.0:
                errors.append(f"Dangerous percentage ({dp}%) is out of bounds (0-100%).")
        else:
            warnings.append("Dangerous percentage is not set (assumes 0%).")
            
        # 3. Check detection percentage bounds
        det = assignment.detection_percentage
        if det is not None:
            if det < 0.0 or det > 100.0:
                errors.append(f"Detection percentage ({det}%) is out of bounds (0-100%).")
        else:
            warnings.append("Detection percentage is not set.")
            
        # 4. Diagnostics check
        if assignment.diagnostic_measure_id and (det is None or det == 0.0):
            warnings.append("Diagnostic measure assigned but detection percentage is 0% or unset.")
        elif not assignment.diagnostic_measure_id and (det is not None and det > 0.0):
            warnings.append("Detection percentage is set but no diagnostic measure is assigned.")
            
        # 5. Blank manual fields check when deviations/measures are assigned
        if assignment.deviation_id and not (getattr(assignment, "notes", None) or "").strip():
            warnings.append("Deviation assigned but Comment/Justification is blank.")

        # DC Test Reference is not currently used in this FMEDA workflow.
        # Therefore, a selected diagnostic measure does not require dc_test_ref.
        # if assignment.diagnostic_measure_id:
        #     if not (getattr(assignment, "diagnostic_function", None) or "").strip():
        #         warnings.append("Diagnostic measure assigned but Diagnostic Function description is blank.")
        #     if not (getattr(assignment, "dc_test_ref", None) or "").strip():
        #         warnings.append("Diagnostic measure assigned but DC Test Reference is blank.")
                
        if errors:
            return "error", errors
        elif warnings:
            return "warning", warnings
        else:
            return "valid", ["Clean"]

    @staticmethod
    def validate_component(component: Component) -> Tuple[str, List[str]]:
        """
        Validates a component as a whole (e.g. failure mode distribution totals).
        """
        errors = []
        warnings = []
        
        if component.failure_rate is None or component.failure_rate <= 0.0:
            errors.append(f"Component '{component.position}' has invalid or missing failure rate (FIT).")
            
        # Sum of failure mode percentages must equal 100% (Warning as per Increment 5 specs)
        if component.failure_modes:
            total_fm_pct = sum(component.failure_modes.values())
            if abs(total_fm_pct - 100.0) > 0.01:
                warnings.append(f"Sum of failure mode distributions ({total_fm_pct:.2f}%) does not equal 100%.")
                
        for assignment in component.failure_mode_assignments:
            row_status, row_msgs = ValidationService.validate_row(assignment, component)
            if row_status == "error":
                errors.extend(f"[{assignment.failure_mode_name}] {m}" for m in row_msgs)
            elif row_status == "warning":
                warnings.extend(f"[{assignment.failure_mode_name}] {m}" for m in row_msgs)
                
        if errors:
            return "error", errors
        elif warnings:
            return "warning", warnings
        else:
            return "valid", ["Component is valid"]
            
    @staticmethod
    def validate_project(project: Project) -> List[Dict[str, Any]]:
        """
        Validates the entire project, running global, unit, component, and row checks.
        
        Returns:
            A list of alert dicts:
            {
                "severity": "Error" | "Warning" | "Info",
                "scope": "Global" | "Functional Group" | "Component",
                "item": str (Designator or name),
                "message": str (Description),
                "unit_id": Optional[str],
                "row_index": Optional[int]
            }
        """
        alerts = []
        
        # 1. Global metadata checks
        if not project.name:
            alerts.append({"severity": "Error", "scope": "Global", "item": "Project Name", "message": "Project Name is missing.", "unit_id": None, "row_index": None})
        if not project.project_number:
            alerts.append({"severity": "Error", "scope": "Global", "item": "Project Number", "message": "Project Number is missing.", "unit_id": None, "row_index": None})
        if not project.description:
            alerts.append({"severity": "Warning", "scope": "Global", "item": "Description", "message": "Project description is empty.", "unit_id": None, "row_index": None})
        if not project.reviewer:
            alerts.append({"severity": "Warning", "scope": "Global", "item": "Reviewer", "message": "No reviewer assigned.", "unit_id": None, "row_index": None})
        if not project.units:
            alerts.append({"severity": "Error", "scope": "Global", "item": "Functional Groups", "message": "No functional groups exist.", "unit_id": None, "row_index": None})
            
        # 2. SIL Target Mismatch
        sil_levels = {"SIL 0": 0, "SIL 1": 1, "SIL 2": 2, "SIL 3": 3, "SIL 4": 4}
        target_val = sil_levels.get(project.target_sil, 0)
        achieved_val = sil_levels.get(project.achieved_sil, 0)
        if achieved_val < target_val:
            alerts.append({
                "severity": "Error",
                "scope": "Global",
                "item": "Target SIL Mismatch",
                "message": f"Target SIL is {project.target_sil} but Achieved SIL is {project.achieved_sil}.",
                "unit_id": None,
                "row_index": None
            })
            
        # 3. Unit, component, and row checks
        for unit in project.units:
            if not unit.components and not getattr(unit, "bom_components", None):
                alerts.append({
                    "severity": "Warning",
                    "scope": "Functional Group",
                    "item": unit.name,
                    "message": "No component instances added or BOM imported in this group.",
                    "unit_id": unit.id,
                    "row_index": None
                })
                
            # Unmapped BOM components check
            bom_components = getattr(unit, "bom_components", []) or []
            component_designators = {c.position.upper() for c in unit.components}
            for bom in bom_components:
                if bom.designator.upper() not in component_designators:
                    alerts.append({
                        "severity": "Warning",
                        "scope": "Functional Group",
                        "item": bom.designator,
                        "message": f"BOM Component '{bom.designator}' has not been mapped to any database template.",
                        "unit_id": unit.id,
                        "row_index": None
                    })
                    
            # Check components and rows
            row_index = 0
            for comp in unit.components:
                # Check sum of failure modes
                tot_dist = sum(comp.failure_modes.values()) if comp.failure_modes else 0
                if abs(tot_dist - 100.0) > 0.01 and comp.failure_modes:
                    alerts.append({
                        "severity": "Warning",
                        "scope": "Component",
                        "item": comp.position,
                        "message": f"Failure mode distribution for component {comp.position} is {tot_dist:.1f}% (must be 100%).",
                        "unit_id": unit.id,
                        "row_index": row_index
                    })
                    
                for fm_name, fm_perc in comp.failure_modes.items():
                    assignment = next((a for a in comp.failure_mode_assignments if a.failure_mode_name == fm_name), None)
                    if assignment:
                        status, msgs = ValidationService.validate_row(assignment, comp)
                        if status == "error":
                            for msg in msgs:
                                alerts.append({
                                    "severity": "Error",
                                    "scope": "Component",
                                    "item": f"{comp.position} ({fm_name})",
                                    "message": msg,
                                    "unit_id": unit.id,
                                    "row_index": row_index
                                })
                        elif status == "warning":
                            for msg in msgs:
                                alerts.append({
                                    "severity": "Warning",
                                    "scope": "Component",
                                    "item": f"{comp.position} ({fm_name})",
                                    "message": msg,
                                    "unit_id": unit.id,
                                    "row_index": row_index
                                })
                    row_index += 1
                    
        return alerts
