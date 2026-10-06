from fmeda_tool.ui.widgets.deviation_selector import DeviationSelector


class DiagnosticMeasureSelector(DeviationSelector):
    """Use the existing catalog search interaction for diagnostic assignment."""

    def __init__(self, options, parent=None):
        super().__init__(options, parent)
        self.lineEdit().setPlaceholderText(
            "Search ID, name, description, verification, timing or notes..."
        )
