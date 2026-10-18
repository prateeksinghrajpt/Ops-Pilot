import json
from typing import Any
import httpx
try:
    from backend.app.config import settings
except ModuleNotFoundError:
    from app.config import settings

SYSTEM_PROMPT = '''You are OpsPilot, an incident investigation assistant for software reliability engineers.
Use only the provided incident and evidence. Separate observed facts from hypotheses. Do not claim certainty
without evidence. Never execute actions. Return a JSON object with keys: root_cause (string), confidence
(number 0 to 1), impact (string), recommended_actions (array of concise strings), evidence_ids (array of
provided evidence IDs), facts (array of observed facts), and hypotheses (array of plausible explanations).
Prefer safe diagnostic actions. Mention uncertainty when evidence is incomplete.'''

def _fallback(incident: dict[str, Any], evidence: list[dict[str, Any]], cause: str, actions: list[str]) -> dict:
    facts = [f"{item.get('source', 'evidence')}: {item.get('message', '')}"[:500] for item in evidence[:6]]
    hypotheses = [cause[:500]]
    return {
        "root_cause": cause,
        "confidence": 0.78 if len(evidence) >= 3 else 0.45,
        "impact": f"Potential impact is concentrated in {incident.get('service_name', 'the affected service')}. "
                  "This is a simulated incident; validate scope against real telemetry before taking action.",
        "recommended_actions": actions,
        "evidence_ids": [item["id"] for item in evidence if item.get("id")],
        "facts": facts,
        "hypotheses": hypotheses,
        "model": "deterministic-fallback",
    }

def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model response did not contain JSON")
    return json.loads(text[start:end + 1])

def investigate(incident: dict[str, Any], evidence: list[dict[str, Any]], fallback_cause: str, fallback_actions: list[str]) -> dict:
    if not settings.openai_api_key:
        return _fallback(incident, evidence, fallback_cause, fallback_actions)

    payload = {
        "incident": incident,
        "evidence": evidence,
        "instructions": "Produce an evidence-backed investigation report. Reference only supplied evidence IDs."
    }
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.openai_model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, default=str)}
                ],
                "response_format": {"type": "json_object"}
            },
            timeout=35.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = _parse_json(content)
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
        known_ids = {item.get("id") for item in evidence}
        evidence_ids = [value for value in parsed.get("evidence_ids", []) if value in known_ids]
        actions = parsed.get("recommended_actions", [])
        if not isinstance(actions, list):
            actions = fallback_actions
        facts = parsed.get("facts", [])
        if not isinstance(facts, list):
            facts = []
        hypotheses = parsed.get("hypotheses", [])
        if not isinstance(hypotheses, list):
            hypotheses = []
        return {
            "root_cause": str(parsed.get("root_cause") or fallback_cause)[:5000],
            "confidence": confidence,
            "impact": str(parsed.get("impact") or "Impact requires validation.")[:2000],
            "recommended_actions": [str(x)[:500] for x in actions[:10]],
            "evidence_ids": evidence_ids,
            "facts": [str(x)[:500] for x in facts[:10]],
            "hypotheses": [str(x)[:500] for x in hypotheses[:10]],
            "model": settings.openai_model,
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        # Resilient fallback keeps the incident workflow usable if the LLM provider fails.
        return _fallback(incident, evidence, fallback_cause, fallback_actions)
