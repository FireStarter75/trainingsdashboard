export interface Session {
  date: string;
  kind: string; // easy | long | steady | tempo | threshold | intervals | hills | strides | strength | race
  label: string;
  detail?: string;
  note?: string;
  minutes: number;
  hr?: [number, number] | null;
  builder?: string;
  args?: Record<string, unknown>;
}

export interface Week {
  index: number;
  start: string;
  end: string;
  phase: string;
  planned_min: number;
  long_min: number;
  sessions: Session[];
  acwr?: number | null;
  deload?: boolean;
  run_walk?: string | null;
  adapted?: { scale: number; severity: string; reasons?: string[]; drop_quality?: boolean } | null;
  capped?: { reason: string; factor: number } | null;
}

export interface Actual {
  km: number;
  minutes: number;
  sessions: number;
}

export interface Run {
  id: number;
  name: string;
  start_time: string;
  distance_meters: number;
  duration_seconds: number;
  avg_hr_bpm?: number | null;
  max_hr_bpm?: number | null;
  elevation_gain_meters?: number | null;
}

export interface ReadinessSignal {
  name: string;
  rating: string;
  detail: string;
}

export interface Readiness {
  decision?: string;
  recommendation?: string[];
  signals?: ReadinessSignal[];
  partial?: boolean;
}

export interface GoalConfig {
  goal_name: string;
  race_date: string;
  distance_km: number;
  days_per_week: number;
  priority: 'health' | 'time';
  target_time_min?: number | null;
}

export interface Estimate {
  race_minutes_after?: number;
  target_min?: number | null;
}

export interface State {
  today: string;
  days_to_race: number;
  plan: {
    config: GoalConfig;
    weeks: Week[];
    estimate?: Estimate;
  };
  actuals: Record<string, Actual>;
  runs: Run[];
  baseline: {
    longest_km?: number;
    longest_min?: number;
    km_90d?: number;
    first_run?: string;
    all_time_longest_km?: number;
  };
  metrics: Record<string, { ok: boolean; value?: Record<string, unknown> }>;
  uploads?: Record<string, unknown>;
  cache_ages?: Record<string, number>;
}

/** Soortkleuren: koraal voor intensief, blauw voor rustig, lime voor done. */
export const KIND_STYLE: Record<
  string,
  { nl: string; badge: string; bar: string }
> = {
  easy: { nl: 'Rustig', badge: 'bg-sky-500/15 text-sky-300 border-sky-500/30', bar: 'bg-sky-400' },
  long: { nl: 'Duurloop', badge: 'bg-violet-500/15 text-violet-300 border-violet-500/30', bar: 'bg-violet-400' },
  steady: { nl: 'Steady', badge: 'bg-coral/15 text-orange-300 border-orange-500/30', bar: 'bg-orange-400' },
  tempo: { nl: 'Tempo', badge: 'bg-coral/15 text-orange-300 border-orange-500/30', bar: 'bg-orange-400' },
  threshold: { nl: 'Drempel', badge: 'bg-coral/15 text-orange-300 border-orange-500/30', bar: 'bg-orange-400' },
  intervals: { nl: 'Interval', badge: 'bg-coral/15 text-orange-300 border-orange-500/30', bar: 'bg-orange-400' },
  hills: { nl: 'Heuvels', badge: 'bg-coral/15 text-orange-300 border-orange-500/30', bar: 'bg-orange-400' },
  strides: { nl: 'Sprongen', badge: 'bg-coral/15 text-orange-300 border-orange-500/30', bar: 'bg-orange-400' },
  strength: { nl: 'Kracht', badge: 'bg-lime/10 text-lime-300 border-lime-500/30', bar: 'bg-lime-400' },
  race: { nl: 'Wedstrijd', badge: 'bg-coral/15 text-orange-300 border-orange-500/30', bar: 'bg-orange-400' },
};

export const kindStyle = (kind: string) =>
  KIND_STYLE[kind] || { nl: kind, badge: 'bg-white/5 text-zinc-400 border-white/10', bar: 'bg-zinc-500' };
