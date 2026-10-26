"""Review a proposed library change before changing any project object."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QFormLayout, QComboBox,
    QDialogButtonBox,
)
from fmeda_tool.services.component_remapping_service import ComponentRemappingService


class RemappingReviewDialog(QDialog):
    def __init__(self, component, template, bom, profile, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Review Remapping — {component.position}")
        self.resize(620, 520)
        self.inputs = component, template, bom, profile, project
        self.plan = ComponentRemappingService.plan(*self.inputs)
        layout = QVBoxLayout(self)
        title = QLabel(f"{component.position}: {component.name} → {template.display_name}")
        title.setWordWrap(True)
        layout.addWidget(title)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        layout.addWidget(self.summary)
        form = QFormLayout()
        self.choices = {}
        # Only unmatched modes need an explicit choice; stable matches take precedence.
        for name in template.failure_modes:
            if name in self.plan.matches:
                continue
            combo = QComboBox()
            combo.addItem("New assessment (retain unmatched history for review)", None)
            for old in self.plan.component.remapping_review_assignments:
                combo.addItem(f"{old.failure_mode_name} [{old.assignment_id}]", old.assignment_id)
            combo.currentIndexChanged.connect(self._update_plan)
            form.addRow(name, combo)
            self.choices[name] = combo
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText("Apply Remapping")
        self.apply_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_plan()

    def _update_plan(self, *_):
        try:
            choices = {name: combo.currentData() for name, combo in self.choices.items() if combo.currentData()}
            self.plan = ComponentRemappingService.plan(*self.inputs, explicit_matches=choices)
            self.summary.setPlainText(self.plan.summary())
            self.apply_button.setEnabled(True)
        except ValueError as error:
            self.summary.setPlainText(str(error))
            self.apply_button.setEnabled(False)
