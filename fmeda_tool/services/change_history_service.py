"""Semantic save diffs; calculated values and transient UI state are not audit changes."""
from collections import Counter
from copy import deepcopy
from datetime import datetime
import json
import uuid

from fmeda_tool.models import FailureModeAssignment


class ChangeHistoryService:
    PROJECT_DERIVED = {
        "total_failure_rate", "safe_failure_rate", "dangerous_detected_rate", "dangerous_undetected_rate",
        "sff", "pfd_avg", "pfd_max", "achieved_sil", "sff_gesamtgerat", "sff_sicherheitskanal",
        "dc_sicherheitskanal", "mttfd_sicherheitskanal", "change_history", "last_active_tab_id", "export_path",
    }
    UNIT_DERIVED = {"total_failure_rate", "safe_failure_fraction", "dangerous_detected_fraction",
                    "dangerous_undetected_fraction", "diagnostic_coverage"}

    @staticmethod
    def meaningful_state(project):
        data = project.model_dump(mode="json")
        for key in list(data):
            if key in ChangeHistoryService.PROJECT_DERIVED or key.startswith("lambda_"):
                data.pop(key)
        for unit in data.get("units", []):
            for key in ChangeHistoryService.UNIT_DERIVED:
                unit.pop(key, None)
            for comp in unit.get("components", []):
                comp.pop("safe_failure_fraction", None)
                # Lazy table loading materializes unevaluated assignments. Treat these as the
                # same blank rows that already exist in the component's failure-mode definition.
                assignments = {a["failure_mode_name"]: a for a in comp["failure_mode_assignments"]}
                for name, pct in comp["failure_modes"].items():
                    if name not in assignments:
                        assignments[name] = FailureModeAssignment(
                            failure_mode_name=name, failure_rate_percentage=pct,
                            classification="not_evaluated", dangerous_failure_percentage=100.0,
                            detection_percentage=0.0,
                        ).model_dump(mode="json")
                comp["failure_mode_assignments"] = list(assignments.values())

        def clean(value, field=""):
            if field == "custom_fields":
                return value  # Engineering keys must not be mistaken for internal field names.
            if isinstance(value, dict):
                return {k: clean(v, k) for k, v in value.items() if k not in {"created_at", "updated_at"}}
            if isinstance(value, list):
                return [clean(v) for v in value]
            return value
        return clean(data)

    @staticmethod
    def changes(before, after):
        if before is None:
            return [{"action": "Added", "affected_object": f"Project: {after['name']}", "field": "project",
                     "old_value": None, "new_value": {"id": after["id"], "name": after["name"]},
                     "details": "Created project"}]
        changes = []

        def readable(value):
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
            return text if len(text) <= 100 else text[:97] + "…"

        def add(action, path, old, new):
            changes.append({"action": action, "affected_object": path if action != "Changed" else path.rsplit(" / ", 1)[0],
                            "field": path, "old_value": old, "new_value": new,
                            "details": f"{action} {path}: {readable(old)} → {readable(new)}"})

        def walk(old, new, path):
            if old == new:
                return
            if isinstance(old, dict) and isinstance(new, dict):
                for key in sorted(old.keys() | new.keys()):
                    child = f"{path} / {key.replace('_', ' ')}"
                    if key not in old:
                        add("Added", child, None, new[key])
                    elif key not in new:
                        add("Removed", child, old[key], None)
                    else:
                        walk(old[key], new[key], child)
            elif isinstance(old, list) and isinstance(new, list):
                combined = old + new
                identity = next((key for key in ("id", "failure_mode_name")
                                 if combined and all(isinstance(v, dict) and key in v for v in combined)), None)
                if identity and len({v[identity] for v in old}) == len(old) and len({v[identity] for v in new}) == len(new):
                    old_map, new_map = ({v[identity]: v for v in values} for values in (old, new))
                    for key in sorted(old_map.keys() | new_map.keys()):
                        item = new_map.get(key, old_map.get(key))
                        label = item.get("position") or item.get("name") or item.get("failure_mode_name") or key
                        child = f"{path} [{label}; {key}]"
                        if key not in old_map:
                            add("Added", child, None, new_map[key])
                        elif key not in new_map:
                            add("Removed", child, old_map[key], None)
                        else:
                            walk(old_map[key], new_map[key], child)
                else:
                    add("Changed", path, old, new)
            else:
                add("Changed", path, old, new)
        walk(before, after, "Project")
        return changes

    @staticmethod
    def entry(project, changes, comment="", user=None):
        counts = Counter(item["action"].lower() for item in changes)
        summary = ", ".join(f"{count} {action}" for action, count in sorted(counts.items()))
        return {"id": uuid.uuid4().hex, "timestamp": datetime.now().isoformat(),
                "user": user or project.created_by or "System", "action": "Save Project",
                "affected_object": project.name,
                "old_value": changes[0]["old_value"] if len(changes) == 1 else None,
                "new_value": changes[0]["new_value"] if len(changes) == 1 else None,
                "details": f"{len(changes)} change(s): {summary}. " + "; ".join(c["field"] for c in changes[:3]),
                "comment": comment, "changes": deepcopy(changes)}

    @staticmethod
    def update_comment(project, index, comment):
        """The sole history editing operation: audit facts are never modified."""
        entry = project.change_history[index]
        if entry.get("comment", "") == comment:
            return False
        entry["comment"] = comment
        return True
