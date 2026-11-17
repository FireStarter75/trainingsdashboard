/* Lokale voortgang: wat jij afvinkt of logt, blijft na een verversing bestaan.
   Server-side gaat het loggen via /api/log (staat ook in je coach-logboek);
   het afvinken van een geplande sessie is een visuele UX-keuze en blijft
   bewust lokaal. */

const KEY = 'dash-web-v1';

export interface LocalState {
  /** Gevinkte sessies op datum: { '2026-11-18': true } */
  done: Record<string, true>;
  /** Lokaal gelogde sessies die de server nog niet bevestigt. */
  pending: Record<string, { km?: number | null; minutes?: number | null; feel?: number | null }>;
}

const empty: LocalState = { done: {}, pending: {} };

export function loadLocal(): LocalState {
  try {
    return { ...empty, ...JSON.parse(localStorage.getItem(KEY) || '{}') };
  } catch {
    return { ...empty };
  }
}

export function saveLocal(next: LocalState): void {
  localStorage.setItem(KEY, JSON.stringify(next));
}

export function markDone(day: string): LocalState {
  const s = loadLocal();
  s.done[day] = true;
  delete s.pending[day];
  saveLocal(s);
  return s;
}

export function markLogged(day: string, entry: LocalState['pending'][string]): LocalState {
  const s = loadLocal();
  s.pending[day] = entry;
  saveLocal(s);
  return s;
}

export function isDone(day: string): boolean {
  return !!loadLocal().done[day];
}
