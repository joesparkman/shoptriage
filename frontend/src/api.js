const BASE_URL = import.meta.env.VITE_API_BASE_URL;

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });

  let body = null;
  try {
    body = await res.json();
  } catch {
    // no body
  }

  if (!res.ok) {
    const message = (body && body.error) || `request failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

export function triggerDemoCall(sampleId) {
  return request("/demo/calls", {
    method: "POST",
    body: JSON.stringify({ sample_id: sampleId }),
  });
}

export function getTimeline(callId) {
  return request(`/calls/${callId}/timeline`);
}

export function listCallsByStatus(status) {
  return request(`/calls?status=${encodeURIComponent(status)}`);
}

export function getInbox(role) {
  return request(`/inbox/${role}`);
}

export function updateCallStatus(callId, status) {
  return request(`/calls/${callId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export function getStats() {
  return request("/stats");
}

export function addNote(callId, { text, author }) {
  return request(`/calls/${callId}/notes`, {
    method: "POST",
    body: JSON.stringify({ text, author }),
  });
}

export function logAttempt(callId, { outcome, note, author }) {
  return request(`/calls/${callId}/attempts`, {
    method: "POST",
    body: JSON.stringify({ outcome, note, author }),
  });
}
