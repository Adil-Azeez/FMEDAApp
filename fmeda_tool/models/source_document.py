from typing import Optional
from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    """Source documents for traceability"""
    
    document_type: str = Field(description="Document type (BOM, Schematic, Requirements, etc.)")
    document_number: str = Field(default="", description="Document identification number")
    document_name: str = Field(default="", description="Document title/name")
    version: str = Field(default="1.0", description="Document version")
    date: Optional[str] = Field(default=None, description="Document release/creation date")
    local_file_path: Optional[str] = Field(default=None, description="Local filepath to the document")
    notes: Optional[str] = Field(default=None, description="Traceability comments or notes")
