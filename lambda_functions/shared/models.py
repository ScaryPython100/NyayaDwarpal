"""
Data Models for Nyaya-Dwarpal AI Agent

This module defines Pydantic models for data validation and serialization.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class LegalCategory(str, Enum):
    """Legal case categories"""
    CIVIL = "Civil"
    CRIMINAL = "Criminal"
    CONSUMER = "Consumer"
    FAMILY = "Family"
    PROPERTY = "Property"
    OTHER = "Other"


class SeverityLevel(str, Enum):
    """Case severity levels"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class EmotionalState(str, Enum):
    """User emotional states"""
    DISTRESSED = "distressed"
    ANGRY = "angry"
    CONFUSED = "confused"
    CALM = "calm"


class DocumentStatus(str, Enum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEFECTIVE = "defective"


class TriageResult(BaseModel):
    """Legal triage classification result"""
    facts: Dict[str, Any] = Field(description="Extracted key facts")
    category: LegalCategory = Field(description="Legal category")
    sections: List[str] = Field(description="Relevant legal sections")
    severity: SeverityLevel = Field(description="Severity level")
    emotion: EmotionalState = Field(description="User's emotional state")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")


class PetitionSections(BaseModel):
    """Structured petition sections"""
    facts_section: str = Field(description="Facts section of petition")
    grounds_section: str = Field(description="Grounds section with legal provisions")
    prayer_section: str = Field(description="Prayer section with relief sought")
    verification: str = Field(description="Verification statement")


class CitationVerification(BaseModel):
    """Citation verification result"""
    citation: str = Field(description="Original citation")
    is_valid: bool = Field(description="Whether citation exists")
    is_outdated: bool = Field(description="Whether citation is outdated")
    suggested_replacement: Optional[str] = Field(description="Updated equivalent if outdated")
    relevance_score: float = Field(ge=0.0, le=1.0, description="Relevance to argument")
    relevance_explanation: str = Field(description="Explanation of relevance")


class DocumentDefect(BaseModel):
    """Document defect description"""
    defect_type: str = Field(description="Type of defect")
    description: str = Field(description="Detailed description")
    remediation: str = Field(description="How to fix the defect")
    severity: str = Field(description="Defect severity: critical, major, minor")


class DocumentMetadata(BaseModel):
    """Document metadata stored in DynamoDB"""
    document_id: str = Field(description="Unique document identifier")
    case_number: Optional[str] = Field(description="Case number if assigned")
    document_type: str = Field(description="Type of document")
    filing_timestamp: str = Field(description="ISO 8601 timestamp")
    filer_info: Dict[str, Any] = Field(description="Information about filer")
    s3_location: Dict[str, str] = Field(description="S3 bucket and key")
    status: DocumentStatus = Field(description="Processing status")
    preferred_language: str = Field(description="User's preferred language")
    triage_results: Optional[TriageResult] = Field(description="Triage classification")
    petition_sections: Optional[PetitionSections] = Field(description="Generated petition")
    citation_verifications: Optional[List[CitationVerification]] = Field(description="Citation checks")
    defects: Optional[List[DocumentDefect]] = Field(description="Detected defects")
    created_at: str = Field(description="Creation timestamp")
    updated_at: str = Field(description="Last update timestamp")
    ttl: int = Field(description="TTL for automatic deletion (Unix timestamp)")
    
    class Config:
        use_enum_values = True


class UserSession(BaseModel):
    """User session for conversational state"""
    session_id: str = Field(description="Unique session identifier")
    user_id: str = Field(description="User identifier")
    document_id: Optional[str] = Field(description="Associated document ID")
    conversation_history: List[Dict[str, str]] = Field(description="Chat history")
    current_step: str = Field(description="Current workflow step")
    context: Dict[str, Any] = Field(description="Session context data")
    preferred_language: str = Field(description="User's preferred language")
    created_at: str = Field(description="Session creation timestamp")
    updated_at: str = Field(description="Last update timestamp")
    ttl: int = Field(description="TTL for automatic deletion (Unix timestamp)")


class LegalGlossaryTerm(BaseModel):
    """Legal glossary term mapping"""
    term: str = Field(description="Regional legal term")
    language: str = Field(description="Language code (ISO 639-1)")
    english_equivalent: str = Field(description="English translation")
    definition: str = Field(description="Term definition")
    examples: List[str] = Field(description="Usage examples")
    category: str = Field(description="Legal category")
    created_at: str = Field(description="Creation timestamp")
    updated_at: str = Field(description="Last update timestamp")


class APIResponse(BaseModel):
    """Standard API response format"""
    success: bool = Field(description="Whether request succeeded")
    message: str = Field(description="Response message")
    data: Optional[Dict[str, Any]] = Field(description="Response data")
    error: Optional[str] = Field(description="Error message if failed")
    timestamp: str = Field(description="Response timestamp")
    
    @classmethod
    def success_response(cls, message: str, data: Optional[Dict[str, Any]] = None):
        """Create success response"""
        return cls(
            success=True,
            message=message,
            data=data,
            error=None,
            timestamp=datetime.utcnow().isoformat()
        )
    
    @classmethod
    def error_response(cls, message: str, error: str):
        """Create error response"""
        return cls(
            success=False,
            message=message,
            data=None,
            error=error,
            timestamp=datetime.utcnow().isoformat()
        )
