import os
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
        assert response.status_code == 200
        assert "total_incidents" in response.json()
