const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  if (response.status === 204) return null
  return response.json()
}

export const api = {
  health: () => request('/health'),
  dashboard: () => request('/api/v1/dashboard'),
  incidents: () => request('/api/v1/incidents?limit=100'),
  incident: (id) => request(`/api/v1/incidents/${id}`),
  simulate: (payload) => request('/api/v1/incidents/simulate', { method: 'POST', body: JSON.stringify(payload) }),
  collectGithub: (id) => request(`/api/v1/incidents/${id}/collect-github-evidence`, { method: 'POST' }),
  investigate: (id) => request(`/api/v1/incidents/${id}/investigate`, { method: 'POST' }),
  approve: (id, payload) => request(`/api/v1/incidents/${id}/approve-remediation`, { method: 'POST', body: JSON.stringify(payload) }),
}
