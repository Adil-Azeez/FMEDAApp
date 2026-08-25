from typing import Optional
from pydantic import BaseModel, Field


class BOMComponent(BaseModel):
    """Component details imported from a Bill of Materials (BOM)"""
    
    id: str = Field(description="Unique BOM component ID (e.g. bom_xxx)")
    designator: str = Field(description="Schematic designator (e.g. R101, C102)")
    part_number: str = Field(default="", description="Manufacturer or internal part number")
    description: Optional[str] = Field(default=None, description="Component description")
    value: Optional[str] = Field(default=None, description="Component value (e.g. 10k, 0.1uF)")
    package: Optional[str] = Field(default=None, description="Package type (e.g. 0805, SOIC-8)")
    layer: Optional[str] = Field(default=None, description="Assembly layer (e.g. Top, Bottom)")
    quantity: int = Field(default=1, description="Component quantity")
    is_fitted: bool = Field(default=True, description="Whether the component is fitted/populated")
    notes: Optional[str] = Field(default=None, description="Notes or documentation comments")
    function: Optional[str] = Field(default=None, description="Component function")
    internal_part_number: Optional[str] = Field(default=None, description="Internal part number")
    manufacturer: Optional[str] = Field(default=None, description="Manufacturer name")
    manufacturer_part_number: Optional[str] = Field(default=None, description="Manufacturer part number")
    location: Optional[str] = Field(default=None, description="Location coordinates or details")
    source_file: Optional[str] = Field(default=None, description="Source CSV filepath")
    row_number: Optional[int] = Field(default=None, description="Source CSV row number")
