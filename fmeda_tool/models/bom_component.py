from typing import Optional
from pydantic import BaseModel, Field


class BOMComponent(BaseModel):
    """Component details imported from a Bill of Materials (BOM) text file"""
    
    id: str = Field(description="Unique BOM component ID (e.g. bom_xxx)")
    designator: str = Field(description="Schematic designator / Pos (e.g. R101, C3)")
    part_number: str = Field(default="", description="Internal Part Number / Material Number (MN)")
    description: Optional[str] = Field(default=None, description="Component description (Beschreibung)")
    value: Optional[str] = Field(default=None, description="Component value (Wert)")
    benennung: Optional[str] = Field(default=None, description="BOM designation / component class (Benennung)")
    layer: Optional[str] = Field(default=None, description="Assembly layer / PCB side (Lage)")
    notes: Optional[str] = Field(default=None, description="Notes or documentation comments (Bemerkung)")
    vs: Optional[str] = Field(default=None, description="Version / Status code (Vs)")
    package: Optional[str] = Field(default=None, description="Package type (e.g. 0805, SOIC-8)")
    quantity: int = Field(default=1, description="Component quantity")
    is_fitted: bool = Field(default=True, description="Whether the component is fitted/populated")
    function: Optional[str] = Field(default=None, description="Component function")
    internal_part_number: Optional[str] = Field(default=None, description="Internal part number / MN")
    manufacturer: Optional[str] = Field(default=None, description="Manufacturer name")
    manufacturer_part_number: Optional[str] = Field(default=None, description="Manufacturer part number")
    location: Optional[str] = Field(default=None, description="Location coordinates or details")
    source_file: Optional[str] = Field(default=None, description="Source BOM text filepath")
    row_number: Optional[int] = Field(default=None, description="Source BOM text row number")
    original_line: Optional[str] = Field(default=None, description="Original source line text")
