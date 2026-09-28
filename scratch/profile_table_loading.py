"""
Micro-profiling script for _load_fmeda_table sub-operations.
Breaks down the 13.7-second table population into exact microsecond metrics.
"""

import sys
import os
import time
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import (
    QApplication, QTableWidget, QTableWidgetItem, QLineEdit, QComboBox,
    QDoubleSpinBox, QCheckBox, QWidget, QHBoxLayout, QHeaderView
)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor

app = QApplication.instance() or QApplication([])

from fmeda_tool.models import Project
from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.services.validation_service import ValidationService


def profile_sub_operations():
    test_path = "scratch/realistic_large_project.json"
    with open(test_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    project = Project.model_validate(data)
    unit = project.units[0]  # 165 components, ~825 rows
    
    table = QTableWidget()
    table.setColumnCount(41)
    
    total_fm_count = sum(len(c.failure_modes) for c in unit.components)
    total_sep_count = len(unit.components) - 1
    total_rows = total_fm_count + total_sep_count
    
    print(f"Profiling FG 1: {len(unit.components)} components, {total_rows} total rows...")
    
    # 1. setRowCount
    t0 = time.perf_counter()
    table.setRowCount(total_rows)
    t_set_row_count = (time.perf_counter() - t0) * 1000.0
    
    # 2. Measure component by component
    t_qtablewidgetitems = 0.0
    t_line_edits = 0.0
    t_combos_creation = 0.0
    t_combos_population = 0.0
    t_spinboxes = 0.0
    t_checkboxes = 0.0
    t_set_cell_widgets = 0.0
    t_signals = 0.0
    t_calc = 0.0
    t_validation_and_styling = 0.0
    
    curr_row = 0
    is_first = True
    
    t_loop_start = time.perf_counter()
    
    for comp in unit.components:
        if not is_first:
            for c in range(41):
                item = QTableWidgetItem("")
                table.setItem(curr_row, c, item)
            curr_row += 1
        is_first = False
        
        for fm_name, fm_pct in comp.failure_modes.items():
            assignment = next((a for a in comp.failure_mode_assignments if a.failure_mode_name == fm_name), None)
            
            # Calculation
            t_s = time.perf_counter()
            local_fit = (comp.failure_rate or 0.0) * (fm_pct / 100.0)
            classif = getattr(assignment, "classification", "not_evaluated")
            dp = getattr(assignment, "dangerous_failure_percentage", 100.0) or 100.0
            det = getattr(assignment, "detection_percentage", 0.0) or 0.0
            row_metrics = CalculationService.calculate_row_detailed(local_fit, classif, dp, det)
            t_calc += (time.perf_counter() - t_s) * 1000.0
            
            # Read-only items
            t_s = time.perf_counter()
            table.setItem(curr_row, 0, QTableWidgetItem(comp.position))
            table.setItem(curr_row, 1, QTableWidgetItem("🟢"))
            table.setItem(curr_row, 6, QTableWidgetItem(comp.type))
            table.setItem(curr_row, 7, QTableWidgetItem(fm_name))
            table.setItem(curr_row, 8, QTableWidgetItem(f"{fm_pct:.1f}%"))
            table.setItem(curr_row, 9, QTableWidgetItem(f"{comp.failure_rate or 0.0:.4f}"))
            table.setItem(curr_row, 10, QTableWidgetItem("MIL-HDBK-217F"))
            table.setItem(curr_row, 11, QTableWidgetItem("Section 5"))
            table.setItem(curr_row, 12, QTableWidgetItem("GB"))
            for c_idx, val in enumerate([
                row_metrics['lambda'], row_metrics['lambda_safe'], row_metrics['lambda_dangerous'],
                row_metrics['lambda_sd'], row_metrics['lambda_su'], row_metrics['lambda_dd'],
                row_metrics['lambda_du'], row_metrics['lambda_no_part'], row_metrics['lambda_no_effect']
            ], start=28):
                table.setItem(curr_row, c_idx, QTableWidgetItem(f"{val:.4f}"))
            table.setItem(curr_row, 37, QTableWidgetItem(f"{row_metrics['sff']:.1f}%"))
            table.setItem(curr_row, 38, QTableWidgetItem(f"{row_metrics['dc']:.1f}%"))
            table.setItem(curr_row, 39, QTableWidgetItem("N/A"))
            table.setItem(curr_row, 40, QTableWidgetItem("N/A"))
            t_qtablewidgetitems += (time.perf_counter() - t_s) * 1000.0
            
            # Line edits (5)
            t_s = time.perf_counter()
            fn_edit = QLineEdit(comp.function or "")
            val_edit = QLineEdit(comp.value or "")
            pn_edit = QLineEdit(comp.internal_pn or "")
            diag_edit = QLineEdit(assignment.diagnostic_function or "")
            notes_edit = QLineEdit(assignment.notes or "")
            t_line_edits += (time.perf_counter() - t_s) * 1000.0
            
            # Combos (6) creation + population
            t_s = time.perf_counter()
            fit_combo = QComboBox()
            fit_combo.addItems(["Fitted", "Not Fitted"])
            
            dev_combo = QComboBox()
            dev_combo.addItem("-- None --", None)
            for dev in project.deviations:
                dev_combo.addItem(dev.name, dev.id)
                
            class_combo = QComboBox()
            class_combo.addItems(["Not Evaluated", "Safe Failure", "Dangerous Failure"])
            
            dm_combo = QComboBox()
            dm_combo.addItem("-- None --", None)
            for dm in project.diagnostic_measures:
                dm_combo.addItem(dm.description, dm.id)
                
            mit_combo = QComboBox()
            mit_combo.addItem("-- None --", None)
            for mit in project.mitigations:
                mit_combo.addItem(mit.name or mit.id, mit.id)
                
            rev_combo = QComboBox()
            rev_combo.addItems(["Draft", "Under Review", "Approved"])
            t_combos_creation += (time.perf_counter() - t_s) * 1000.0
            
            # Spinboxes (6)
            t_s = time.perf_counter()
            dang_spin = QDoubleSpinBox()
            dang_spin.setRange(0, 100)
            safe_spin = QDoubleSpinBox()
            safe_spin.setRange(0, 100)
            det_spin = QDoubleSpinBox()
            det_spin.setRange(0, 100)
            pt_a = QDoubleSpinBox()
            pt_b = QDoubleSpinBox()
            pt_c = QDoubleSpinBox()
            t_spinboxes += (time.perf_counter() - t_s) * 1000.0
            
            # Checkbox (1)
            t_s = time.perf_counter()
            dc_check = QCheckBox()
            ch_w = QWidget()
            ch_l = QHBoxLayout(ch_w)
            ch_l.addWidget(dc_check)
            t_checkboxes += (time.perf_counter() - t_s) * 1000.0
            
            # Signals
            t_s = time.perf_counter()
            fn_edit.textChanged.connect(lambda txt: None)
            val_edit.textChanged.connect(lambda txt: None)
            pn_edit.textChanged.connect(lambda txt: None)
            fit_combo.currentTextChanged.connect(lambda txt: None)
            dev_combo.currentIndexChanged.connect(lambda idx: None)
            diag_edit.textChanged.connect(lambda txt: None)
            class_combo.currentTextChanged.connect(lambda txt: None)
            dang_spin.valueChanged.connect(lambda val: None)
            safe_spin.valueChanged.connect(lambda val: None)
            dm_combo.currentIndexChanged.connect(lambda idx: None)
            det_spin.valueChanged.connect(lambda val: None)
            mit_combo.currentIndexChanged.connect(lambda idx: None)
            notes_edit.textChanged.connect(lambda txt: None)
            rev_combo.currentTextChanged.connect(lambda txt: None)
            pt_a.valueChanged.connect(lambda val: None)
            pt_b.valueChanged.connect(lambda val: None)
            pt_c.valueChanged.connect(lambda val: None)
            dc_check.stateChanged.connect(lambda st: None)
            t_signals += (time.perf_counter() - t_s) * 1000.0
            
            # setCellWidget (18 calls!)
            t_s = time.perf_counter()
            table.setCellWidget(curr_row, 2, fn_edit)
            table.setCellWidget(curr_row, 3, val_edit)
            table.setCellWidget(curr_row, 4, pn_edit)
            table.setCellWidget(curr_row, 5, fit_combo)
            table.setCellWidget(curr_row, 13, dev_combo)
            table.setCellWidget(curr_row, 14, diag_edit)
            table.setCellWidget(curr_row, 15, class_combo)
            table.setCellWidget(curr_row, 16, dang_spin)
            table.setCellWidget(curr_row, 17, safe_spin)
            table.setCellWidget(curr_row, 18, dm_combo)
            table.setCellWidget(curr_row, 19, det_spin)
            table.setCellWidget(curr_row, 21, mit_combo)
            table.setCellWidget(curr_row, 22, notes_edit)
            table.setCellWidget(curr_row, 23, rev_combo)
            table.setCellWidget(curr_row, 24, pt_a)
            table.setCellWidget(curr_row, 25, pt_b)
            table.setCellWidget(curr_row, 26, pt_c)
            table.setCellWidget(curr_row, 27, ch_w)
            t_set_cell_widgets += (time.perf_counter() - t_s) * 1000.0
            
            # Styling & validation
            t_s = time.perf_counter()
            status, msgs = ValidationService.validate_row(assignment, comp)
            bg = QColor("#ffffff")
            for col in range(13):
                it = table.item(curr_row, col)
                if it:
                    it.setBackground(bg)
            t_validation_and_styling += (time.perf_counter() - t_s) * 1000.0
            
            curr_row += 1
            
    total_loop_time = (time.perf_counter() - t_loop_start) * 1000.0
    
    print("\n" + "="*60)
    print("SUB-OPERATION PROFILING RESULTS:")
    print("="*60)
    print(f"  setRowCount ({total_rows} rows)            : {t_set_row_count:>8.2f} ms")
    print(f"  QTableWidgetItem creation (41 cols)       : {t_qtablewidgetitems:>8.2f} ms")
    print(f"  Row calculation detailed                  : {t_calc:>8.2f} ms")
    print(f"  QLineEdit widget creation (5/row)         : {t_line_edits:>8.2f} ms")
    print(f"  QComboBox creation & item populate (6/row): {t_combos_creation:>8.2f} ms")
    print(f"  QDoubleSpinBox creation (6/row)           : {t_spinboxes:>8.2f} ms")
    print(f"  QCheckBox & QWidget container (1/row)     : {t_checkboxes:>8.2f} ms")
    print(f"  Signal connections (18/row)               : {t_signals:>8.2f} ms")
    print(f"  setCellWidget (18 calls/row)              : {t_set_cell_widgets:>8.2f} ms")
    print(f"  Validation & cell background styling      : {t_validation_and_styling:>8.2f} ms")
    print(f"  TOTAL POPULATION LOOP                     : {total_loop_time:>8.2f} ms")
    print("="*60)


if __name__ == "__main__":
    profile_sub_operations()
