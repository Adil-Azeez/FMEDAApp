"""
Component data model for FMEDA Tool
Represents an electronic component in a unit with library references and project snapshots.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from .failure_mode_assignment import FailureModeAssignment


class Component(BaseModel):
    """Electronic component in a unit"""
    
    # Basic identification
    id: str = Field(description="Unique component instance identifier")
    position: str = Field(description="Component position/reference (e.g., C101, R205)")
    name: str = Field(description="Component name or description")
    
    # Component specifications
    type: str = Field(description="Component type or displayed label (e.g., CEL, Resistor, Capacitor)")
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
    
    # FMEDA-specific data & Stored Snapshot
    failure_rate: Optional[float] = Field(default=None, description="Failure rate (FIT)")
    safe_failure_fraction: Optional[float] = Field(default=None, description="Safe failure fraction (SFF)")
    
    # Failure modes (from ComponentDB template / snapshot)
    failure_modes: Dict[str, float] = Field(
        default_factory=dict,
        description="Base failure modes with their percentage of overall FIT"
    )
    
    # Failure mode assignments (configured for this specific component instance)
    failure_mode_assignments: List[FailureModeAssignment] = Field(
        default_factory=list,
        description="Assignments of failure modes to deviations and diagnostics"
    )
    
    # Library References & Project Snapshotting
    library_component_id: Optional[str] = Field(default=None, description="UUID or legacy ID in SQLite component library")
    failure_rate_id: Optional[str] = Field(default=None, description="Failure Rate ID (e.g. FR-000001)")
    item_no: Optional[str] = Field(default=None, description="Handbook Item Number (e.g. E.1.1.1)")
    component_subtype: Optional[str] = Field(default=None, description="Component subtype")
    component_use_category: Optional[str] = Field(default=None, description="Component use category")
    selected_profile: Optional[str] = Field(default=None, description="Selected profile name (e.g. Profile 1)")
    source_type: Optional[str] = Field(default="exida", description="Source type ('exida' or 'legacy')")
    library_id: Optional[str] = Field(default=None, description="Library metadata UUID")
    schema_version: Optional[str] = Field(default=None, description="Library schema version")
    snapshot: Optional[Dict[str, Any]] = Field(default=None, description="Complete library snapshot at time of selection")
    
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
                "type": "CEL",
                "failure_rate_id": "FR-000001",
                "failure_rate": 5.2,
                "selected_profile": "Profile 1",
                "source_type": "exida"
            }
        }
