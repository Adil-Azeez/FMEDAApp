"""Project-specific assessment cases; physical library modes stay unchanged."""
from collections import defaultdict
from decimal import Decimal
from uuid import uuid4, uuid5, NAMESPACE_URL

from fmeda_tool.models import FailureModeAssignment


def allocation_percentage(component, assignment):
    if assignment.allocation_percentage is not None:
        return assignment.allocation_percentage
    return component.failure_modes.get(assignment.failure_mode_name, 0.0)


def assessment_rows(component):
    by_name = defaultdict(list)
    for assignment in component.failure_mode_assignments:
        by_name[assignment.failure_mode_name].append(assignment)
    for name, parent_percentage in component.failure_modes.items():
        cases = by_name[name] or [FailureModeAssignment(
            failure_mode_name=name, failure_rate_percentage=parent_percentage,
            dangerous_failure_percentage=100.0, detection_percentage=0.0)]
        for case in cases:
            yield name, parent_percentage, case


def allocation_errors(component):
    grouped = defaultdict(list)
    for assignment in component.failure_mode_assignments:
        grouped[assignment.failure_mode_name].append(assignment)
    errors = []
    for name, cases in grouped.items():
        if not any(a.allocation_percentage is not None for a in cases):
            continue  # Legacy single assessments are unchanged.
        parent = Decimal(str(component.failure_modes.get(name, 0)))
        allocated = sum((Decimal(str(allocation_percentage(component, a))) for a in cases), Decimal(0))
        if allocated != parent:
            errors.append(f"{name}: Parent {parent}%; Allocated {allocated}%; Remaining {parent - allocated}%")
    return errors


def split_case(component, assignment):
    """Return two independent copies without mutating the source."""
    percentage = Decimal(str(allocation_percentage(component, assignment)))
    first, second = assignment.model_copy(deep=True), assignment.model_copy(deep=True)
    parent_id = assignment.parent_failure_mode_id or component.failure_mode_ids.get(assignment.failure_mode_name)
    parent_id = parent_id or "mode_" + uuid5(NAMESPACE_URL, f"{component.id}:{assignment.failure_mode_name}").hex
    first.parent_failure_mode_id = second.parent_failure_mode_id = parent_id
    first.assignment_id = first.assignment_id or "assessment_" + uuid4().hex
    second.assignment_id = "assessment_" + uuid4().hex
    first.allocation_percentage = float(percentage / 2)
    second.allocation_percentage = float(percentage - percentage / 2)
    return first, second
