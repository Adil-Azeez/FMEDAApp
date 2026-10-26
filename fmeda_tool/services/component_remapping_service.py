"""Pure remapping plans. No library writes, project mutations, or calculations."""
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5, uuid4

from fmeda_tool.models import Component, FailureModeAssignment
from fmeda_tool.services.catalog_service import valid_mitigation
from fmeda_tool.services.import_service import format_value_description


def normalized_mode(name):
    return " ".join(name.split()).casefold()


def library_identity(template):
    source = template.source_type or template.database or "exida"
    if source.casefold() in ("exida", "legacy", "custom"):
        source = source.casefold()
    return source, template.library_component_id or template.id


def mode_identities(template):
    return dict(template.failure_mode_ids or (template.snapshot or {}).get("failure_mode_ids", {}))


def assignment_findings(assignment, project):
    """Existing catalogs define validity; descriptive deviation text is not a constraint."""
    if project is None:
        return []
    findings = []
    if assignment.deviation_id and not any(d.id == assignment.deviation_id for d in project.deviations):
        findings.append("Previous deviation is unavailable; select a deviation or explicitly remove it.")
    if assignment.diagnostic_measure_id and not any(d.id == assignment.diagnostic_measure_id for d in project.diagnostic_measures):
        findings.append("Previous diagnostic measure is unavailable; select a measure or explicitly remove it.")
    if not valid_mitigation(project, assignment.deviation_id, assignment.mitigation_id):
        findings.append("Previous mitigation is not linked to the deviation; select a linked mitigation or explicitly remove it.")
    return findings


@dataclass
class RemappingPlan:
    component: Component
    preserved: dict
    review: list
    matches: dict

    def summary(self):
        counts = "\n".join(f"- {count} {label}" for label, count in self.preserved.items())
        review = "\n".join("- " + text for text in self.review) or "- None"
        return f"Preserved:\n{counts}\n\nRequires review:\n{review}"


class ComponentRemappingService:
    @staticmethod
    def plan(old, template, bom, profile="Profile 1", project=None, explicit_matches=None):
        """Match identities before names. Explicit choices are the final fallback."""
        explicit_matches = explicit_matches or {}
        source, library_id = library_identity(template)
        component = old.model_copy(deep=True) if old else Component(
            id="comp_" + uuid4().hex, position=bom.designator,
            name=template.display_name, type=template.material or template.display_name)
        old_modes = (old.failure_mode_ids or (old.snapshot or {}).get("failure_mode_ids", {})) if old else {}
        previous = [a.model_copy(deep=True) for a in
                    ((old.failure_mode_assignments + old.remapping_review_assignments) if old else [])]
        for index, a in enumerate(previous):
            a.assignment_id = a.assignment_id or "assessment_" + uuid5(
                NAMESPACE_URL, f"{component.id}:{a.failure_mode_name}:{index}").hex
            a.parent_failure_mode_id = a.parent_failure_mode_id or old_modes.get(a.failure_mode_name)
        new_ids = mode_identities(template)
        proposed_assignment_ids = (template.snapshot or {}).get("assignment_ids", {})
        used, matches, assignments, review = set(), {}, [], []
        counts = {"deviations": 0, "diagnostic measures": 0, "mitigations": 0}
        # Reserve identities across the entire distribution before considering names.
        # Otherwise an early name match could steal a later mode's stable identity.
        resolved = {}
        criteria = [
            lambda name, a: bool(new_ids.get(name)) and a.parent_failure_mode_id == new_ids[name],
            lambda name, a: bool(proposed_assignment_ids.get(name)) and a.assignment_id == proposed_assignment_ids[name],
            lambda name, a: normalized_mode(a.failure_mode_name) == normalized_mode(name),
        ]
        for criterion in criteria:
            proposals = {}
            for name in template.failure_modes:
                if name in resolved:
                    continue
                found = [a for a in previous if a.assignment_id not in used and criterion(name, a)]
                if len(found) == 1:
                    proposals[name] = found[0]
            for name, a in proposals.items():
                if sum(other.assignment_id == a.assignment_id for other in proposals.values()) == 1:
                    resolved[name] = a
                    used.add(a.assignment_id)
        for name, requested in explicit_matches.items():
            if name not in template.failure_modes or name in resolved:
                raise ValueError(f"An existing match takes precedence for {name}.")
            matched = next((a for a in previous if a.assignment_id == requested and a.assignment_id not in used), None)
            if matched is None:
                raise ValueError(f"Invalid or reused assignment choice for {name}.")
            resolved[name] = matched
            used.add(matched.assignment_id)
        for name, percentage in template.failure_modes.items():
            matched = resolved.get(name)
            if matched:
                used.add(matched.assignment_id)
                matches[name] = matched.assignment_id
                a = matched.model_copy(deep=True)
                counts["deviations"] += bool(a.deviation_id)
                counts["diagnostic measures"] += bool(a.diagnostic_measure_id)
                counts["mitigations"] += bool(a.mitigation_id and (project is None or valid_mitigation(project, a.deviation_id, a.mitigation_id)))
                review.extend(f"{name}: {message}" for message in assignment_findings(a, project))
            else:
                a = FailureModeAssignment(failure_mode_name=name, failure_rate_percentage=percentage,
                    assignment_id="assessment_" + uuid4().hex, classification="not_evaluated")
            a.failure_mode_name = name
            a.failure_rate_percentage = percentage
            a.parent_failure_mode_id = new_ids.get(name) or a.parent_failure_mode_id
            assignments.append(a)
        unmatched = [a for a in previous if a.assignment_id not in used]
        review.extend(f"{a.failure_mode_name}: unmatched previous assignment retained for review." for a in unmatched)
        component.name = template.display_name
        component.type = template.material or template.display_name
        component.failure_rate = template.fits
        component.failure_modes = dict(template.failure_modes)
        component.failure_mode_ids = new_ids
        component.failure_mode_assignments = assignments
        component.remapping_review_assignments = unmatched
        component.library_component_id = library_id
        component.source_type = source
        component.failure_rate_id = template.failure_rate_id or template.shortcut
        component.item_no = template.item_no
        component.component_subtype = template.component_subtype
        component.component_use_category = template.component_use_category
        component.library_id = template.library_id or (template.snapshot or {}).get("library_id")
        component.schema_version = template.schema_version or (template.snapshot or {}).get("schema_version")
        component.selected_profile = template.selected_profile or profile
        component.snapshot = template.model_copy(deep=True).snapshot
        component.position = bom.designator
        component.part_number = component.internal_pn = bom.internal_part_number or bom.part_number
        component.value = format_value_description(bom.value, bom.description) or component.value
        component.layer = bom.layer or component.layer or "TOP"
        component.notes = component.notes if old else bom.notes or component.notes
        component.fitted_status = "Not Fitted" if not bom.is_fitted or any(
            text in (bom.notes or "").casefold() for text in ("nicht bestueckt", "nicht bestückt", "not fitted", "dnp")) else "Fitted"
        # Validate the complete proposed instance before exposing a commit candidate.
        component = Component.model_validate(component.model_dump())
        return RemappingPlan(component, counts, review, matches)
