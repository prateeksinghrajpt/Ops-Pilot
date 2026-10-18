from datetime import datetime, timezone
from uuid import uuid4

SCENARIOS = {
    "http_5xx_spike": {
        "title": "HTTP 5xx error spike",
        "summary": "The service is returning an elevated rate of server errors.",
        "signals": {"error_rate_percent": 18.0, "baseline_error_rate_percent": 0.4, "p95_latency_ms": 2800, "requests_per_minute": 1240},
        "evidence": [
            ("metrics", "critical", "HTTP 5xx error rate rose to 18%, compared with a 0.4% baseline.", {"metric": "http_5xx_rate", "value": 18, "unit": "percent"}),
            ("logs", "error", "Checkout handler raised an unhandled upstream timeout.", {"trace_id": "trace-demo-001", "exception": "UpstreamTimeout"}),
            ("traces", "warning", "Checkout request spends 2.4s waiting on payment-provider dependency.", {"dependency": "payment-provider", "duration_ms": 2400}),
        ],
        "cause": "The strongest available evidence points to slow responses from the payment-provider dependency, which are propagating as checkout errors. Confirm provider health and compare with recent deployment events before concluding.",
        "actions": ["Check payment-provider health and timeout/error metrics.", "Inspect correlated traces for the affected time window.", "Review recent checkout and payment integration deployments.", "Consider reducing retry amplification or using the established fallback path, after engineer review."],
    },
    "database_latency": {
        "title": "Database latency regression",
        "summary": "Database operations are slower than their normal baseline.",
        "signals": {"db_p95_latency_ms": 1850, "baseline_db_p95_latency_ms": 90, "db_pool_in_use_percent": 96, "api_p95_latency_ms": 2300},
        "evidence": [
            ("metrics", "critical", "Database p95 latency increased to 1850ms from a 90ms baseline.", {"metric": "db_query_p95_ms", "value": 1850}),
            ("metrics", "warning", "Database connection pool is 96% utilized.", {"metric": "db_pool_in_use_percent", "value": 96}),
            ("logs", "error", "Requests are timing out while waiting for a database connection.", {"exception": "PoolTimeout", "component": "db-pool"}),
        ],
        "cause": "Evidence indicates database connection-pool saturation alongside elevated query latency. Determine whether slow queries, a traffic surge, or connection leakage is the primary driver before changing pool limits.",
        "actions": ["Inspect slow-query logs and query plans.", "Check connection counts, pool wait time and active transactions.", "Compare traffic volume with the incident baseline.", "Review recent database and application changes before tuning pool sizes."],
    },
    "memory_pressure": {
        "title": "Memory pressure detected",
        "summary": "A service is approaching its memory limit and may be restarting.",
        "signals": {"memory_used_percent": 94, "restart_count_15m": 3, "p95_latency_ms": 970},
        "evidence": [
            ("metrics", "critical", "Memory utilization reached 94% of the container limit.", {"metric": "container_memory_used_percent", "value": 94}),
            ("logs", "error", "Worker restarted after an out-of-memory termination.", {"reason": "OOMKilled", "container": "api-worker"}),
            ("metrics", "warning", "Three restarts observed in the last 15 minutes.", {"metric": "container_restart_count", "value": 3}),
        ],
        "cause": "The service is under memory pressure and has experienced repeated worker restarts. This is consistent with a memory leak, a workload spike, or insufficient resource limits; the available evidence does not distinguish them conclusively.",
        "actions": ["Compare memory usage by process and endpoint over time.", "Inspect recent changes for retained objects or unbounded buffering.", "Review workload volume and request payload sizes.", "Check container limits and restart history before considering resource changes."],
    },
    "deployment_regression": {
        "title": "Possible deployment regression",
        "summary": "Latency and error rate increased shortly after a deployment.",
        "signals": {"error_rate_percent": 7.5, "p95_latency_ms": 1650, "deployment_age_minutes": 8, "previous_p95_latency_ms": 210},
        "evidence": [
            ("deployments", "warning", "Version api-2026.10.12.3 was deployed 8 minutes before the alert.", {"version": "api-2026.10.12.3", "age_minutes": 8}),
            ("metrics", "critical", "p95 latency rose from 210ms to 1650ms.", {"metric": "http_server_duration_p95_ms", "value": 1650}),
            ("logs", "error", "New version reports repeated serialization errors on response payloads.", {"exception": "ResponseValidationError"}),
        ],
        "cause": "The timing and response-validation errors make the latest deployment a plausible contributor to the latency and error regression. Validate with a version comparison or canary before deciding whether to roll back.",
        "actions": ["Compare error and latency metrics by application version.", "Inspect response-validation errors and affected endpoints.", "Use the deployment diff to identify relevant changes.", "Prepare a rollback plan for engineer approval if version-level evidence confirms the regression."],
    },
}

def build_scenario(scenario: str):
    if scenario not in SCENARIOS:
        raise ValueError(f"Unsupported scenario: {scenario}")
    template = SCENARIOS[scenario]
    return {
        "title": template["title"],
        "summary": template["summary"],
        "signals": dict(template["signals"]),
        "evidence": [
            {"source": source, "level": level, "message": message, "details": dict(details)}
            for source, level, message, details in template["evidence"]
        ],
        "fallback_cause": template["cause"],
        "fallback_actions": list(template["actions"]),
    }
