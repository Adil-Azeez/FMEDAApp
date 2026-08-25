

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class MitigationType(str, Enum):
    """Types of mitigation measures"""
    REDUNDANCY = "redundancy"
    DIAGNOSTIC = "diagnostic"
    PROTECTIVE_CIRCUIT = "protective_circuit"
    SOFTWARE_CHECK = "software_check"
    DESIGN_IMPROVEMENT = "design_improvement"
    OTHER = "other"


class MitigationStatus(str, Enum):
    """Implementation status of mitigation"""
    PROPOSED = "proposed"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Mitigation(BaseModel):
    """Mitigation or safety measure"""
    
    # Basic identification
    id: str = Field(description="Unique mitigation identifier")
    name: str = Field(description="Mitigation name")
    description: str = Field(description="Detailed description of the mitigation")
    
    # Classification
    mitigation_type: MitigationType = Field(description="Type of mitigation")
    status: MitigationStatus = Field(default=MitigationStatus.PROPOSED, description="Implementation status")
    
    # Effectiveness
    effectiveness: Optional[float] = Field(
        default=None, 
        ge=0.0, 
        le=1.0,
        description="Effectiveness factor (0.0 to 1.0)"
    )
    coverage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0, 
        description="Diagnostic coverage (0.0 to 1.0)"
    )
    
    # Implementation details
    implementation_method: Optional[str] = Field(default=None, description="How the mitigation is implemented")
    verification_method: Optional[str] = Field(default=None, description="How effectiveness is verified")
    
    # Cost and effort
    cost_estimate: Optional[float] = Field(default=None, description="Estimated cost")
    effort_estimate: Optional[str] = Field(default=None, description="Estimated effort (e.g., '2 weeks')")
    
    # Relationships
    deviation_ids: List[str] = Field(default_factory=list, description="Mitigated deviation IDs")
    component_ids: List[str] = Field(default_factory=list, description="Associated component IDs")
    
    # Additional information
    responsible_person: Optional[str] = Field(default=None, description="Responsible person or team")
    notes: Optional[str] = Field(default=None, description="Additional notes or comments")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "mit_001",
                "name": "Voltage Monitoring Circuit",
                "description": "Add voltage monitoring to detect power supply failures",
                "mitigation_type": "diagnostic",
                "status": "implemented",
                "effectiveness": 0.95,
                "coverage": 0.95,
                "implementation_method": "ADC-based voltage monitoring",
                "deviation_ids": ["dev_001"],
                "component_ids": ["comp_001"]
            }
        }
