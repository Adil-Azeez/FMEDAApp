

from typing import Optional
from pydantic import BaseModel, Field, model_validator

CLASSIFICATIONS = {
    "not_evaluated": "Not Evaluated",
    "safe_failure": "Safe Failure",
    "dangerous_failure": "Dangerous Failure",
    "no_part_failure": "No Part Failure",
    "no_effect_failure": "No Effect Failure",
    "diagnostic_function_failure": "Diagnostic Function Failure",
}
LEGACY_CLASSIFICATION = "legacy_no_part_no_effect"
CLASSIFICATION_LABELS = {**CLASSIFICATIONS, LEGACY_CLASSIFICATION:
    "Legacy No Part / No Effect — Classification Review Required"}


class FailureModeAssignment(BaseModel):
    """Assignment of a failure mode to deviations and diagnostic measures"""
    
    # Failure mode information (from ComponentDB)
    failure_mode_name: str = Field(description="Name of the failure mode")
    failure_rate_percentage: float = Field(
        description="Percentage of overall FITS for this failure mode",
        ge=0.0,
        le=100.0
    )
    
    # Assignments
    deviation_id: Optional[str] = Field(
        default=None,
        description="ID of the deviation this failure mode causes"
    )
    diagnostic_measure_id: Optional[str] = Field(
        default=None,
        description="ID of the diagnostic measure used to detect this failure"
    )
    detection_percentage: Optional[float] = Field(
        default=None,
        description="Percentage of detection (0-100)",
        ge=0.0,
        le=100.0
    )
    dangerous_failure_percentage: Optional[float] = Field(
        default=None,
        description="Percentage indicating how dangerous this failure is (0-100)",
        ge=0.0,
        le=100.0
    )
    secondary_failure_component_id: Optional[str] = Field(
        default=None,
        description="ID of another component where secondary failure can occur"
    )
    classification: Optional[str] = Field(
        default="not_evaluated",
        description="Failure classification (safe, dangerous, etc.)"
    )
    classification_version: int = 2
    legacy_classification: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_classification(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            classification = str(values.get("classification") or "not_evaluated").strip()
            aliases = {label.casefold(): key for key, label in CLASSIFICATIONS.items()}
            aliases.update(safe="safe_failure", dangerous="dangerous_failure")
            classification = aliases.get(classification.casefold(), classification)
            if classification not in CLASSIFICATION_LABELS:
                values.setdefault("legacy_classification", classification)
                classification = "not_evaluated"
            if values.get("dont_care") and values.get("classification_version", 1) == 1 and classification in ("not_evaluated", "safe_failure", "dangerous_failure"):
                values.setdefault("legacy_classification", classification)
                classification = LEGACY_CLASSIFICATION
                values["classification_version"] = 1
            values["classification"] = classification
        return values

    def set_classification(self, classification: str) -> None:
        """Explicit engineering decision; the historical compatibility flag is retained."""
        if classification not in CLASSIFICATIONS:
            raise ValueError("Unknown failure classification.")
        if self.classification == LEGACY_CLASSIFICATION and classification not in ("no_part_failure", "no_effect_failure"):
            raise ValueError("Classification Review Required: select No Part Failure or No Effect Failure.")
        self.classification = classification
        self.classification_version = 2
        if classification in ("safe_failure", "dangerous_failure"):
            self.dangerous_failure_percentage = 100.0 if classification == "dangerous_failure" else 0.0
    diagnostic_function: Optional[str] = Field(
        default=None,
        description="Explicit diagnostic function evaluation: Yes, No, or blank"
    )
    legacy_diagnostic_function: Optional[str] = Field(
        default=None, description="Unrecognized legacy diagnostic text retained for reference"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_diagnostic_function(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            raw = values.get("diagnostic_function")
            text = str(raw).strip() if raw is not None else ""
            normalized = {"yes": "Yes", "y": "Yes", "true": "Yes", "1": "Yes",
                          "no": "No", "n": "No", "false": "No", "0": "No"}.get(text.casefold())
            if text and normalized is None:
                values.setdefault("legacy_diagnostic_function", text)
            values["diagnostic_function"] = normalized
        return values
    dc_test_ref: Optional[str] = Field(
        default=None,
        description="Diagnostic coverage test reference"
    )
    mitigation_id: Optional[str] = Field(
        default=None,
        description="Mitigation ID assigned to this row"
    )
    review_status: Optional[str] = Field(
        default="draft",
        description="Review status of this row"
    )
    proof_test_a: Optional[float] = Field(
        default=0.0,
        description="Proof test A coverage %",
        ge=0.0,
        le=100.0
    )
    proof_test_b: Optional[float] = Field(
        default=0.0,
        description="Proof test B coverage %",
        ge=0.0,
        le=100.0
    )
    proof_test_c: Optional[float] = Field(
        default=0.0,
        description="Proof test C coverage %",
        ge=0.0,
        le=100.0
    )
    dont_care: Optional[bool] = Field(
        default=False,
        description="Don't Care / No Part / No Effect flag"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Engineering notes or justification comments"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "failure_mode_name": "Short Circuit",
                "failure_rate_percentage": 40.0,
                "deviation_id": "dev_001",
                "diagnostic_measure_id": "dm_001",
                "detection_percentage": 95.0,
                "dangerous_failure_percentage": 75.0,
                "secondary_failure_component_id": "comp_002"
            }
        }
