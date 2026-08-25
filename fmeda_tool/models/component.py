"""
Component data model for FMEDA Tool
Represents an electronic component in a unit
"""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from .failure_mode_assignment import FailureModeAssignment


class Component(BaseModel):
    """Electronic component in a unit"""
    
    # Basic identification
    id: str = Field(description="Unique component identifier")
    position: str = Field(description="Component position/reference (e.g., C101, R205)")
    name: str = Field(description="Component name or description")
    
    # Component specifications
    type: str = Field(description="Component type (e.g., Resistor, Capacitor, IC)")
    value: Optional[str] = Field(default=None, description="Component value (e.g., 10kΩ, 100μF)")
    manufacturer: Optional[str] = Field(default=None, description="Manufacturer name")
    part_number: Optional[str] = Field(default=None, description="Manufacturer part number")
    function: Optional[str] = Field(default=None, description="Component function")
    internal_pn: Optional[str] = Field(default=None, description="Internal part number")
    fitted_status: Optional[str] = Field(default="Fitted", description="Fitted status (Fitted / Not Fitted)")
    
    # Location information
    layer: Optional[str] = Field(default=None, description="PCB layer (e.g., TOP, BOTTOM)")
    x_position: Optional[float] = Field(default=None, description="X coordinate position")
    y_position: Optional[float] = Field(default=None, description="Y coordinate position")
    
    # FMEDA-specific data
    failure_rate: Optional[float] = Field(default=None, description="Failure rate (FIT)")
    safe_failure_fraction: Optional[float] = Field(default=None, description="Safe failure fraction (SFF)")
    
    # Failure modes (from ComponentDB template)
    failure_modes: Dict[str, float] = Field(
        default_factory=dict,
        description="Base failure modes with their percentage of overall FITS"
    )
    
    # Failure mode assignments (configured for this specific component instance)
    failure_mode_assignments: List[FailureModeAssignment] = Field(
        default_factory=list,
        description="Assignments of failure modes to deviations and diagnostics"
    )
    
    # Relationships
    deviation_ids: List[str] = Field(default_factory=list, description="Associated deviation IDs")
    mitigation_ids: List[str] = Field(default_factory=list, description="Associated mitigation IDs")
    
    # Additional notes
    notes: Optional[str] = Field(default=None, description="Additional notes or comments")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "comp_001",
                "position": "C101",
                "name": "Decoupling Capacitor",
                "type": "Capacitor",
                "value": "100μF",
                "manufacturer": "Samsung",
                "part_number": "CL21A106KOQNNNE",
                "layer": "TOP",
                "failure_rate": 0.05,
                "deviation_ids": ["dev_001"],
                "mitigation_ids": ["mit_001"]
            }
        }
