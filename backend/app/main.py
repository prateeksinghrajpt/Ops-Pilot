from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from .config import settings
from .database import Base, engine, get_db
from .github_connector import GitHubConnectorError
from . import models
from .schemas import SimulateIncidentRequest, CreateIncidentRequest, IncidentOut, ApproveRequest
from .services import create_incident, simulate_incident, list_incidents, get_incident, dashboard, run_investigation, approve_remediation, collect_github_evidence

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

@app.get("/api/v1/dashboard", tags=["Dashboard"])
def get_dashboard(db: Session = Depends(get_db)):
    return dashboard(db)

@app.get("/api/v1/incidents", response_model=list[IncidentOut], tags=["Incidents"])
def get_incidents(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    return list_incidents(db, limit=limit)

@app.post("/api/v1/incidents", response_model=IncidentOut, status_code=201, tags=["Incidents"])
def post_incident(payload: CreateIncidentRequest, db: Session = Depends(get_db)):
    return create_incident(
        db, title=payload.title, service_name=payload.service_name,
        scenario=payload.scenario, severity=payload.severity, summary=payload.summary,
        signals=payload.signals
    )

@app.post("/api/v1/incidents/simulate", response_model=IncidentOut, status_code=201, tags=["Incidents"])
def simulate(payload: SimulateIncidentRequest, db: Session = Depends(get_db)):
    return simulate_incident(db, payload.scenario, payload.service_name, payload.severity)

@app.get("/api/v1/incidents/{incident_id}", response_model=IncidentOut, tags=["Incidents"])
def incident_detail(incident_id: str, db: Session = Depends(get_db)):
    incident = get_incident(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@app.post("/api/v1/incidents/{incident_id}/investigate", response_model=IncidentOut, tags=["Investigation"])
def investigate_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = run_investigation(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@app.post("/api/v1/incidents/{incident_id}/collect-github-evidence", response_model=IncidentOut, tags=["Evidence"])
def collect_github(incident_id: str, db: Session = Depends(get_db)):
    try:
        incident = collect_github_evidence(db, incident_id)
    except GitHubConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@app.post("/api/v1/incidents/{incident_id}/approve-remediation", response_model=IncidentOut, tags=["Approval"])
def approve(incident_id: str, payload: ApproveRequest, db: Session = Depends(get_db)):
    incident = approve_remediation(db, incident_id, payload.approved_by, payload.note)
    if not incident:
        raise HTTPException(status_code=400, detail="Incident or completed investigation not found")
    return incident
