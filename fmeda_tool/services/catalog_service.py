"""Shared catalog lookups; assignments retain references, not catalog copies."""


def linked_mitigations(project, deviation_id):
    deviation = next((d for d in project.deviations if d.id == deviation_id), None)
    if deviation is None:
        return []
    return [m for m in project.mitigations
            if m.id in deviation.mitigation_ids or deviation.id in m.deviation_ids]


def valid_mitigation(project, deviation_id, mitigation_id):
    return not mitigation_id or any(
        m.id == mitigation_id for m in linked_mitigations(project, deviation_id))


def deviation_search_text(deviation):
    return " ".join((deviation.name, deviation.description,
                     deviation.effect or "", deviation.keywords))
