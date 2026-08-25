

from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class DiagnosticMeasure(BaseModel):
    """Diagnostic measure with coverage and requirements"""
    
    # Basic identification
    id: str = Field(description="Unique diagnostic measure identifier")
    dc: float = Field(
        description="Diagnostic Coverage percentage (0-100)",
        ge=0.0,
        le=100.0
    )
    description: str = Field(description="Description of the diagnostic measure")
    
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
