from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from .config import settings
from .github_connector import GitHubConnectorError, collect_github_events
from .models import Incident, Evidence, Investigation, User, AccessRequest
from .simulator import build_scenario
try:
    from ai_service.investigator import investigate
except ModuleNotFoundError:
    from backend.ai_service.investigator import investigate

def now():
    return datetime.now(timezone.utc)

def create_incident(db: Session, *, user_id, title, service_name, scenario, severity, summary="", signals=None, evidence_items=None):
    incident_id = str(uuid4())
    incident = Incident(
        id=incident_id, user_id=user_id, title=title, service_name=service_name, scenario=scenario,
        severity=severity, status="open", summary=summary, signals=signals or {},
        created_at=now(), updated_at=now()
    )
    db.add(incident)
    for item in evidence_items or []:
        db.add(Evidence(
            id=str(uuid4()), incident_id=incident_id, source=item["source"],
            level=item.get("level", "info"), message=item["message"],
            details=item.get("details", {}), timestamp=item.get("timestamp") or now()
        ))
    db.commit()
    return get_incident(db, incident_id, user_id)

def simulate_incident(db: Session, user_id: str, scenario: str, service_name: str, severity: str):
    data = build_scenario(scenario)
    incident = create_incident(
        db, user_id=user_id, title=data["title"], service_name=service_name, scenario=scenario,
        severity=severity, summary=data["summary"], signals=data["signals"],
        evidence_items=data["evidence"]
    )
    # Internal fallback context is derived from scenario templates, not user input.
    incident._fallback_cause = data["fallback_cause"]
    incident._fallback_actions = data["fallback_actions"]
    return incident

def list_incidents(db: Session, user_id: str, limit=50):
    return list(db.scalars(
        select(Incident).options(selectinload(Incident.evidence), selectinload(Incident.investigation)).where(Incident.user_id == user_id)
        .order_by(Incident.created_at.desc()).limit(limit)
    ).all())

def get_incident(db: Session, incident_id: str, user_id: str):
    return db.scalar(
        select(Incident).options(selectinload(Incident.evidence), selectinload(Incident.investigation))
        .where(Incident.id == incident_id, Incident.user_id == user_id)
    )

def dashboard(db: Session, user_id: str):
    scope = Incident.user_id == user_id
    total = db.scalar(select(func.count()).select_from(Incident).where(scope)) or 0
    open_count = db.scalar(select(func.count()).select_from(Incident).where(scope, Incident.status == "open")) or 0
    investigating = db.scalar(select(func.count()).select_from(Incident).where(scope, Incident.status == "investigating")) or 0
    critical = db.scalar(select(func.count()).select_from(Incident).where(scope, Incident.severity == "critical", Incident.status != "resolved")) or 0
    return {"total_incidents": total, "open_incidents": open_count, "investigating_incidents": investigating, "critical_active": critical}

def collect_github_evidence(db: Session, incident_id: str, user_id: str):
    incident = get_incident(db, incident_id, user_id)
    if not incident:
        return None
    if not settings.github_repo:
        raise GitHubConnectorError("GITHUB_REPO is not configured")
    events = collect_github_events(
        repo=settings.github_repo,
        token=settings.github_token,
        incident_time=incident.created_at,
        lookback_hours=settings.github_lookback_hours,
    )
    existing_keys = {
        item.details.get("sha") or item.details.get("url") or item.message
        for item in incident.evidence
        if item.source == "github"
    }
    if not events:
        events = [{
            "source": "github",
            "level": "info",
            "message": f"No GitHub changes found in the {settings.github_lookback_hours}h lookback window.",
            "details": {
                "event_type": "no_changes_found",
                "repo": settings.github_repo,
                "lookback_hours": settings.github_lookback_hours,
            },
            "timestamp": now(),
        }]
    for item in events:
        key = item.get("details", {}).get("sha") or item.get("details", {}).get("url") or item["message"]
        if key in existing_keys:
            continue
        db.add(Evidence(
            id=str(uuid4()),
            incident_id=incident.id,
            source=item["source"],
            level=item.get("level", "info"),
            message=item["message"],
            details={**item.get("details", {}), "repo": settings.github_repo},
            timestamp=item.get("timestamp") or now(),
        ))
    incident.updated_at = now()
    db.commit()
    return get_incident(db, incident_id, user_id)

def run_investigation(db: Session, incident_id: str, user_id: str):
    incident = get_incident(db, incident_id, user_id)
    if not incident:
        return None
    incident.status = "investigating"
    db.commit()
    evidence = [{
        "id": item.id, "source": item.source, "level": item.level,
        "message": item.message, "details": item.details,
        "timestamp": item.timestamp.isoformat()
    } for item in incident.evidence]
    fallback_cause = getattr(incident, "_fallback_cause", None)
    fallback_actions = getattr(incident, "_fallback_actions", None)
    if not fallback_cause:
        scenario = build_scenario(incident.scenario) if incident.scenario in {
            "http_5xx_spike", "database_latency", "memory_pressure", "deployment_regression"
        } else {"fallback_cause": "Insufficient evidence to establish a specific root cause.", "fallback_actions": ["Collect correlated logs, metrics and traces.", "Compare the incident window with recent deployments."]}
        fallback_cause, fallback_actions = scenario["fallback_cause"], scenario["fallback_actions"]
    report = investigate(
        incident={"id": incident.id, "title": incident.title, "service_name": incident.service_name,
                  "scenario": incident.scenario, "severity": incident.severity, "summary": incident.summary,
                  "signals": incident.signals},
        evidence=evidence, fallback_cause=fallback_cause, fallback_actions=fallback_actions
    )
    if incident.investigation:
        inv = incident.investigation
        inv.status = "completed"
        inv.root_cause = report["root_cause"]
        inv.confidence = report["confidence"]
        inv.impact = report["impact"]
        inv.recommended_actions = report["recommended_actions"]
        inv.evidence_ids = report["evidence_ids"]
        inv.facts = report.get("facts", [])
        inv.hypotheses = report.get("hypotheses", [])
        inv.model = report["model"]
        inv.remediation_approved = False
    else:
        inv = Investigation(
            id=str(uuid4()), incident_id=incident.id, status="completed",
            root_cause=report["root_cause"], confidence=report["confidence"],
            impact=report["impact"], recommended_actions=report["recommended_actions"],
            evidence_ids=report["evidence_ids"], model=report["model"],
            facts=report.get("facts", []), hypotheses=report.get("hypotheses", []),
            remediation_approved=False, created_at=now()
        )
        db.add(inv)
    incident.status = "investigated"
    incident.updated_at = now()
    db.commit()
    return get_incident(db, incident_id, user_id)

def approve_remediation(db: Session, incident_id: str, user_id: str, approved_by: str, note: str):
    incident = get_incident(db, incident_id, user_id)
    if not incident or not incident.investigation:
        return None
    incident.investigation.remediation_approved = True
    incident.status = "approved"
    incident.updated_at = now()
    # MVP note is appended to the audit-style impact field.
    if note:
        incident.investigation.impact = f"{incident.investigation.impact}\nApproval recorded by {approved_by}: {note}"
    db.commit()
    return get_incident(db, incident_id, user_id)

def register_user(db: Session, email: str, password_hash: str):
    user = User(id=str(uuid4()), email=email, password_hash=password_hash, created_at=now())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def request_access(db: Session, user_id: str):
    pending = db.scalar(select(AccessRequest).where(
        AccessRequest.user_id == user_id, AccessRequest.status == "pending"
    ))
    if pending:
        return pending
    request = AccessRequest(id=str(uuid4()), user_id=user_id, status="pending", created_at=now())
    db.add(request)
    db.commit()
    db.refresh(request)
    return request

def list_access_requests(db: Session):
    rows = db.execute(
        select(AccessRequest, User.email)
        .join(User, User.id == AccessRequest.user_id)
        .order_by(AccessRequest.created_at.desc())
    ).all()
    return [access_request_data(request, email) for request, email in rows]

def access_request_data(request: AccessRequest, requester_email: str):
    return {
        "id": request.id,
        "user_id": request.user_id,
        "requester_email": requester_email,
        "status": request.status,
        "created_at": request.created_at,
        "resolved_at": request.resolved_at,
    }

def grant_access(db: Session, request_id: str, uses: int):
    request = db.get(AccessRequest, request_id)
    if not request or request.status != "pending":
        return None
    user = db.get(User, request.user_id)
    if not user:
        return None
    user.access_uses_remaining += uses
    request.status = "approved"
    request.resolved_at = now()
    db.commit()
    return access_request_data(request, user.email)

def reject_access(db: Session, request_id: str):
    request = db.get(AccessRequest, request_id)
    if not request or request.status != "pending":
        return None
    user = db.get(User, request.user_id)
    if not user:
        return None
    request.status = "rejected"
    request.resolved_at = now()
    db.commit()
    return access_request_data(request, user.email)

def get_user_by_email(db: Session, email: str):
    return db.scalar(select(User).where(User.email == email))

def get_user(db: Session, user_id: str):
    return db.get(User, user_id)
