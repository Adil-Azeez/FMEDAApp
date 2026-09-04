"""
FmedaTableModel: High-performance QAbstractTableModel for the FMEDA spreadsheet.
Eliminates permanent per-cell widgets by handling data rendering, validation coloring,
cell editing, and targeted row recalculations natively.
"""

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from fmeda_tool.models import Project, Unit, Component, FailureModeAssignment
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.validation_service import ValidationService


COLUMN_HEADERS = [
    "Component ID / Designator", "Status", "Function", "Value / Description",
    "Internal Part Number", "Fitted Status", "Component Type",
    "Failure Mode", "Failure-Mode %", "Base Failure Rate (FIT)",
    "Reliability Source", "Source Reference", "Environmental Profile",
    "Failure Effect / Deviation", "Diagnostic Function", "Failure Classification",
    "Dangerous %", "Safe %",
    "Diagnostic Measure ID", "Detection % (DC)", "DC Test Ref", "Mitigation",
    "Comments / Justification", "Review Status",
    "Proof Test A", "Proof Test B", "Proof Test C", "No Part / No Effect",
    "lambda (FIT)", "lambda_safe (FIT)", "lambda_dangerous (FIT)",
    "lambda_sd (FIT)", "lambda_su (FIT)", "lambda_dd (FIT)", "lambda_du (FIT)",
    "lambda_no_part (FIT)", "lambda_no_effect (FIT)", "SFF %", "DC %", "MTBF (h)", "MTTFd (y)"
]

CLASSIFICATION_DISPLAY_MAP = {
    "not_evaluated": "Not Evaluated",
    "safe_failure": "Safe Failure",
    "dangerous_failure": "Dangerous Failure"
}

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
    Model backing the FMEDA spreadsheet with targeted row recalculations
    and Locked View Mode vs Edit Mode control.
    """
    data_modified = pyqtSignal()

    def __init__(self, unit: Unit, project: Project, parent=None):
        super().__init__(parent)
        self.unit = unit
        self.project = project
        self.is_edit_mode: bool = False
        self.rows: List[FmedaRowEntry] = []
        self._rebuild_rows()

    def set_edit_mode(self, enabled: bool) -> None:
        """Enables or disables cell editing."""
        if self.is_edit_mode != enabled:
            self.is_edit_mode = enabled
            # Emit dataChanged across whole model to update editable flags/styles
            if self.rows:
                top_left = self.index(0, 0)
                bottom_right = self.index(len(self.rows) - 1, len(COLUMN_HEADERS) - 1)
                self.dataChanged.emit(top_left, bottom_right)

    def _rebuild_rows(self) -> None:
        """Builds internal row entries and precomputes initial row metrics."""
        self.rows.clear()
        if not self.unit or not self.unit.components:
            return

        is_first_comp = True
        for comp in self.unit.components:
            if not is_first_comp:
                self.rows.append(FmedaRowEntry(is_separator=True))
            is_first_comp = False

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
        fm_percentage = comp.failure_modes.get(entry.fm_name, entry.fm_percentage)
        local_fit = (comp.failure_rate or 0.0) * (fm_percentage / 100.0)
        classif = getattr(assignment, "classification", "not_evaluated")
        dp = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage is not None else 100.0
        det = assignment.detection_percentage if assignment.detection_percentage is not None else 0.0

        if classif in ["no_part_failure", "no_effect_failure", "diagnostic_function_failure"]:
            assignment.dont_care = True
            assignment.dangerous_failure_percentage = 0.0
            assignment.classification = "safe_failure"
            classif = "safe_failure"
            dp = 0.0

        entry.row_metrics = CalculationService.calculate_row_detailed(local_fit, classif, dp, det)
        status, msgs = ValidationService.validate_row(assignment, comp)
        entry.validation_status = status
        entry.validation_messages = msgs

    def refresh_all_metrics(self) -> None:
        """Refreshes metrics across all rows with targeted dataChanged."""
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

        # In Edit Mode, editable columns return ItemIsEditable (or ItemIsUserCheckable for col 27)
        editable_cols = {2, 3, 4, 5, 8, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26}
        if col in editable_cols:
            return base_flags | Qt.ItemFlag.ItemIsEditable
        elif col == 27:  # DON'T CARE / No Part checkbox
            return base_flags | Qt.ItemFlag.ItemIsUserCheckable

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
                return QBrush(QColor("#f8f9fa"))
            return None

        comp = entry.component
        assignment = entry.assignment
        metrics = entry.row_metrics

        # 1. Background Role (Validation status coloring)
        if role == Qt.ItemDataRole.BackgroundRole:
            if col < 13:
                if entry.validation_status == "error":
                    return QBrush(QColor("#f8d7da"))
                elif entry.validation_status == "warning":
                    return QBrush(QColor("#fff3cd"))
            return None

        # 2. Tooltip Role
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == 1 or col < 13:
                if entry.validation_messages:
                    return "\n".join(entry.validation_messages)
                return "Clean"
            return None

        # 3. Text Alignment Role
        if role == Qt.ItemDataRole.TextAlignmentRole:
            center_cols = {0, 1, 5, 6, 8, 9, 10, 11, 12, 15, 16, 17, 19, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40}
            if col in center_cols:
                return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        # 4. CheckState Role (Col 27 - No Part / No Effect)
        if role == Qt.ItemDataRole.CheckStateRole and col == 27:
            return Qt.CheckState.Checked if getattr(assignment, "dont_care", False) else Qt.CheckState.Unchecked

        # 5. DisplayRole and EditRole
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._get_cell_value(col, comp, assignment, entry, role)

        # 6. Dropdown Options Role for ComboBoxDelegate
        if role == Qt.ItemDataRole.UserRole + 1:
            return self._get_dropdown_options(col)

        return None

    def _get_dropdown_options(self, col: int) -> List[Dict[str, Any]]:
        """Returns option list for delegate combo boxes."""
        if col == 5:  # Fitted Status
            return [{"label": "Fitted", "data": "Fitted"}, {"label": "Not Fitted", "data": "Not Fitted"}]
        elif col == 13:  # Deviation
            opts = [{"label": "-- None --", "data": None}]
            for dev in self.project.deviations:
                opts.append({"label": dev.name, "data": dev.id})
            return opts
        elif col == 15:  # Classification
            return [
                {"label": "Not Evaluated", "data": "not_evaluated"},
                {"label": "Safe Failure", "data": "safe_failure"},
                {"label": "Dangerous Failure", "data": "dangerous_failure"}
            ]
        elif col == 18:  # Diagnostic Measure
            opts = [{"label": "-- None --", "data": None}]
            for dm in self.project.diagnostic_measures:
                opts.append({"label": dm.description, "data": dm.id})
            return opts
        elif col == 21:  # Mitigation
            opts = [{"label": "-- None --", "data": None}]
            for mit in self.project.mitigations:
                opts.append({"label": mit.name or mit.id, "data": mit.id})
            return opts
        elif col == 23:  # Review Status
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
            return comp.fitted_status or "Fitted"
        elif col == 6:
            return comp.type or ""
        elif col == 7:
            return entry.fm_name
        elif col == 8:
            pct = comp.failure_modes.get(entry.fm_name, entry.fm_percentage)
            return pct if role == Qt.ItemDataRole.EditRole else f"{pct:.1f}%"
        elif col == 9:
            rate = comp.failure_rate or 0.0
            return rate if role == Qt.ItemDataRole.EditRole else f"{rate:.4f}"
        elif col == 10:
            return self.project.reliability_database_source or "MIL-HDBK-217F"
        elif col == 11:
            return "Section 5"
        elif col == 12:
            return self.project.environmental_profile or "Ground Benign (GB)"
        elif col == 13:
            dev_id = assignment.deviation_id
            if role == Qt.ItemDataRole.EditRole:
                return dev_id
            if dev_id:
                dev = next((d for d in self.project.deviations if d.id == dev_id), None)
                return dev.name if dev else dev_id
            return "-- None --"
        elif col == 14:
            return assignment.diagnostic_function or ""
        elif col == 15:
            classif = getattr(assignment, "classification", "not_evaluated")
            if role == Qt.ItemDataRole.EditRole:
                return classif
            return CLASSIFICATION_DISPLAY_MAP.get(classif, "Not Evaluated")
        elif col == 16:
            dp = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage is not None else 100.0
            return dp if role == Qt.ItemDataRole.EditRole else f"{dp:.1f}%"
        elif col == 17:
            dp = assignment.dangerous_failure_percentage if assignment.dangerous_failure_percentage is not None else 100.0
            safe_pct = 100.0 - dp
            return safe_pct if role == Qt.ItemDataRole.EditRole else f"{safe_pct:.1f}%"
        elif col == 18:
            dm_id = assignment.diagnostic_measure_id
            if role == Qt.ItemDataRole.EditRole:
                return dm_id
            if dm_id:
                dm = next((m for m in self.project.diagnostic_measures if m.id == dm_id), None)
                return dm.description if dm else dm_id
            return "-- None --"
        elif col == 19:
            det = assignment.detection_percentage if assignment.detection_percentage is not None else 0.0
            return det if role == Qt.ItemDataRole.EditRole else f"{det:.1f}%"
        elif col == 20:
            return ""
        elif col == 21:
            mit_id = assignment.mitigation_id
            if role == Qt.ItemDataRole.EditRole:
                return mit_id
            if mit_id:
                mit = next((m for m in self.project.mitigations if m.id == mit_id), None)
                return mit.name or mit.id if mit else mit_id
            return "-- None --"
        elif col == 22:
            return assignment.notes or ""
        elif col == 23:
            st = getattr(assignment, "review_status", "draft") or "draft"
            if role == Qt.ItemDataRole.EditRole:
                return st.lower()
            return st.title()
        elif col == 24:
            val = getattr(assignment, "proof_test_a", 0.0) or 0.0
            return val if role == Qt.ItemDataRole.EditRole else f"{val:.1f}%"
        elif col == 25:
            val = getattr(assignment, "proof_test_b", 0.0) or 0.0
            return val if role == Qt.ItemDataRole.EditRole else f"{val:.1f}%"
        elif col == 26:
            val = getattr(assignment, "proof_test_c", 0.0) or 0.0
            return val if role == Qt.ItemDataRole.EditRole else f"{val:.1f}%"
        elif col == 27:
            return ""
        elif col == 28:
            return f"{metrics.get('lambda', 0.0):.4f}"
        elif col == 29:
            return f"{metrics.get('lambda_safe', 0.0):.4f}"
        elif col == 30:
            return f"{metrics.get('lambda_dangerous', 0.0):.4f}"
        elif col == 31:
            return f"{metrics.get('lambda_sd', 0.0):.4f}"
        elif col == 32:
            return f"{metrics.get('lambda_su', 0.0):.4f}"
        elif col == 33:
            return f"{metrics.get('lambda_dd', 0.0):.4f}"
        elif col == 34:
            return f"{metrics.get('lambda_du', 0.0):.4f}"
        elif col == 35:
            return f"{metrics.get('lambda_no_part', 0.0):.4f}"
        elif col == 36:
            return f"{metrics.get('lambda_no_effect', 0.0):.4f}"
        elif col == 37:
            return f"{metrics.get('sff', 0.0):.1f}%"
        elif col == 38:
            return f"{metrics.get('dc', 0.0):.1f}%"
        elif col == 39:
            mtbf = metrics.get('mtbf', 0.0)
            return f"{mtbf:.1e}" if mtbf > 0 else "N/A"
        elif col == 40:
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

        # Handle CheckStateRole for Col 27 (DON'T CARE)
        if role == Qt.ItemDataRole.CheckStateRole and col == 27:
            is_checked = (value == Qt.CheckState.Checked or value == Qt.CheckState.Checked.value or bool(value))
            assignment.dont_care = is_checked
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        if role != Qt.ItemDataRole.EditRole:
            return False

        # Component-level text fields (col 2, 3, 4, 5) propagate to all rows for this component
        if col in (2, 3, 4, 5):
            if col == 2:
                comp.function = str(value)
            elif col == 3:
                comp.value = str(value)
            elif col == 4:
                comp.internal_pn = str(value)
            elif col == 5:
                comp.fitted_status = str(value)
                # Recompute metrics for all rows of this component
                for r_idx, r_entry in enumerate(self.rows):
                    if r_entry.component == comp:
                        self._compute_entry_metrics(r_entry)

            # Emit dataChanged for all rows of this component
            for r_idx, r_entry in enumerate(self.rows):
                if r_entry.component == comp:
                    self.dataChanged.emit(self.index(r_idx, 0), self.index(r_idx, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Failure-Mode % (col 8)
        if col == 8:
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

        # Deviation (col 13)
        if col == 13:
            assignment.deviation_id = value if value else None
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Diagnostic Function (col 14)
        if col == 14:
            assignment.diagnostic_function = str(value) if value else None
            self.dataChanged.emit(self.index(row, 14), self.index(row, 14))
            self.data_modified.emit()
            return True

        # Classification (col 15)
        if col == 15:
            class_key = CLASSIFICATION_DATA_MAP.get(value, value)
            assignment.classification = class_key
            if class_key == "safe_failure":
                assignment.dangerous_failure_percentage = 0.0
            elif class_key == "dangerous_failure":
                assignment.dangerous_failure_percentage = 100.0
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Dangerous % (col 16)
        if col == 16:
            try:
                dp = float(value)
                assignment.dangerous_failure_percentage = dp
                if dp == 0.0:
                    assignment.classification = "safe_failure"
                else:
                    assignment.classification = "dangerous_failure"
                self._compute_entry_metrics(entry)
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
                self.data_modified.emit()
                return True
            except (ValueError, TypeError):
                return False

        # Safe % (col 17)
        if col == 17:
            try:
                safe_pct = float(value)
                dp = 100.0 - safe_pct
                assignment.dangerous_failure_percentage = dp
                if dp == 0.0:
                    assignment.classification = "safe_failure"
                else:
                    assignment.classification = "dangerous_failure"
                self._compute_entry_metrics(entry)
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
                self.data_modified.emit()
                return True
            except (ValueError, TypeError):
                return False

        # Diagnostic Measure (col 18)
        if col == 18:
            dm_id = value if value else None
            assignment.diagnostic_measure_id = dm_id
            if dm_id:
                dm = next((m for m in self.project.diagnostic_measures if m.id == dm_id), None)
                if dm:
                    assignment.detection_percentage = dm.dc
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Detection % (col 19)
        if col == 19:
            try:
                det = float(value)
                assignment.detection_percentage = det
                self._compute_entry_metrics(entry)
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
                self.data_modified.emit()
                return True
            except (ValueError, TypeError):
                return False

        # Mitigation (col 21)
        if col == 21:
            assignment.mitigation_id = value if value else None
            self._compute_entry_metrics(entry)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMN_HEADERS) - 1))
            self.data_modified.emit()
            return True

        # Notes / Comments (col 22)
        if col == 22:
            assignment.notes = str(value) if value else None
            self.dataChanged.emit(self.index(row, 22), self.index(row, 22))
            self.data_modified.emit()
            return True

        # Review Status (col 23)
        if col == 23:
            assignment.review_status = str(value).lower()
            self.dataChanged.emit(self.index(row, 23), self.index(row, 23))
            self.data_modified.emit()
            return True

        # Proof Test A, B, C (col 24, 25, 26)
        if col in (24, 25, 26):
            try:
                pt_val = float(value)
                if col == 24:
                    assignment.proof_test_a = pt_val
                elif col == 25:
                    assignment.proof_test_b = pt_val
                elif col == 26:
                    assignment.proof_test_c = pt_val
                self.dataChanged.emit(self.index(row, col), self.index(row, col))
                self.data_modified.emit()
                return True
            except (ValueError, TypeError):
                return False

        return False
