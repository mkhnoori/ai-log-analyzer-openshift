from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone


class LogEntry(BaseModel):
    source: str  # jenkins | gitlab | github_actions | k8s | custom
    build_id: Optional[str] = None
    step_name: Optional[str] = None
    exit_code: Optional[int] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_log: str


class LogChunk(BaseModel):
    chunk_id: str
    log_entry: LogEntry
    content: str
    token_count: int
    chunk_index: int


class RetrievedIncident(BaseModel):
    incident_id: str
    log_snippet: str
    root_cause: str
    fix_applied: str
    confidence: float
    similarity_score: float


class AnalysisResult(BaseModel):
    incident_id: Optional[str] = None   # set by the API, used by feedback loop
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    fix_suggestion: str
    fix_steps: List[str] = []
    evidence_steps: List[str]
    similar_incidents: List[RetrievedIncident]
    causal_chain: List[str]
    severity: str  # low | medium | high | critical
    prevention: str = ""
    docs_links: List[str] = []
    analysis_time_ms: int


class AnalysisRequest(BaseModel):
    log_entry: LogEntry


class FeedbackRequest(BaseModel):
    incident_id: str
    log_snippet: Optional[str] = None
    predicted_root_cause: Optional[str] = None
    correct_root_cause: Optional[str] = None
    fix_applied: Optional[str] = None
    fix_worked: bool
    rating: int = Field(ge=1, le=5)
    notes: Optional[str] = None
    source: str = "unknown" 


class AddIncidentRequest(BaseModel):
    log_snippet: str
    root_cause: str
    fix_applied: str
