import type { State, GoalConfig } from './types';

/* API-basis: leeg in productie, '/test' in de testomgeving. De Flask-route
 * die deze app serveert zet window.__API_BASE__ op request.script_root. */
export const API_BASE: string =
  (window as unknown as { __API_BASE__?: string }).__API_BASE__ || '';

export async function fetchState(): Promise<State> {
  const r = await fetch(API_BASE + '/api/state');
  if (r.status === 401) {
    window.location.href =
      API_BASE + '/login?next=' + encodeURIComponent(location.pathname);
    throw new Error('niet ingelogd');
  }
  if (!r.ok) throw new Error('kon de data niet ophalen (' + r.status + ')');
  return r.json();
}

export interface LogEntry {
  day: string;
  km?: number | null;
  minutes?: number | null;
  feel?: number | null;
  note?: string | null;
}

/** Logt een gelopen training server-side (staat ook in het coach-logboek). */
export async function logRun(entry: LogEntry): Promise<void> {
  const r = await fetch(API_BASE + '/api/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  });
  if (!r.ok) throw new Error('loggen mislukte (' + r.status + ')');
}

export async function saveGoal(cfg: GoalConfig): Promise<void> {
  const r = await fetch(API_BASE + '/api/goal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  });
  if (!r.ok) throw new Error('opslaan mislukte (' + r.status + ')');
}

export async function logout(): Promise<void> {
  await fetch(API_BASE + '/logout');
  window.location.href = API_BASE + '/login';
}
