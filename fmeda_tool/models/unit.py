
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from .component import Component
from .bom_component import BOMComponent
from .component_mapping import ComponentMapping


class Unit(BaseModel):
    """Functional unit or subsystem"""
    
    # Basic identification
    id: str = Field(description="Unique unit identifier")
    name: str = Field(description="Unit name")
    description: str = Field(description="Detailed description of the unit")
    
    # Classification
    unit_type: Optional[str] = Field(default=None, description="Type of unit (e.g., Power Supply, Controller)")
    function: Optional[str] = Field(default=None, description="Primary function of the unit")
    
    # Hierarchy
    parent_unit_id: Optional[str] = Field(default=None, description="Parent unit ID if this is a sub-unit")
    sub_unit_ids: List[str] = Field(default_factory=list, description="Child unit IDs")
    
    # Components
    components: List[Component] = Field(default_factory=list, description="Components in this unit")
    bom_components: List[BOMComponent] = Field(default_factory=list, description="BOM Components in this functional group")
    component_mappings: List[ComponentMapping] = Field(default_factory=list, description="BOM component mappings to DB templates")
    
    # Functional group attributes
    included_in_safety_function: bool = Field(default=True, description="Whether this unit is part of the safety function")
    optional_module: bool = Field(default=False, description="Whether this unit is an optional hardware module")
    variant_dependency: Optional[str] = Field(default=None, description="Variant dependency information")
    status: str = Field(default="Draft", description="Status of the functional group (e.g., Draft, In Progress, etc.)")
    
    # FMEDA metrics (calculated from components and deviations)
    total_failure_rate: Optional[float] = Field(default=None, description="Total failure rate (FIT)")
    safe_failure_fraction: Optional[float] = Field(default=None, description="Safe failure fraction")
    dangerous_detected_fraction: Optional[float] = Field(default=None, description="Dangerous detected fraction")
    dangerous_undetected_fraction: Optional[float] = Field(default=None, description="Dangerous undetected fraction")
    diagnostic_coverage: Optional[float] = Field(default=None, description="Diagnostic Coverage of the unit")
    
    # Safety integrity level
    sil_rating: Optional[str] = Field(default=None, description="Safety Integrity Level (SIL 1-4)")
    target_sil: Optional[str] = Field(default=None, description="Target SIL level")
    
    # Additional information
    criticality: Optional[str] = Field(default=None, description="Criticality level (Low, Medium, High, Critical)")
    notes: Optional[str] = Field(default=None, description="Additional notes or comments")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "unit_001",
                "name": "Power Supply Unit",
                "description": "Main power supply subsystem providing regulated voltages",
                "unit_type": "Power Supply",
                "function": "Convert 24V input to 5V and 3.3V regulated outputs",
                "criticality": "high",
                "target_sil": "SIL 2",
                "components": []
            }
        }
