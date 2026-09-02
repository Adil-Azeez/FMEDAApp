
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from .unit import Unit
from .deviation import Deviation
from .mitigation import Mitigation
from .diagnostic_measure import DiagnosticMeasure
from .safety_context import SafetyContext
from .source_document import SourceDocument


class ProjectStatus(str, Enum):
    """Project status"""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class SafetyStandard(str, Enum):
    """Safety standards"""
    IEC_61508 = "IEC 61508"



class Project(BaseModel):
    """FMEDA analysis project"""
    
    # Basic identification
    id: str = Field(description="Unique project identifier")
    name: str = Field(description="Project name")
    description: str = Field(description="Project description")
    version: str = Field(default="1.0.0", description="Project version")
    project_number: Optional[str] = Field(default=None, description="Project or document number")
    
    # Project metadata
    status: ProjectStatus = Field(default=ProjectStatus.DRAFT, description="Project status")
    created_by: Optional[str] = Field(default=None, description="Creator name")
    organization: Optional[str] = Field(default=None, description="Organization name")
    reviewer: Optional[str] = Field(default=None, description="Reviewer name")
    
    # Safety requirements
    safety_standard: Optional[SafetyStandard] = Field(default=None, description="Applicable safety standard")
    target_sil: Optional[str] = Field(default=None, description="Target Safety Integrity Level")
    
    # Product information
    product_name: Optional[str] = Field(default=None, description="Product name")
    product_group: Optional[str] = Field(default=None, description="Product group")
    product_version: Optional[str] = Field(default=None, description="Product version")
    hardware_version: Optional[str] = Field(default=None, description="Hardware version")
    software_version: Optional[str] = Field(default=None, description="Software version")
    
    # Safety Context
    safety_context: Optional[SafetyContext] = Field(default=None, description="Project safety context and demand details")
    
    # Traceability and DB sources
    source_documents_list: List[SourceDocument] = Field(default_factory=list, description="Structured source documents")
    reliability_database_source: Optional[str] = Field(default=None, description="Reliability database source")
    selected_profile: str = Field(default="Profile 1", description="Selected Exida reliability profile (Profile 1 to Profile 5)")
    environmental_profile: Optional[str] = Field(default=None, description="Environmental or operating profile")
    diagnostic_test_interval: Optional[float] = Field(default=None, description="Diagnostic test interval in hours")
    
    # Project components
    units: List[Unit] = Field(default_factory=list, description="Functional units in the project")
    deviations: List[Deviation] = Field(default_factory=list, description="Identified deviations")
    mitigations: List[Mitigation] = Field(default_factory=list, description="Implemented mitigations")
    diagnostic_measures: List[DiagnosticMeasure] = Field(
        default_factory=list,
        description="Diagnostic measures for failure detection"
    )
    
    # Analysis results (calculated)
    total_failure_rate: Optional[float] = Field(default=None, description="Total system failure rate (FIT)")
    safe_failure_rate: Optional[float] = Field(default=None, description="Safe failure rate (FIT)")
    dangerous_detected_rate: Optional[float] = Field(default=None, description="Dangerous detected rate (FIT)")
    dangerous_undetected_rate: Optional[float] = Field(default=None, description="Dangerous undetected rate (FIT)")
    
    # Metrics (calculated)
    sff: Optional[float] = Field(default=None, description="Safe Failure Fraction")
    pfd_avg: Optional[float] = Field(default=None, description="Average Probability of Failure on Demand")
    pfd_max: Optional[float] = Field(default=None, description="Maximum PFD")
    achieved_sil: Optional[str] = Field(default=None, description="Achieved SIL level")
    
    # Gesamtgeraet metrics
    lambda_total_gesamtgerat: Optional[float] = Field(default=None, description="Total Gesamtgeraet failure rate (FIT)")
    lambda_safe_gesamtgerat: Optional[float] = Field(default=None, description="Safe Gesamtgeraet failure rate (FIT)")
    lambda_dangerous_gesamtgerat: Optional[float] = Field(default=None, description="Dangerous Gesamtgeraet failure rate (FIT)")
    lambda_sd_gesamtgerat: Optional[float] = Field(default=None, description="Safe detected Gesamtgeraet failure rate (FIT)")
    lambda_su_gesamtgerat: Optional[float] = Field(default=None, description="Safe undetected Gesamtgeraet failure rate (FIT)")
    lambda_dd_gesamtgerat: Optional[float] = Field(default=None, description="Dangerous detected Gesamtgeraet failure rate (FIT)")
    lambda_du_gesamtgerat: Optional[float] = Field(default=None, description="Dangerous undetected Gesamtgeraet failure rate (FIT)")
    sff_gesamtgerat: Optional[float] = Field(default=None, description="Safe Failure Fraction for Gesamtgeraet")
    
    # Sicherheitskanal metrics
    lambda_total_sicherheitskanal: Optional[float] = Field(default=None, description="Total Sicherheitskanal failure rate (FIT)")
    lambda_safe_sicherheitskanal: Optional[float] = Field(default=None, description="Safe Sicherheitskanal failure rate (FIT)")
    lambda_dangerous_sicherheitskanal: Optional[float] = Field(default=None, description="Dangerous Sicherheitskanal failure rate (FIT)")
    lambda_sd_sicherheitskanal: Optional[float] = Field(default=None, description="Safe detected Sicherheitskanal failure rate (FIT)")
    lambda_su_sicherheitskanal: Optional[float] = Field(default=None, description="Safe undetected Sicherheitskanal failure rate (FIT)")
    lambda_dd_sicherheitskanal: Optional[float] = Field(default=None, description="Dangerous detected Sicherheitskanal failure rate (FIT)")
    lambda_du_sicherheitskanal: Optional[float] = Field(default=None, description="Dangerous undetected Sicherheitskanal failure rate (FIT)")
    sff_sicherheitskanal: Optional[float] = Field(default=None, description="Safe Failure Fraction for Sicherheitskanal")
    dc_sicherheitskanal: Optional[float] = Field(default=None, description="Diagnostic Coverage for Sicherheitskanal")
    mttfd_sicherheitskanal: Optional[float] = Field(default=None, description="MTTFd for Sicherheitskanal in years")
    
    # File paths and references
    source_documents: List[str] = Field(default_factory=list, description="Source document paths")
    export_path: Optional[str] = Field(default=None, description="Last export path")
    
    # Additional data
    tags: List[str] = Field(default_factory=list, description="Project tags for categorization")
    custom_fields: Dict[str, str] = Field(default_factory=dict, description="Custom user-defined fields")
    notes: Optional[str] = Field(default=None, description="Project notes")
    change_history: List[Dict[str, Any]] = Field(default_factory=list, description="Change history logs")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Completion timestamp")
    
    # Analysis settings
    mission_time: Optional[float] = Field(default=None, description="Mission time in hours")
    test_interval: Optional[float] = Field(default=None, description="Proof test interval in hours")
    
    # Schema Versioning & Workspace State
    schema_version: int = Field(default=2, description="Project schema version")
    last_active_tab_id: Optional[str] = Field(default=None, description="ID of the last active tab to restore")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "proj_001",
                "name": "Industrial Controller FMEDA",
                "description": "FMEDA analysis for safety-critical industrial controller",
                "version": "1.0.0",
                "status": "in_progress",
                "created_by": "John Doe",
                "organization": "Safety Engineering Corp",
                "safety_standard": "IEC 61508",
                "target_sil": "SIL 2",
                "product_name": "IC-2000 Controller",
                "product_version": "2.1",
                "mission_time": 87600.0,
                "test_interval": 8760.0,
                "units": [],
                "deviations": [],
                "mitigations": []
            }
        }
