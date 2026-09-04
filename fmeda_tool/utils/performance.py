"""
Performance instrumentation, granular phase timing, call counters, and reconciliation tracking for FMEDA Tool.
Measures every stage of project loading and table rendering to guarantee complete timing accountability.
"""

import time
import logging
import tracemalloc
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field

# Configure logger for performance metrics
logger = logging.getLogger("fmeda_tool.performance")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / "fmeda_performance.log"
    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


@dataclass
class CallCounters:
    """Explicit invocation counters during a project load operation."""
    load_project_count: int = 0
    functional_group_editor_creation_count: int = 0
    full_table_refresh_count: int = 0
    row_refresh_count: int = 0
    calculate_project_count: int = 0
    validate_project_count: int = 0
    resize_columns_to_contents_count: int = 0
    resize_rows_to_contents_count: int = 0
    set_cell_widget_total: int = 0
    set_cell_widget_line_edit: int = 0
    set_cell_widget_combo_box: int = 0
    set_cell_widget_double_spin_box: int = 0
    set_cell_widget_checkbox: int = 0
    set_cell_widget_other: int = 0
    insert_row_count: int = 0
    set_row_count_count: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "load_project_count": self.load_project_count,
            "functional_group_editor_creation_count": self.functional_group_editor_creation_count,
            "full_table_refresh_count": self.full_table_refresh_count,
            "row_refresh_count": self.row_refresh_count,
            "calculate_project_count": self.calculate_project_count,
            "validate_project_count": self.validate_project_count,
            "resize_columns_to_contents_count": self.resize_columns_to_contents_count,
            "resize_rows_to_contents_count": self.resize_rows_to_contents_count,
            "set_cell_widget_total": self.set_cell_widget_total,
            "set_cell_widget_line_edit": self.set_cell_widget_line_edit,
            "set_cell_widget_combo_box": self.set_cell_widget_combo_box,
            "set_cell_widget_double_spin_box": self.set_cell_widget_double_spin_box,
            "set_cell_widget_checkbox": self.set_cell_widget_checkbox,
            "set_cell_widget_other": self.set_cell_widget_other,
            "insert_row_count": self.insert_row_count,
            "set_row_count_count": self.set_row_count_count
        }


@dataclass
class LazyLoadLogEntry:
    """Log entry for functional group tab lifecycle and population."""
    unit_id: str
    unit_name: str
    action: str  # "tab_header_created", "editor_created", "table_populated"
    row_count: int = 0
    duration_ms: float = 0.0
    reason: str = "initial"  # "initial", "selected", "dirty_refresh", "manual"
    timestamp: float = field(default_factory=time.perf_counter)


class PerformanceTimer:
    """
    Granular timer and profiler to measure the complete project load timeline,
    call counters, lazy loading events, and reconciliation check.
    """
    
    def __init__(self, operation_name: str = "Project Operation"):
        self.operation_name = operation_name
        self.timings: Dict[str, float] = {}
        self.metrics: Dict[str, Any] = {}
        self.counters = CallCounters()
        self.lazy_logs: List[LazyLoadLogEntry] = []
        
        self._active_timers: Dict[str, float] = {}
        self._start_total: float = time.perf_counter()
        self._last_phase_end: float = self._start_total
        self._last_phase_name: str = "init"
        self._tracemalloc_started: bool = False
        
        try:
            if not tracemalloc.is_tracing():
                tracemalloc.start()
                self._tracemalloc_started = True
        except Exception:
            pass

    def start_phase(self, phase_name: str, start_time: Optional[float] = None) -> None:
        """Starts timing a named phase."""
        t_now = start_time if start_time is not None else time.perf_counter()
        self._active_timers[phase_name] = t_now

    def end_phase(self, phase_name: str) -> float:
        """Ends timing for a phase and accumulates elapsed milliseconds."""
        end_time = time.perf_counter()
        start_time = self._active_timers.pop(phase_name, None)
        if start_time is None:
            return 0.0
        elapsed_ms = (end_time - start_time) * 1000.0
        self.timings[phase_name] = self.timings.get(phase_name, 0.0) + elapsed_ms
        self._last_phase_end = end_time
        self._last_phase_name = phase_name
        return elapsed_ms

    def add_phase_time(self, phase_name: str, elapsed_ms: float) -> None:
        """Accumulates elapsed time in milliseconds directly to a phase."""
        self.timings[phase_name] = self.timings.get(phase_name, 0.0) + elapsed_ms

    def record_metric(self, metric_name: str, value: Any) -> None:
        """Records a metric value."""
        self.metrics[metric_name] = value

    def log_lazy_event(
        self,
        unit_id: str,
        unit_name: str,
        action: str,
        row_count: int = 0,
        duration_ms: float = 0.0,
        reason: str = "initial"
    ) -> None:
        """Records a lazy loading lifecycle event for a functional group."""
        entry = LazyLoadLogEntry(
            unit_id=unit_id,
            unit_name=unit_name,
            action=action,
            row_count=row_count,
            duration_ms=duration_ms,
            reason=reason
        )
        self.lazy_logs.append(entry)

    def record_project_metrics(self, project: Any, file_size_bytes: int = 0) -> None:
        """Extracts structural project metrics."""
        if file_size_bytes > 0:
            self.metrics["file_size_bytes"] = file_size_bytes
            self.metrics["file_size_mb"] = round(file_size_bytes / (1024 * 1024), 3)
            
        if project:
            num_units = len(project.units) if hasattr(project, "units") and project.units else 0
            num_comps = sum(len(u.components) for u in project.units) if num_units else 0
            num_fma = sum(
                len(c.failure_mode_assignments)
                for u in project.units
                for c in u.components
            ) if num_units else 0
            
            total_rows = 0
            max_rows_in_group = 0
            for u in project.units:
                group_rows = sum(len(c.failure_modes) for c in u.components)
                if len(u.components) > 1:
                    group_rows += len(u.components) - 1
                total_rows += group_rows
                if group_rows > max_rows_in_group:
                    max_rows_in_group = group_rows
                    
            self.metrics["functional_groups_count"] = num_units
            self.metrics["components_count"] = num_comps
            self.metrics["failure_mode_assignments_count"] = num_fma
            self.metrics["total_fmeda_table_rows"] = total_rows
            self.metrics["max_rows_in_single_group"] = max_rows_in_group

    def finish(self) -> Dict[str, Any]:
        """
        Finalizes total elapsed duration, performs reconciliation check,
        verifies that >= 95% of time is accounted for, and outputs structured log.
        """
        total_time_ms = (time.perf_counter() - self._start_total) * 1000.0
        self.timings["total_project_open"] = total_time_ms
        
        # Calculate sum of discrete named sub-phases
        # (Exclude top-level container phases to avoid double-counting)
        container_phases = {
            "total_project_open",
            "uniteditorview_load_project",
            "active_functional_group_population",
            "every_call_to_populate_or_refresh_table"
        }
        
        discrete_sum = sum(
            ms for phase, ms in self.timings.items()
            if phase not in container_phases and not phase.startswith("_")
        )
        
        # If discrete sub-phases were measured, reconcile against total_project_open
        unaccounted_ms = max(0.0, total_time_ms - discrete_sum)
        unaccounted_pct = (unaccounted_ms / total_time_ms * 100.0) if total_time_ms > 0 else 0.0
        
        self.metrics["accounted_phases_sum_ms"] = round(discrete_sum, 2)
        self.metrics["unaccounted_time_ms"] = round(unaccounted_ms, 2)
        self.metrics["unaccounted_time_pct"] = round(unaccounted_pct, 2)
        self.metrics["reconciliation_pass"] = (unaccounted_pct <= 5.0)
        
        # Memory tracking
        try:
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                self.metrics["peak_memory_mb"] = round(peak / (1024 * 1024), 2)
                self.metrics["current_memory_mb"] = round(current / (1024 * 1024), 2)
                if self._tracemalloc_started:
                    tracemalloc.stop()
        except Exception:
            self.metrics["peak_memory_mb"] = "N/A"
            
        summary = {
            "operation": self.operation_name,
            "timings_ms": self.timings,
            "metrics": self.metrics,
            "counters": self.counters.to_dict(),
            "lazy_events": [
                {
                    "unit": e.unit_name,
                    "action": e.action,
                    "rows": e.row_count,
                    "ms": round(e.duration_ms, 2),
                    "reason": e.reason
                }
                for e in self.lazy_logs
            ],
            "total_ms": round(total_time_ms, 2)
        }
        
        # Format detailed log
        log_lines = [
            f"=== Granular Performance Report: {self.operation_name} ===",
            f"Total Duration: {total_time_ms:.2f} ms",
            "Named Phase Timings (ms):"
        ]
        for phase, ms in sorted(self.timings.items(), key=lambda x: x[1], reverse=True):
            pct = (ms / total_time_ms * 100.0) if total_time_ms > 0 else 0.0
            log_lines.append(f"  - {phase}: {ms:.2f} ms ({pct:.1f}%)")
            
        log_lines.append(f"Reconciliation: Accounted {discrete_sum:.2f} ms ({100.0-unaccounted_pct:.1f}%) | Unaccounted {unaccounted_ms:.2f} ms ({unaccounted_pct:.1f}%)")
        
        if unaccounted_pct > 5.0:
            log_lines.append(f"⚠️ UNACCOUNTED_LOAD_TIME: {unaccounted_ms:.2f} ms ({unaccounted_pct:.1f}%) [Surrounding: {self._last_phase_name}]")
            
        log_lines.append("Call Counters:")
        for k, v in self.counters.to_dict().items():
            log_lines.append(f"  - {k}: {v}")
            
        log_lines.append("Lazy Loading Events:")
        for e in self.lazy_logs:
            log_lines.append(f"  - [{e.action}] Unit: '{e.unit_name}' ({e.unit_id}) | Rows: {e.row_count} | Duration: {e.duration_ms:.2f} ms | Reason: {e.reason}")
            
        log_lines.append("Project Metrics:")
        for metric, val in self.metrics.items():
            log_lines.append(f"  - {metric}: {val}")
        log_lines.append("=" * 60)
        
        report_text = "\n".join(log_lines)
        logger.info(report_text)
        return summary
