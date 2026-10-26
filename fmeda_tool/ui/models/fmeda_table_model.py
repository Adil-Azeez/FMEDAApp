"""
FmedaTableModel: High-performance QAbstractTableModel for the FMEDA spreadsheet.
Eliminates permanent per-cell widgets by handling data rendering, validation coloring,
subtle entry-origin highlighting, cell editing, and targeted row recalculations natively.
"""

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment
from fmeda_tool.models.failure_mode_assignment import CLASSIFICATIONS, CLASSIFICATION_LABELS
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.component_ordering import component_blocks
from fmeda_tool.services.validation_service import ValidationService
from fmeda_tool.services.catalog_service import linked_mitigations, valid_mitigation, deviation_search_text


COLUMN_HEADERS = [
    "Component ID / Designator", "Status", "Function", "Value / Description",
    "Internal Part Number", "Display Name / Component Type",
    "Failure Mode", "Failure-Mode %", "Base Failure Rate (FIT)",
    "Failure Effect / Deviation", "Diagnostic Function", "Failure Classification",
    "Dangerous %", "Safe %",
    "Diagnostic Measure ID", "Detection % (DC)", "Mitigation",
    "Comments / Justification", "Review Status",
    "Proof Test A", "Proof Test B", "Proof Test C",
    "lambda (FIT)", "lambda_safe (FIT)", "lambda_dangerous (FIT)",
    "lambda_sd (FIT)", "lambda_su (FIT)", "lambda_dd (FIT)", "lambda_du (FIT)",
    "lambda_no_part (FIT)", "lambda_no_effect (FIT)", "SFF %", "DC %", "MTBF (h)", "MTTFd (y)"
]

CLASSIFICATION_DISPLAY_MAP = CLASSIFICATION_LABELS

CLASSIFICATION_DATA_MAP = {v: k for k, v in CLASSIFICATION_DISPLAY_MAP.items()}


@dataclass
class FmedaRowEntry:
    is_separator: bool = False
    component: Optional[Component] = None
    assignment: Optional[FailureModeAssignment] = None
    fm_name: str = ""
    fm_percentage: float = 0.0
    row_metrics: Dict[str, float] = field(default_factory=dict)
    validation_status: str = "valid"
    validation_messages: List[str] = field(default_factory=list)


class FmedaTableModel(QAbstractTableModel):
    """
    Model backing the FMEDA spreadsheet with 35 simplified columns,
    subtle entry-origin styling, and Locked View Mode vs Edit Mode control.
    """
    data_modified = pyqtSignal()

    def __init__(self, unit: Unit, project: Project, auto_populate: bool = True, parent=None):
        super().__init__(parent)
        self.unit = unit
        self.project = project
        self.is_edit_mode: bool = False
        self.rows: List[FmedaRowEntry] = []
        self.active_search_row: Optional[int] = None
        self._search_texts = {}
        self.dataChanged.connect(self._invalidate_search_text)
        if auto_populate:
            self._rebuild_rows()

    def search_rows(self, query: str):
        """Return only matching data rows, without recalculating or mutating project data."""
        query = query.strip().casefold()
        if not query:
            return [], set(range(len(self.rows)))
        matches = []
        for row, entry in enumerate(self.rows):
            if entry.is_separator:
                continue
            comp = entry.component
            if row not in self._search_texts:
                values = [self._get_cell_value(col, comp, entry.assignment, entry, Qt.ItemDataRole.DisplayRole)
                          for col in range(self.columnCount()) if col != 1]
                # A lazy text index, not a second set of project objects. Hidden/raw engineering
                # values remain searchable alongside their displayed names and numbers.
                values.extend(entry.assignment.model_dump().values())
                values.extend((comp.name, comp.type, comp.value, comp.part_number,
                               (comp.snapshot or {}).get("description")))
                self._search_texts[row] = "\n".join(str(v).casefold() for v in values if v is not None)
            if query in self._search_texts[row]:
                matches.append(row)
        return matches, set(matches)

    def _invalidate_search_text(self, first, last, roles=None):
        if not roles or Qt.ItemDataRole.DisplayRole in roles:
            for row in range(first.row(), last.row() + 1):
                self._search_texts.pop(row, None)

    def set_active_search_row(self, row):
        previous = self.active_search_row
        self.active_search_row = row
        for affected in (previous, row):
            if affected is not None and 0 <= affected < len(self.rows):
                self.dataChanged.emit(self.index(affected, 0), self.index(affected, self.columnCount() - 1),
                                      [Qt.ItemDataRole.BackgroundRole])

    def set_edit_mode(self, enabled: bool) -> None:
        """Enables or disables cell editing."""
        if self.is_edit_mode != enabled:
            self.is_edit_mode = enabled
            if self.rows:
                top_left = self.index(0, 0)
                bottom_right = self.index(len(self.rows) - 1, len(COLUMN_HEADERS) - 1)
                self.dataChanged.emit(top_left, bottom_right)

    def _rebuild_rows(self) -> None:
        """Builds internal row entries and precomputes initial row metrics."""
        self.rows.clear()
        self._search_texts.clear()
        if not self.unit or not self.unit.components:
            return

        for block in component_blocks(self.unit):
            if self.rows and any(c.failure_modes for c in block.components):
                self.rows.append(FmedaRowEntry(is_separator=True))
            for comp in block.components:
                self._append_component_rows(comp)

    def _append_component_rows(self, comp):
        for fm_name, fm_percentage in comp.failure_modes.items():
            assignment = next((a for a in comp.failure_mode_assignments if a.failure_mode_name == fm_name), None)
            if not assignment:
                assignment = FailureModeAssignment(
                    failure_mode_name=fm_name,
                    failure_rate_percentage=fm_percentage,
                    classification="not_evaluated",
                    dangerous_failure_percentage=100.0,
                    detection_percentage=0.0
                )
                comp.failure_mode_assignments.append(assignment)

            entry = FmedaRowEntry(
                is_separator=False,
                component=comp,
                assignment=assignment,
                fm_name=fm_name,
                fm_percentage=fm_percentage
            )
            self._compute_entry_metrics(entry)
            self.rows.append(entry)

    def reload_data(self) -> None:
        """Full model reload."""
        self.beginResetModel()
        self._rebuild_rows()
        self.endResetModel()

    def _compute_entry_metrics(self, entry: FmedaRowEntry) -> None:
        """Calculates row detailed metrics and validation status for a single row entry."""
        if entry.is_separator or not entry.component or not entry.assignment:
            return

        comp = entry.component
        assignment = entry.assignment
        entry.row_metrics = CalculationService.calculate_assignment(comp, assignment)
        status, msgs = ValidationService.validate_row(assignment, comp, self.project)
        entry.validation_status = status
        entry.validation_messages = msgs

    def refresh_all_metrics(self) -> None:
        """Refreshes metrics across all rows with targeted dataChanged."""
        self.sync_components(set())
        for r_idx, entry in enumerate(self.rows):
            if not entry.is_separator:
                self._compute_entry_metrics(entry)
        if self.rows:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.rows) - 1, len(COLUMN_HEADERS) - 1)
            )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMN_HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(COLUMN_HEADERS):
                return COLUMN_HEADERS[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self.rows):
            return Qt.ItemFlag.NoItemFlags

        entry = self.rows[row]
        if entry.is_separator:
            return Qt.ItemFlag.NoItemFlags

        base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

        # In View Mode, cells are not editable
        if not self.is_edit_mode:
            return base_flags

        # In Edit Mode, editable engineering columns return ItemIsEditable
        editable_cols = {2, 3, 4, 7, 9, 10, 11, 14, 15, 16, 17, 18, 19, 20, 21}
        if col in editable_cols:
            return base_flags | Qt.ItemFlag.ItemIsEditable

        return base_flags

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self.rows):
            return None

        entry = self.rows[row]

        # Separator row styling
        if entry.is_separator:
            if role == Qt.ItemDataRole.BackgroundRole:
                return QBrush(QColor("#e9ecef"))
            return None

        comp = entry.component
        assignment = entry.assignment
        metrics = entry.row_metrics

        # 1. Background Role (Validation status + subtle entry-origin colors)
        if role == Qt.ItemDataRole.BackgroundRole:
            if row == self.active_search_row:
                return QBrush(QColor("#ffe08a"))
            # High priority: Validation warnings and errors on identification columns
            if col < 9:
                if entry.validation_status == "error":
                    return QBrush(QColor("#f8d7da"))
                elif entry.validation_status == "warning":
                    return QBrush(QColor("#fff3cd"))

            # Calculated columns: very light gray
            if col >= 22:
                return QBrush(QColor("#f8f9fa"))

            # Manual engineering inputs: subtle warm cream/yellow
            if col in (2, 3, 4, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21):
                return QBrush(QColor("#fffdf0"))

            # Library / BOM supplied components
            if col in (0, 5, 6, 7, 8):
                is_bom_imported = any(b.designator == comp.position for b in getattr(self.unit, "bom_components", []) or [])
                if is_bom_imported:
                    return QBrush(QColor("#f2faf2"))  # Subtle green for BOM
                return QBrush(QColor("#f0f7ff"))  # Subtle blue for Library

            return None

        # 2. Tooltip Role
        if role == Qt.ItemDataRole.ToolTipRole:
            if col in (11, 12, 13):
                return CLASSIFICATION_LABELS.get(assignment.classification, "Not Evaluated") + "\nClassification allocates the full failure-mode rate. Legacy percentage values are retained until review."
            if col == 14:
                dm = next((m for m in self.project.diagnostic_measures if m.id == assignment.diagnostic_measure_id), None)
                if dm:
                    return f"{dm.display_label}\n{dm.description}\nVerification Method: {dm.verification_method or ''}\nExecution Timing: {dm.execution_timing or ''}"
            if col == 16 and not valid_mitigation(self.project, assignment.deviation_id, assignment.mitigation_id):
                return "Invalid deviation/mitigation combination: mitigation is not linked to the selected deviation."
            origin_info = "Origin: Library"
            if col >= 22:
                origin_info = "Origin: Calculated"
            elif col in (2, 3, 4, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21):
                origin_info = "Origin: Manual Engineering"
            elif any(b.designator == comp.position for b in getattr(self.unit, "bom_components", []) or []):
                origin_info = "Origin: BOM Import"

            if col == 1 or col < 9:
                if entry.validation_messages:
                    return f"{origin_info}\n" + "\n".join(entry.validation_messages)
            return origin_info

        # 3. Text Alignment Role
        if role == Qt.ItemDataRole.TextAlignmentRole:
            center_cols = {0, 1, 5, 7, 8, 11, 12, 13, 15, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35}
            if col in center_cols:
                return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        # 5. DisplayRole and EditRole
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._get_cell_value(col, comp, assignment, entry, role)

        # 6. Dropdown Options Role for ComboBoxDelegate
        if role == Qt.ItemDataRole.UserRole + 1:
            return self._get_dropdown_options(col, assignment)

        return None

    def _get_dropdown_options(self, col: int, assignment=None) -> List[Dict[str, Any]]:
        """Returns option list for delegate combo boxes."""
        if col == 9:  # Deviation
            opts = [{"label": "-- None --", "data": None}]
            for dev in self.project.deviations:
                opts.append({"label": dev.name, "data": dev.id, "search": deviation_search_text(dev)})
            return opts
        elif col == 10:  # Diagnostic Function: no implicit default
            return [{"label": "", "data": ""}, {"label": "Yes", "data": "Yes"}, {"label": "No", "data": "No"}]
        elif col == 11:  # Classification
            legacy = assignment is not None and assignment.classification == "legacy_no_part_no_effect"
            options = [{"label": label, "data": key,
                        "enabled": not legacy or key in ("no_part_failure", "no_effect_failure")}
                       for key, label in CLASSIFICATIONS.items()]
            if legacy:
                options.insert(0, {"label": CLASSIFICATION_LABELS[assignment.classification],
                                   "data": assignment.classification, "enabled": False})
            return options
        elif col == 14:  # Diagnostic Measure
            opts = [{"label": "-- None --", "data": None}]
            for dm in self.project.diagnostic_measures:
                opts.append({"label": dm.display_label, "data": dm.id,
                             "search": "\n".join(getattr(dm, field) or "" for field in
                                                 ("id", "name", "description", "verification_method",
                                                  "execution_timing", "notes"))})
            return opts
        elif col == 16:  # Mitigation
            opts = [{"label": "-- None --", "data": None}]
            for mit in linked_mitigations(self.project, assignment.deviation_id if assignment else None):
                opts.append({"label": mit.name or mit.id, "data": mit.id})
            return opts
        elif col == 18:  # Review Status
            return [
                {"label": "Draft", "data": "draft"},
                {"label": "Under Review", "data": "under_review"},
                {"label": "Approved", "data": "approved"}
            ]
        return []

    def _get_cell_value(self, col: int, comp: Component, assignment: FailureModeAssignment, entry: FmedaRowEntry, role: int) -> Any:
        metrics = entry.row_metrics

        if col == 0:
            return comp.position
        elif col == 1:
            if entry.validation_status == "error":
                return "🔴"
            elif entry.validation_status == "warning":
                return "🟡"
            return "🟢"
        elif col == 2:
            return comp.function or ""
        elif col == 3:
            return comp.value or ""
        elif col == 4:
            return comp.internal_pn or ""
        elif col == 5:
            disp_label = None
            if getattr(comp, "snapshot", None) and isinstance(comp.snapshot, dict):
                disp_label = comp.snapshot.get("displayed_label") or comp.snapshot.get("display_name")
            if not disp_label:
                disp_label = comp.type or comp.name
            return disp_label or ""
        elif col == 6:
            return entry.fm_name
        elif col == 7:
            pct = comp.failure_modes.get(entry.fm_name, entry.fm_percentage)
            return pct if role == Qt.ItemDataRole.EditRole else f"{pct:.1f}%"
        elif col == 8:
            rate = comp.failure_rate or 0.0
            return rate if role == Qt.ItemDataRole.EditRole else f"{rate:.4f}"
        elif col == 9:
            dev_id = assignment.deviation_id
            if role == Qt.ItemDataRole.EditRole:
                return dev_id
            if dev_id:
                dev = next((d for d in self.project.deviations if d.id == dev_id), None)
                return dev.name if dev else dev_id
            return "-- None --"
        elif col == 10:
            return assignment.diagnostic_function or ""
        elif col == 11:
            classif = getattr(assignment, "classification", "not_evaluated")
            if role == Qt.ItemDataRole.EditRole:
                return classif
            return CLASSIFICATION_DISPLAY_MAP.get(classif, "Not Evaluated")
        elif col == 12:
            dp = assignment.dangerous_failure_percentage if assignment.classification_version == 1 else (100.0 if assignment.classification == "dangerous_failure" else 0.0)
            dp = dp if dp is not None else 100.0
            return dp if role == Qt.ItemDataRole.EditRole else f"{dp:.1f}%"
        elif col == 13:
            dp = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage is not None else 100.0
            safe_pct = 100.0 - dp if assignment.classification_version == 1 else (100.0 if assignment.classification == "safe_failure" else 0.0)
            return safe_pct if role == Qt.ItemDataRole.EditRole else f"{safe_pct:.1f}%"
        elif col == 14:
            dm_id = assignment.diagnostic_measure_id
            if role == Qt.ItemDataRole.EditRole:
                return dm_id
            if dm_id:
                dm = next((m for m in self.project.diagnostic_measures if m.id == dm_id), None)
                return dm.display_label if dm else dm_id
            return "-- None --"
        elif col == 15:
            det = assignment.detection_percentage if assignment.detection_percentage is not None else 0.0
            return det if role == Qt.ItemDataRole.EditRole else f"{det:.1f}%"
        elif col == 16:
            mit_id = assignment.mitigation_id
            if role == Qt.ItemDataRole.EditRole:
                return mit_id
            if mit_id:
                mit = next((m for m in self.project.mitigations if m.id == mit_id), None)
                label = (mit.name or mit.id) if mit else mit_id
                return label if valid_mitigation(self.project, assignment.deviation_id, mit_id) else f"⚠ Invalid: {label}"
            return "-- None --"
        elif col == 17:
            return assignment.notes or ""
        elif col == 18:
            st = getattr(assignment, "review_status", "draft") or "draft"
            if role == Qt.ItemDataRole.EditRole:
                return st.lower()
            return st.title()
        elif col == 19:
            val = getattr(assignment, "proof_test_a", 0.0) or 0.0
            return val if role == Qt.ItemDataRole.EditRole else f"{val:.1f}%"
        elif col == 20:
            val = getattr(assignment, "proof_test_b", 0.0) or 0.0
            return val if role == Qt.ItemDataRole.EditRole else f"{val:.1f}%"
        elif col == 21:
            val = getattr(assignment, "proof_test_c", 0.0) or 0.0
            return val if role == Qt.ItemDataRole.EditRole else f"{val:.1f}%"
        elif col == 22:
            return f"{metrics.get('lambda', 0.0):.4f}"
        elif col == 23:
            return f"{metrics.get('lambda_safe', 0.0):.4f}"
        elif col == 24:
            return f"{metrics.get('lambda_dangerous', 0.0):.4f}"
        elif col == 25:
            return f"{metrics.get('lambda_sd', 0.0):.4f}"
        elif col == 26:
            return f"{metrics.get('lambda_su', 0.0):.4f}"
        elif col == 27:
            return f"{metrics.get('lambda_dd', 0.0):.4f}"
        elif col == 28:
            return f"{metrics.get('lambda_du', 0.0):.4f}"
        elif col == 29:
            return f"{metrics.get('lambda_no_part', 0.0):.4f}"
        elif col == 30:
            return f"{metrics.get('lambda_no_effect', 0.0):.4f}"
        elif col == 31:
            return f"{metrics.get('sff', 0.0):.1f}%"
        elif col == 32:
            return f"{metrics.get('dc', 0.0):.1f}%"
        elif col == 33:
            mtbf = metrics.get('mtbf', 0.0)
            return f"{mtbf:.1e}" if mtbf > 0 else "N/A"
        elif col == 34:
            mttfd = metrics.get('mttfd', 0.0)
            return f"{mttfd:.1f}" if mttfd > 0 else "N/A"
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or not self.is_edit_mode:
            return False

        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self.rows):
            return False

        entry = self.rows[row]
        if entry.is_separator or not entry.component or not entry.assignment:
            return False

        comp = entry.component
        assignment = entry.assignment

        if role != Qt.ItemDataRole.EditRole:
            return False

        # Component-level text fields (col 2, 3, 4) propagate to all rows for this component
        if col in (2, 3, 4):
            if col == 2:
                comp.function = str(value)
            elif col == 3:
                comp.value = str(value)
            elif col == 4:
                comp.internal_pn = str(value)

            for r_idx, r_entry in enumerate(self.rows):
                if r_entry.component == comp:
                    self.dataChanged.emit(self.index(r_idx, 0), self.index(r_idx, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Failure-Mode % (col 7)
        if col == 7:
            try:
                fm_pct = float(value)
                comp.failure_modes[entry.fm_name] = fm_pct
                assignment.failure_rate_percentage = fm_pct
                entry.fm_percentage = fm_pct
                self._compute_entry_metrics(entry)
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
                self.data_modified.emit()
                return True
            except (ValueError, TypeError):
                return False

        # Deviation (col 9)
        if col == 9:
            value = value or None
            if value and not any(d.id == value for d in self.project.deviations):
                return False
            if assignment.deviation_id == value:
                return False
            assignment.deviation_id = value
            if not valid_mitigation(self.project, value, assignment.mitigation_id):
                assignment.mitigation_id = None
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Diagnostic Function (col 10)
        if col == 10:
            if value not in (None, "", "Yes", "No"):
                return False
            value = value or None
            if assignment.diagnostic_function == value:
                return False
            assignment.diagnostic_function = value
            # Refresh validation only; this independent choice changes no other assignment field.
            entry.validation_status, entry.validation_messages = ValidationService.validate_row(assignment, comp, self.project)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Classification (col 11)
        if col == 11:
            class_key = CLASSIFICATION_DATA_MAP.get(value, value)
            try:
                assignment.set_classification(class_key)
            except ValueError:
                return False
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        if col in (12, 13):
            return False  # Classification defines the full safe/dangerous bucket.

        # Diagnostic Measure (col 14)
        if col == 14:
            dm_id = value if value else None
            if dm_id and not any(m.id == dm_id for m in self.project.diagnostic_measures):
                return False
            if assignment.diagnostic_measure_id == dm_id:
                return False
            assignment.diagnostic_measure_id = dm_id
            if dm_id:
                dm = next((m for m in self.project.diagnostic_measures if m.id == dm_id), None)
                if dm and dm.dc is not None:
                    assignment.detection_percentage = dm.dc
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Detection % (col 15)
        if col == 15:
            try:
                det = float(value)
                assignment.detection_percentage = det
                self._compute_entry_metrics(entry)
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
                self.data_modified.emit()
                return True
            except (ValueError, TypeError):
                return False

        # Mitigation (col 16)
        if col == 16:
            if not valid_mitigation(self.project, assignment.deviation_id, value):
                return False
            assignment.mitigation_id = value if value else None
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Notes / Comments (col 17)
        if col == 17:
            assignment.notes = str(value) if value else None
            self.dataChanged.emit(self.index(row, 17), self.index(row, 17))
            self.data_modified.emit()
            return True

        # Review Status (col 18)
        if col == 18:
            assignment.review_status = str(value).lower()
            self.dataChanged.emit(self.index(row, 18), self.index(row, 18))
            self.data_modified.emit()
            return True

        # Proof Test A, B, C (col 19, 20, 21)
        if col in (19, 20, 21):
            try:
                pt_val = float(value)
                if col == 19:
                    assignment.proof_test_a = pt_val
                elif col == 20:
                    assignment.proof_test_b = pt_val
                elif col == 21:
                    assignment.proof_test_c = pt_val
                self.dataChanged.emit(self.index(row, col), self.index(row, col))
                self.data_modified.emit()
                return True
            except (ValueError, TypeError):
                return False

        return False

    def get_row_indices_for_component(self, comp_id: str) -> List[int]:
        """Returns all model row indices corresponding to the given component ID."""
        indices = []
        for r_idx, entry in enumerate(self.rows):
            if not entry.is_separator and entry.component and entry.component.id == comp_id:
                indices.append(r_idx)
        return indices

    def sync_components(self, changed_ids):
        """Refresh changed blocks once, retaining every unaffected row and lazy tab."""
        old_entries = {(entry.component.id, entry.fm_name): entry for entry in self.rows if not entry.is_separator}
        separators = {}
        for index, entry in enumerate(self.rows[:-1]):
            if entry.is_separator and self.rows[index + 1].component:
                separators[self.rows[index + 1].component.id] = entry
        desired = []
        ordered = [(component, index) for block in component_blocks(self.unit)
                   for index, component in enumerate(c for c in block.components if c.failure_modes)]
        for component, index in ordered:
            if desired and index == 0:
                desired.append(separators.get(component.id) or FmedaRowEntry(is_separator=True))
            assignments = {a.failure_mode_name: a for a in component.failure_mode_assignments}
            for name, pct in component.failure_modes.items():
                entry = old_entries.get((component.id, name))
                if entry is None or component.id in changed_ids:
                    assignment = assignments.get(name)
                    if assignment is None:
                        assignment = FailureModeAssignment(failure_mode_name=name, failure_rate_percentage=pct)
                        component.failure_mode_assignments.append(assignment)
                    entry = FmedaRowEntry(component=component, assignment=assignment, fm_name=name, fm_percentage=pct)
                    self._compute_entry_metrics(entry)
                desired.append(entry)
        prefix = 0
        while prefix < min(len(self.rows), len(desired)) and self.rows[prefix] is desired[prefix]:
            prefix += 1
        suffix = 0
        while suffix < min(len(self.rows), len(desired)) - prefix and self.rows[-suffix - 1] is desired[-suffix - 1]:
            suffix += 1
        old_end, new_end = len(self.rows) - suffix, len(desired) - suffix
        if old_end > prefix:
            self.beginRemoveRows(QModelIndex(), prefix, old_end - 1)
            del self.rows[prefix:old_end]
            self.endRemoveRows()
        if new_end > prefix:
            self.beginInsertRows(QModelIndex(), prefix, new_end - 1)
            self.rows[prefix:prefix] = desired[prefix:new_end]
            self.endInsertRows()
        self._search_texts.clear()
        self.active_search_row = None

    def get_distinct_component_ids(self) -> List[str]:
        """Returns ordered list of distinct component IDs currently visible in model rows."""
        comp_ids = []
        for entry in self.rows:
            if not entry.is_separator and entry.component and entry.component.id:
                if entry.component.id not in comp_ids:
                    comp_ids.append(entry.component.id)
        return comp_ids
