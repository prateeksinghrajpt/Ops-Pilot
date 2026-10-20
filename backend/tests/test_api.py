import os
from uuid import uuid4
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_opspilot.db")
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

def test_dashboard_empty_or_populated():
    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard")
        assert response.status_code == 401

def signup(client, email=None):
    response = client.post("/api/v1/auth/signup", json={
        "email": email or f"engineer-{uuid4()}@example.com",
        "password": "a-secure-demo-password",
    })
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

def test_authenticated_user_only_sees_own_incidents():
    with TestClient(app) as client:
        first_headers = signup(client)
        created = client.post("/api/v1/incidents/simulate", json={
            "scenario": "deployment_regression",
            "service_name": "checkout-service",
            "severity": "high",
        }, headers=first_headers)
        assert created.status_code == 201
        incident_id = created.json()["id"]

        second_headers = signup(client)
        dashboard = client.get("/api/v1/dashboard", headers=second_headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["total_incidents"] == 0
        assert client.get(f"/api/v1/incidents/{incident_id}", headers=second_headers).status_code == 404
        assert client.get(f"/api/v1/incidents/{incident_id}", headers=first_headers).status_code == 200

def test_regular_user_gets_one_investigation_then_can_request_access():
    with TestClient(app) as client:
        headers = signup(client)
        created = client.post("/api/v1/incidents/simulate", json={
            "scenario": "deployment_regression",
            "service_name": "checkout-service",
            "severity": "high",
        }, headers=headers)
        assert created.status_code == 201
        investigated = client.post(f"/api/v1/incidents/{created.json()['id']}/investigate", headers=headers)
        assert investigated.status_code == 200

        blocked = client.post("/api/v1/incidents/simulate", json={
            "scenario": "database_latency",
            "service_name": "checkout-service",
            "severity": "high",
        }, headers=headers)
        assert blocked.status_code == 403

        requested = client.post("/api/v1/access-requests", headers=headers)
        assert requested.status_code == 201
        assert requested.json()["status"] == "pending"
