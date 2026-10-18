from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import re

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from .config import settings
from .database import Base, engine, get_db
from .github_connector import GitHubConnectorError
from . import models
from .schemas import SimulateIncidentRequest, CreateIncidentRequest, IncidentOut, ApproveRequest, AuthOut, Credentials, UserOut
from .security import create_access_token, get_current_user_id, hash_password, verify_password
from .services import create_incident, simulate_incident, list_incidents, get_incident, dashboard, run_investigation, approve_remediation, collect_github_evidence, get_user, get_user_by_email, register_user

def ensure_runtime_schema():
    inspector = inspect(engine)
    if "investigations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("investigations")}
    statements = []
    if "facts" not in columns:
        statements.append("ALTER TABLE investigations ADD COLUMN facts JSON DEFAULT '[]'")
    if "hypotheses" not in columns:
        statements.append("ALTER TABLE investigations ADD COLUMN hypotheses JSON DEFAULT '[]'")
    incident_columns = {column["name"] for column in inspector.get_columns("incidents")}
    if "user_id" not in incident_columns:
        statements.append("ALTER TABLE incidents ADD COLUMN user_id VARCHAR(36)")
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    yield

app = FastAPI(
    title="OpsPilot API",
    description="AI-powered production incident investigation MVP",
    version="1.0.0",
    lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.allowed_origins or ["http://localhost:5173"],
    allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
)

@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "service": "opspilot-api", "version": "1.0.0"}

def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    return normalized

def auth_response(user):
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": user}

@app.post("/api/v1/auth/signup", response_model=AuthOut, status_code=201, tags=["Authentication"])
def signup(payload: Credentials, db: Session = Depends(get_db)):
    email = normalize_email(payload.email)
    if get_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    return auth_response(register_user(db, email, hash_password(payload.password)))

@app.post("/api/v1/auth/login", response_model=AuthOut, tags=["Authentication"])
def login(payload: Credentials, db: Session = Depends(get_db)):
    user = get_user_by_email(db, normalize_email(payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return auth_response(user)

@app.get("/api/v1/auth/me", response_model=UserOut, tags=["Authentication"])
def me(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

@app.get("/api/v1/dashboard", tags=["Dashboard"])
def get_dashboard(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return dashboard(db, user_id)

@app.get("/api/v1/incidents", response_model=list[IncidentOut], tags=["Incidents"])
def get_incidents(limit: int = Query(default=50, ge=1, le=200), user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return list_incidents(db, user_id, limit=limit)

@app.post("/api/v1/incidents", response_model=IncidentOut, status_code=201, tags=["Incidents"])
def post_incident(payload: CreateIncidentRequest, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return create_incident(
        db, user_id=user_id, title=payload.title, service_name=payload.service_name,
        scenario=payload.scenario, severity=payload.severity, summary=payload.summary,
        signals=payload.signals
    )

@app.post("/api/v1/incidents/simulate", response_model=IncidentOut, status_code=201, tags=["Incidents"])
def simulate(payload: SimulateIncidentRequest, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return simulate_incident(db, user_id, payload.scenario, payload.service_name, payload.severity)

@app.get("/api/v1/incidents/{incident_id}", response_model=IncidentOut, tags=["Incidents"])
def incident_detail(incident_id: str, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    incident = get_incident(db, incident_id, user_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@app.post("/api/v1/incidents/{incident_id}/investigate", response_model=IncidentOut, tags=["Investigation"])
def investigate_incident(incident_id: str, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    incident = run_investigation(db, incident_id, user_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@app.post("/api/v1/incidents/{incident_id}/collect-github-evidence", response_model=IncidentOut, tags=["Evidence"])
def collect_github(incident_id: str, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    try:
        incident = collect_github_evidence(db, incident_id, user_id)
    except GitHubConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@app.post("/api/v1/incidents/{incident_id}/approve-remediation", response_model=IncidentOut, tags=["Approval"])
def approve(incident_id: str, payload: ApproveRequest, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    incident = approve_remediation(db, incident_id, user_id, payload.approved_by, payload.note)
    if not incident:
        raise HTTPException(status_code=400, detail="Incident or completed investigation not found")
    return incident
