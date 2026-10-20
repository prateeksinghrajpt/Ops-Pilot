from datetime import datetime
from typing import Literal, Any
from pydantic import BaseModel, Field

Scenario = Literal["http_5xx_spike", "database_latency", "memory_pressure", "deployment_regression"]
Severity = Literal["low", "medium", "high", "critical"]

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime
    access_uses_remaining: int
    is_admin: bool = False
    model_config = {"from_attributes": True}

class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class SimulateIncidentRequest(BaseModel):
    scenario: Scenario = "http_5xx_spike"
    service_name: str = Field(default="checkout-service", min_length=2, max_length=120)
    severity: Severity = "high"

class CreateIncidentRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    service_name: str = Field(min_length=2, max_length=120)
    scenario: str = Field(default="custom", max_length=60)
    severity: Severity = "medium"
    summary: str = ""
    signals: dict[str, Any] = Field(default_factory=dict)

class EvidenceOut(BaseModel):
    id: str
    source: str
    level: str
    message: str
    details: dict
    timestamp: datetime
    model_config = {"from_attributes": True}

class InvestigationOut(BaseModel):
    id: str
    status: str
    root_cause: str
    confidence: float
    impact: str
    recommended_actions: list
    evidence_ids: list
    facts: list = []
    hypotheses: list = []
    model: str
    remediation_approved: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class IncidentOut(BaseModel):
    id: str
    title: str
    service_name: str
    scenario: str
    severity: str
    status: str
    summary: str
    signals: dict
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceOut] = []
    investigation: InvestigationOut | None = None
    model_config = {"from_attributes": True}

class ApproveRequest(BaseModel):
    approved_by: str = Field(default="local-engineer", min_length=2, max_length=120)
    note: str = Field(default="", max_length=1000)

class AccessRequestOut(BaseModel):
    id: str
    user_id: str
    requester_email: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    model_config = {"from_attributes": True}

class GrantAccessRequest(BaseModel):
    uses: int = Field(default=1, ge=1, le=100)
