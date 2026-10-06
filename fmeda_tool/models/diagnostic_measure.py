

from typing import Optional
from pydantic import BaseModel, Field, model_validator, field_validator
from datetime import datetime


class DiagnosticMeasure(BaseModel):
    """Diagnostic measure with coverage and requirements"""
    
    # Basic identification
    id: str = Field(description="Unique diagnostic measure identifier")
    name: str = Field(description="Catalog name")
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
        if isinstance(values, dict) and "name" not in values:
            values = dict(values, name=values.get("description", ""))
        return values

    @field_validator("id", "name", "description")
    @classmethod
    def require_text(cls, value):
        if not value.strip():
            raise ValueError("This field is required.")
        return value.strip()

    @property
    def display_label(self):
        dc = f" (DC: {self.dc:.1f}%)" if self.dc is not None else ""
        return f"{self.id} — {self.name}{dc}"
    
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
