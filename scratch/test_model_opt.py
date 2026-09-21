"""
Test shared QStandardItemModel and column span optimizations on realistic project.
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
    QApplication, QTableWidget, QTableWidgetItem, QComboBox, QLineEdit,
    QDoubleSpinBox, QCheckBox, QWidget, QHBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QColor

app = QApplication.instance() or QApplication([])

from fmeda_tool.models import Project


def test_shared_models():
    test_path = "scratch/realistic_large_project.json"
    with open(test_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    project = Project.model_validate(data)
    unit = project.units[0]
    
    table = QTableWidget()
    table.setColumnCount(41)
    
    total_fm_count = sum(len(c.failure_modes) for c in unit.components)
    total_sep_count = len(unit.components) - 1
    total_rows = total_fm_count + total_sep_count
    
    print(f"Testing FG 1 ({total_rows} rows) with Shared Models and Spanned Separators...")
    
    t_start = time.perf_counter()
    table.setUpdatesEnabled(False)
    table.blockSignals(True)
    table.setRowCount(total_rows)
    
    # 1. Build shared models once
    t0 = time.perf_counter()
    dev_model = QStandardItemModel()
    dev_item_none = QStandardItem("-- None --")
    dev_item_none.setData(None, Qt.ItemDataRole.UserRole)
    dev_model.appendRow(dev_item_none)
    for dev in project.deviations:
        item = QStandardItem(dev.name)
        item.setData(dev.id, Qt.ItemDataRole.UserRole)
        dev_model.appendRow(item)
    dev_id_to_row = {dev.id: i+1 for i, dev in enumerate(project.deviations)}
    
    dm_model = QStandardItemModel()
    dm_item_none = QStandardItem("-- None --")
    dm_item_none.setData(None, Qt.ItemDataRole.UserRole)
    dm_model.appendRow(dm_item_none)
    for dm in project.diagnostic_measures:
        item = QStandardItem(dm.description)
        item.setData(dm.id, Qt.ItemDataRole.UserRole)
        dm_model.appendRow(item)
    dm_id_to_row = {dm.id: i+1 for i, dm in enumerate(project.diagnostic_measures)}
    
    mit_model = QStandardItemModel()
    mit_item_none = QStandardItem("-- None --")
    mit_item_none.setData(None, Qt.ItemDataRole.UserRole)
    mit_model.appendRow(mit_item_none)
    for mit in project.mitigations:
        item = QStandardItem(mit.name or mit.id)
        item.setData(mit.id, Qt.ItemDataRole.UserRole)
        mit_model.appendRow(item)
    mit_id_to_row = {mit.id: i+1 for i, mit in enumerate(project.mitigations)}
    
    fit_model = QStandardItemModel()
    for f in ["Fitted", "Not Fitted"]:
        fit_model.appendRow(QStandardItem(f))
        
    class_model = QStandardItemModel()
    for c in ["Not Evaluated", "Safe Failure", "Dangerous Failure"]:
        class_model.appendRow(QStandardItem(c))
        
    rev_model = QStandardItemModel()
    for r in ["Draft", "Under Review", "Approved"]:
        rev_model.appendRow(QStandardItem(r))
        
    t_models = (time.perf_counter() - t0) * 1000.0
    print(f"Shared Models Pre-generation: {t_models:.2f} ms")
    
    curr_row = 0
    is_first = True
    
    t_loop_start = time.perf_counter()
    for comp in unit.components:
        if not is_first:
            sep_item = QTableWidgetItem(f"--- Component {comp.position} ---")
            sep_item.setBackground(QColor("#f8f9fa"))
            table.setItem(curr_row, 0, sep_item)
            table.setSpan(curr_row, 0, 1, 41)
            table.setRowHeight(curr_row, 10)
            curr_row += 1
        is_first = False
        
        for fm_name, fm_pct in comp.failure_modes.items():
            assignment = next((a for a in comp.failure_mode_assignments if a.failure_mode_name == fm_name), None)
            
            # Read-only items
            table.setItem(curr_row, 0, QTableWidgetItem(comp.position))
            table.setItem(curr_row, 1, QTableWidgetItem("🟢"))
            table.setItem(curr_row, 6, QTableWidgetItem(comp.type))
            table.setItem(curr_row, 7, QTableWidgetItem(fm_name))
            table.setItem(curr_row, 8, QTableWidgetItem(f"{fm_pct:.1f}%"))
            table.setItem(curr_row, 9, QTableWidgetItem(f"{comp.failure_rate or 0.0:.4f}"))
            table.setItem(curr_row, 10, QTableWidgetItem("MIL-HDBK-217F"))
            table.setItem(curr_row, 11, QTableWidgetItem("Section 5"))
            table.setItem(curr_row, 12, QTableWidgetItem("GB"))
            for col_idx in range(28, 37):
                table.setItem(curr_row, col_idx, QTableWidgetItem("0.0000"))
            table.setItem(curr_row, 37, QTableWidgetItem("100.0%"))
            table.setItem(curr_row, 38, QTableWidgetItem("90.0%"))
            table.setItem(curr_row, 39, QTableWidgetItem("N/A"))
            table.setItem(curr_row, 40, QTableWidgetItem("N/A"))
            
            # LineEdits
            fn_edit = QLineEdit(comp.function or "")
            val_edit = QLineEdit(comp.value or "")
            pn_edit = QLineEdit(comp.internal_pn or "")
            diag_edit = QLineEdit(assignment.diagnostic_function or "")
            notes_edit = QLineEdit(assignment.notes or "")
            
            # Combos with shared models
            fit_combo = QComboBox()
            fit_combo.setModel(fit_model)
            
            dev_combo = QComboBox()
            dev_combo.setModel(dev_model)
            if assignment.deviation_id:
                dev_combo.setCurrentIndex(dev_id_to_row.get(assignment.deviation_id, 0))
                
            class_combo = QComboBox()
            class_combo.setModel(class_model)
            
            dm_combo = QComboBox()
            dm_combo.setModel(dm_model)
            if assignment.diagnostic_measure_id:
                dm_combo.setCurrentIndex(dm_id_to_row.get(assignment.diagnostic_measure_id, 0))
                
            mit_combo = QComboBox()
            mit_combo.setModel(mit_model)
            if assignment.mitigation_id:
                mit_combo.setCurrentIndex(mit_id_to_row.get(assignment.mitigation_id, 0))
                
            rev_combo = QComboBox()
            rev_combo.setModel(rev_model)
            
            # Spinboxes
            dang_spin = QDoubleSpinBox()
            safe_spin = QDoubleSpinBox()
            det_spin = QDoubleSpinBox()
            pt_a = QDoubleSpinBox()
            pt_b = QDoubleSpinBox()
            pt_c = QDoubleSpinBox()
            
            # Checkbox
            ch_w = QWidget()
            ch_l = QHBoxLayout(ch_w)
            ch_l.addWidget(QCheckBox())
            
            # setCellWidgets
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
            
            curr_row += 1
            
    table.blockSignals(False)
    table.setUpdatesEnabled(True)
    
    total_time = (time.perf_counter() - t_start) * 1000.0
    loop_time = (time.perf_counter() - t_loop_start) * 1000.0
    
    print("\n" + "="*60)
    print(f"OPTIMIZED POPULATION TIME: {total_time:.2f} ms (Loop: {loop_time:.2f} ms)")
    print("="*60)


if __name__ == "__main__":
    test_shared_models()
