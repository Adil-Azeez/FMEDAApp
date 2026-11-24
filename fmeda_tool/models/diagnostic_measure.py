

from typing import Optional
from pydantic import BaseModel, Field, model_validator, field_validator
from datetime import datetime
from uuid import uuid4

DEFAULT_SOURCE_LINK = "https://de-lx-polarion1.jumo.net/polarion/#/project/JUMO_safetyM_TB_TW/wiki/02%20Entwicklungsphase/08%20FMEDA"


class DiagnosticMeasure(BaseModel):
    """Diagnostic measure with coverage and requirements"""
    
    # Basic identification
    id: str = Field(default_factory=lambda: "dm_" + uuid4().hex, description="Internal assignment key")
    display_id: Optional[str] = None
    diagnostic_measure_test: str
    source_link: str = DEFAULT_SOURCE_LINK
    dc: Optional[float] = Field(
        default=None,
        description="Diagnostic Coverage percentage (0-100)",
        ge=0.0,
        le=100.0
    )
    description: str = Field(description="Description of the diagnostic measure")
    failure_reaction: Optional[str] = None
    execution_timing: Optional[str] = None
    verification_method: Optional[str] = None
    implementation_type: Optional[str] = None
    responsible: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def load_legacy_name(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            if "diagnostic_measure_test" not in values and ("name" in values or values.get("id")):
                values["diagnostic_measure_test"] = values.get("name", values.get("description", ""))
                values.setdefault("display_id", values.get("id") or None)
            values.pop("name", None)
            if not values.get("id"):
                values.pop("id", None)
        return values

    @field_validator("diagnostic_measure_test", "description")
    @classmethod
    def require_text(cls, value):
        if not value.strip():
            raise ValueError("This field is required.")
        return value.strip()

    @property
    def name(self):
        """Read compatibility for historical integrations; not a catalog field."""
        return self.diagnostic_measure_test

    @property
    def display_label(self):
        return f"{self.diagnostic_measure_test} | {self.description}"

    # Optional references
    risk_id: Optional[str] = Field(
        default=None,
        description="Associated risk identifier",
        alias="riskId"
    )
    sw_requirement_id: Optional[str] = Field(
        default=None,
        description="Software requirement identifier",
        alias="swRequirementId"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes or references"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    class Config:
        populate_by_name = True  # Allow using both alias and field name
        json_schema_extra = {
            "example": {
                "id": "dm_001",
                "dc": 95.0,
                "description": "Voltage monitoring circuit with ADC-based detection",
                "riskId": "risk_psu_001",
                "swRequirementId": "SWR-123"
            }
        }
