from app.simulator import build_scenario

def test_all_scenarios_have_evidence_and_actions():
    for scenario in ("http_5xx_spike", "database_latency", "memory_pressure", "deployment_regression"):
        data = build_scenario(scenario)
        assert data["title"]
        assert data["evidence"]
        assert data["fallback_actions"]
