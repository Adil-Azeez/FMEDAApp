

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class DeviationSeverity(str, Enum):
    """Severity levels for deviations"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DeviationType(str, Enum):
    """Types of deviations"""
    SAFE = "safe"
    DANGEROUS_DETECTED = "dangerous_detected"
    DANGEROUS_UNDETECTED = "dangerous_undetected"
    NO_EFFECT = "no_effect"


class Deviation(BaseModel):
    """Failure mode or deviation in the system"""
    
    # Basic identification
    id: str = Field(description="Unique deviation identifier")
    name: str = Field(description="Deviation name")
    description: str = Field(description="Detailed description of the deviation")
    
    # Classification
    deviation_type: DeviationType = Field(description="Type of deviation")
    severity: DeviationSeverity = Field(description="Severity level")
    
    # Failure mode details
    failure_mode: str = Field(description="Failure mode description")
    cause: Optional[str] = Field(default=None, description="Root cause of the deviation")
    effect: Optional[str] = Field(default=None, description="Effect of the deviation")
    
    # FMEDA metrics
    failure_rate: Optional[float] = Field(default=None, description="Failure rate (FIT)")
    detection_rate: Optional[float] = Field(default=None, description="Diagnostic detection rate")
    
    # Relationships
    component_ids: List[str] = Field(default_factory=list, description="Associated component IDs")
    mitigation_ids: List[str] = Field(default_factory=list, description="Associated mitigation IDs")
    
    # Additional information
    detection_method: Optional[str] = Field(default=None, description="How the deviation is detected")
    notes: Optional[str] = Field(default=None, description="Additional notes or comments")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "dev_001",
                "name": "Capacitor Short Circuit",
                "description": "Decoupling capacitor fails in short circuit mode",
                "deviation_type": "dangerous_detected",
                "severity": "high",
                "failure_mode": "Short circuit",
                "cause": "Overvoltage stress",
                "effect": "Power supply instability",
                "failure_rate": 0.05,
                "detection_rate": 0.95,
                "component_ids": ["comp_001"],
                "mitigation_ids": ["mit_001"]
            }
        }
