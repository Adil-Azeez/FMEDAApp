

from typing import Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ComponentDB(BaseModel):
    """Component template in the database"""
    
    # Basic identification
    id: str = Field(description="Unique component database identifier")
    display_name: str = Field(description="Display name of the component")
    shortcut: Optional[str] = Field(default=None, description="Shortcut or abbreviation")
    
    # Technical specifications
    material: Optional[str] = Field(default=None, description="Component material")
    fits: Optional[float] = Field(default=None, description="Overall FITS (Failure In Time) value")
    database: Optional[str] = Field(default=None, description="Source database or standard")
    
    # Failure modes: key=failure mode name, value=percentage of overall FITS
    failure_modes: Dict[str, float] = Field(
        default_factory=dict, 
        description="Failure modes with their percentage of overall FITS (lambda)"
    )
    
    # Extended Library Metadata & Project Snapshot
    library_component_id: Optional[str] = Field(default=None, description="Library UUID or legacy component ID")
    failure_rate_id: Optional[str] = Field(default=None, description="Failure rate ID (e.g. FR-000001)")
    item_no: Optional[str] = Field(default=None, description="Handbook item number")
    component_subtype: Optional[str] = Field(default=None, description="Component subtype")
    component_use_category: Optional[str] = Field(default=None, description="Component use category")
    selected_profile: Optional[str] = Field(default=None, description="Selected profile name")
    source_type: Optional[str] = Field(default=None, description="Source type (exida or legacy)")
    library_id: Optional[str] = Field(default=None, description="Library metadata UUID")
    schema_version: Optional[str] = Field(default=None, description="Library schema version")
    snapshot: Optional[Dict[str, Any]] = Field(default=None, description="Complete library snapshot")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "compdb_001",
                "display_name": "Ceramic Capacitor 100nF",
                "shortcut": "C100N",
                "material": "Ceramic X7R",
                "fits": 5.0,
                "database": "MIL-HDBK-217F",
                "failure_modes": {
                    "Short Circuit": 40.0,
                    "Open Circuit": 35.0,
                    "Degradation": 25.0
                }
            }
        }
