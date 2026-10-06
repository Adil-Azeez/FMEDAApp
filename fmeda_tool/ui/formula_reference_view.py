"""Read-only documentation of CalculationService; no project or calculation calls.

The source links resolve to the live service methods. The reference's calculation
fingerprints in test_formula_reference.py require review when those methods change.
"""
from dataclasses import dataclass
from html import escape
import inspect

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextOption
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QTextBrowser, QFrame, QDialog,
    QDialogButtonBox, QPlainTextEdit, QLabel,
)

from fmeda_tool.services.calculation_service import CalculationService
from fmeda_tool.ui.widgets.workflow_header import WorkflowPageHeader


@dataclass(frozen=True)
class Formula:
    key: str
    name: str
    expression: str
    explanation: str
    methods: tuple[str, ...]


def rate(suffix):
    return f"λ<sub>{suffix}</sub>"


ROW = "calculate_row_detailed"
SCOPE = "calculate_scope"
UNIT = "calculate_unit"
COMPONENT = "calculate_component"
UNIT_METRICS = "calculate_unit_metrics"

FORMULA_SECTIONS = (
    ("Failure Rates", (
        Formula("lambda_row", "Failure-mode rate (λrow)",
                f"{rate('row')} = {rate('component')} × p<sub>FM</sub> / 100",
                "Allocates the component failure rate to one failure mode using its percentage in the component's failure-mode distribution.",
                (COMPONENT,)),
        Formula("lambda_total", "Total failure rate (λtotal)",
                f"{rate('total')} = Σ {rate('row')}",
                "Sum of assigned failure-mode rates in the chosen scope, accumulated through components and functional groups. Percentages are not averaged.",
                (COMPONENT, UNIT, SCOPE)),
        Formula("lambda_safe", "Safe failure rate (λsafe)",
                f"{rate('safe,row')} = {rate('row')} × (100 − p<sub>D</sub>) / 100",
                "Safe share of each row. Scope totals sum these row rates.", (ROW, COMPONENT)),
        Formula("lambda_dangerous", "Dangerous failure rate (λdangerous)",
                f"{rate('dangerous,row')} = {rate('row')} × p<sub>D</sub> / 100",
                "Dangerous share of each row. The numerical split uses Dangerous %, not the classification label.", (ROW, COMPONENT)),
    )),
    ("Safety Channel", (
        Formula("lambda_sd", "Safe detected failure rate (λsd)",
                f"{rate('sd,row')} = {rate('safe,row')} × p<sub>DC</sub> / 100",
                "Detected portion of safe failures. Safety-channel totals sum the included rows.", (ROW, COMPONENT, SCOPE)),
        Formula("lambda_su", "Safe undetected failure rate (λsu)",
                f"{rate('su,row')} = {rate('safe,row')} × (1 − p<sub>DC</sub> / 100)",
                "Undetected portion of safe failures.", (ROW,)),
        Formula("lambda_dd", "Dangerous detected failure rate (λdd)",
                f"{rate('dd,row')} = {rate('dangerous,row')} × p<sub>DC</sub> / 100",
                "Detected portion of dangerous failures.", (ROW,)),
        Formula("lambda_du", "Dangerous undetected failure rate (λdu)",
                f"{rate('du,row')} = {rate('dangerous,row')} × (1 − p<sub>DC</sub> / 100)",
                "Undetected portion of dangerous failures.", (ROW,)),
    )),
    ("Diagnostic Metrics", (
        Formula("lambda_diag_gesamt", "Diagnostic-function failure rate (λDiagGesamt)",
                f"{rate('DiagGesamt')} = Σ {rate('row')}<br>"
                "Summation condition: Diagnostic Function = Yes",
                "Sums the full failure-mode rate for explicit Yes assignments across the selected groups. Independent of classification, detection percentage, No Part / No Effect, and group safety-function inclusion.",
                ("calculate_diagnostic_lambda", UNIT, SCOPE)),
    )),
    ("Safety Metrics", (
        Formula("sff", "Safe Failure Fraction (SFF)",
                f"SFF<sub>safety</sub> = 100 × ({rate('sd')} + {rate('su')} + {rate('dd')}) / "
                f"({rate('sd')} + {rate('su')} + {rate('dd')} + {rate('du')})<br>"
                f"SFF<sub>device</sub> = 100 × ({rate('safe')} + {rate('dd')}) / {rate('total')}<br>"
                f"SFF<sub>row</sub> = 100 × ({rate('safe,row')} + {rate('dd,row')}) / {rate('row')}",
                "Share of safe or dangerous detected failures, in percent. Scope results are unavailable for non-positive denominators; row and unit calculations return 0 in that case.",
                (ROW, UNIT, SCOPE)),
        Formula("dc", "Diagnostic Coverage (DC)",
                f"DC<sub>safety</sub> = 100 × {rate('dd')} / ({rate('dd')} + {rate('du')})<br>"
                f"DC<sub>device</sub> = 100 × {rate('dd')} / {rate('dangerous')}<br>"
                "DC<sub>row</sub> = p<sub>DC</sub>",
                "Detected share of dangerous failures, in percent. Scope results are unavailable for non-positive denominators; unit calculations return 0. Row DC is the entered Detection %, even when the dangerous rate is zero.",
                (ROW, UNIT, SCOPE)),
        Formula("mttfd", "Mean Time to Dangerous Failure (MTTFd)",
                f"MTTFd<sub>safety</sub> [years] = 10<sup>9</sup> / (({rate('dd')} + {rate('du')}) × 8760)<br>"
                f"MTTFd<sub>row</sub> [years] = (1 / ({rate('du,row')} × 10<sup>−9</sup>)) / 8760",
                "The safety-scope calculation uses all dangerous failures; the row calculation uses dangerous undetected failures. Scope results are unavailable when the rate is non-positive; the row calculation returns 0 (shown as N/A in the table).",
                (SCOPE, ROW)),
        Formula("sil", "Achieved SIL (application SFF mapping)",
                "SFF &lt; 60% → SIL 0<br>60% ≤ SFF &lt; 90% → SIL 1<br>"
                "90% ≤ SFF &lt; 99% → SIL 2<br>SFF ≥ 99% → SIL 3",
                "Uses safety-channel SFF. If SFF is unavailable, a nonempty selection with zero safety-channel rate returns SIL 0; otherwise N/A. This is the application's implemented mapping.",
                (SCOPE,)),
    )),
    ("Reliability Metrics", (
        Formula("units", "Rate and interval units",
                f"{rate('du,h')} = {rate('du')} × 10<sup>−9</sup><br>"
                f"{rate('dd,h')} = {rate('dd')} × 10<sup>−9</sup>",
                "Converts FIT to failures per hour. Tproof and Tdiag are project intervals in hours; when absent, the service uses 8760 h and 8 h respectively. Explicit zero intervals are retained.",
                (SCOPE,)),
        Formula("pfd_avg", "Average Probability of Failure on Demand (PFDavg)",
                f"1oo1, 1oo1D, Other: PFDavg = {rate('du,h')} × T<sub>proof</sub> / 2 + {rate('dd,h')} × T<sub>diag</sub><br>"
                f"1oo2: PFDavg = ({rate('du,h')}<sup>2</sup> × T<sub>proof</sub><sup>2</sup>) / 3<br>"
                f"2oo2: PFDavg = {rate('du,h')} × T<sub>proof</sub>",
                "Dimensionless result using safety-channel rates and the selected architecture. Missing architecture uses 1oo1; other architecture values use the first branch.",
                (SCOPE,)),
        Formula("pfhd", "Dangerous Failure Frequency (PFHd)",
                f"1oo1, 1oo1D, Other, 1oo2: PFHd = {rate('du,h')}<br>"
                f"2oo2: PFHd = 2 × {rate('du,h')}",
                "Dangerous failure frequency per hour. Returned under the legacy result key pfd_max and displayed as PFHd.",
                (SCOPE,)),
        Formula("mtbf", "Mean Time Between Failures (MTBF)",
                f"MTBF<sub>row</sub> [h] = 1 / ({rate('row')} × 10<sup>−9</sup>)<br>"
                f"MTBF<sub>group,device</sub> [years] = 10<sup>9</sup> / ({rate('total,device')} × 8760)",
                "Reciprocal of the total rate. A non-positive rate gives 0 for the row (displayed as N/A), or an unavailable functional-group result.",
                (ROW, UNIT_METRICS)),
        Formula("proof_coverage", "Proof-test coverage (A, B, C)",
                f"Coverage<sub>X</sub> [%] = 100 × Σ ({rate('du,row')} × p<sub>X,row</sub> / 100) / Σ {rate('du,row')}<br>"
                "X = A, B or C",
                "Dangerous-undetected-rate-weighted coverage across all assigned rows in a functional group, including No Part / No Effect rows. Unavailable when the summed rate is non-positive.",
                (UNIT_METRICS,)),
    )),
)


def reference_html():
    parts = ["""<html><head><style>
        body { font-family: 'Segoe UI', sans-serif; color: #243247; }
        h2 { color: #155a91; margin-top: 28px; margin-bottom: 14px; }
        h3 { margin-top: 22px; margin-bottom: 8px; }
        p { margin-top: 8px; margin-bottom: 12px; }
        a { color: #176bb0; }
        </style></head><body>
        <p>Formulas used by the application's CalculationService. Rates are in FIT
        (failures per 10<sup>9</sup> hours) unless marked otherwise.</p>
        <p><b>Notation:</b> p<sub>FM</sub> is the failure-mode percentage,
        p<sub>D</sub> is Dangerous %, and p<sub>DC</sub> is Detection %.
        Missing Dangerous % defaults to 100; missing Detection % defaults to 0.</p>
        <p><b>Scope:</b> Overall device (Gesamtgerät) includes assigned rows in all
        selected groups. Safety channel (Sicherheitskanal) excludes No Part / No Effect
        rows and, at scope level, groups not included in the safety function.
        Mapping templates are excluded throughout. Scope percentages are calculated
        from summed rates.</p>"""]
    for section, formulas in FORMULA_SECTIONS:
        parts.append(f"<h2>{escape(section)}</h2><hr>")
        for formula in formulas:
            parts.append(f'<h3 id="{formula.key}">{escape(formula.name)}</h3>')
            parts.append(f'<p style="font-size: 14pt; color: #133c60;">{formula.expression}</p>')
            parts.append(f"<p>{escape(formula.explanation)}</p>")
            links = " · ".join(f'<a href="source:{method}">{method}</a>' for method in formula.methods)
            parts.append(f'<p style="font-size: 10pt;">Implementation: {links}</p>')
    parts.append("</body></html>")
    return "".join(parts)


class FormulaReferenceView(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = WorkflowPageHeader("Formula Reference")
        self.back_btn = QPushButton("Back")
        self.back_btn.setToolTip("Return to Page 2: FMEDA Analysis")
        self.back_btn.clicked.connect(self.back_requested.emit)
        header.left_layout.addWidget(self.back_btn)
        layout.addWidget(header)
        self.browser = QTextBrowser()
        self.browser.setReadOnly(True)
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setFrameShape(QFrame.Shape.NoFrame)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.browser.setFont(QFont("Segoe UI", 11))
        self.browser.document().setDocumentMargin(28)
        self.browser.setHtml(reference_html())
        self.browser.anchorClicked.connect(self._show_implementation)
        layout.addWidget(self.browser, 1)

    def _show_implementation(self, url):
        allowed = {method for _, formulas in FORMULA_SECTIONS for formula in formulas for method in formula.methods}
        method_name = url.path()
        if url.scheme() != "source" or method_name not in allowed:
            return
        method = getattr(CalculationService, method_name)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"CalculationService.{method_name}")
        dialog.resize(900, 600)
        layout = QVBoxLayout(dialog)
        location = QLabel(f"fmeda_tool/services/calculation_service.py — {method_name}")
        location.setWordWrap(True)
        layout.addWidget(location)
        source = QPlainTextEdit()
        source.setReadOnly(True)
        source.setFont(QFont("Consolas", 10))
        source.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        try:
            source.setPlainText(inspect.getsource(method))
        except (OSError, TypeError):
            source.setPlainText("Source text is unavailable in this packaged installation.\n"
                                f"Implementation: CalculationService.{method_name}")
        layout.addWidget(source)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
