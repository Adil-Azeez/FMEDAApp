from typing import Optional
from pydantic import BaseModel, Field


class SafetyContext(BaseModel):
    """Safety context and requirements for the FMEDA project"""
    
    safety_function_name: str = Field(default="", description="Name of the safety function")
    safety_function_description: str = Field(default="", description="Description of the safety function")
    safe_state: str = Field(default="", description="Defined safe state of the system")
    dangerous_state: str = Field(default="", description="Defined dangerous state of the system")
    safety_architecture: str = Field(default="1oo1", description="Safety architecture (1oo1, 1oo2, etc.)")
    operating_mode: str = Field(default="Low demand mode", description="Demand mode of operation")
    safety_boundary: str = Field(default="", description="Physical/functional safety boundary definition")
    external_sensor_included: bool = Field(default=False, description="Whether external sensor is in scope")
    no_part_failure_definition: Optional[str] = Field(default=None, description="Definition of No Part Failure")
    no_effect_failure_definition: Optional[str] = Field(default=None, description="Definition of No Effect Failure")
    notes: Optional[str] = Field(default=None, description="Notes on safety context")
