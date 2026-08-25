from pydantic import BaseModel, Field


class ComponentMapping(BaseModel):
    """Binds a physical BOM component to a database component failure model template"""
    
    bom_component_id: str = Field(description="ID of the BOM component instance")
    component_db_id: str = Field(description="ID of the matched ComponentDB database template")
    confidence: float = Field(default=0.0, description="Matching confidence score (0.0 to 1.0)")
    is_confirmed: bool = Field(default=False, description="Whether the mapping has been verified by the user")
