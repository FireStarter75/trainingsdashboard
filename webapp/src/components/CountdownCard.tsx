import type { State } from '../lib/types';

function pad(n: number) {
  return String(n).padStart(2, '0');
}

/* Live aftelklok naar de racedag (09:00 als aanvangstijdstip), met ring voor
   de voortgang van het schema en een subtiele balk. */
export function CountdownCard({ state }: { state: State }) {
  const { plan, days_to_race, today } = state;
  const cfg = plan.config;

  const race = new Date(cfg.race_date + 'T09:00:00');
  const diff = Math.max(0, race.getTime() - Date.now());
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);

  // Voortgang: gemaakte weken / het hele plan.
  const total = plan.weeks.length;
  const completed = plan.weeks.filter((w) => w.end < today).length;
  const pct = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;

  const R = 52;
  const C = 2 * Math.PI * R;

  return (
    <div className="ambient relative overflow-hidden rounded-3xl border border-white/10 bg-card/90 p-6 md:p-8 md:col-span-2 md:row-span-2">
      <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-lime-400">
            {cfg.goal_name}
          </p>
          <p className="mt-1 text-sm text-zinc-400">
            {cfg.distance_km.toLocaleString('nl-NL')} km ·{' '}
            {new Date(cfg.race_date + 'T12:00:00').toLocaleDateString('nl-NL', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
              year: 'numeric',
            })}
          </p>
          <div className="mt-5 flex items-end gap-1.5 tabular">
            <span className="text-6xl md:text-7xl font-bold leading-none tracking-tighter text-zinc-50">
              {days}
            </span>
            <span className="mb-1 text-sm text-zinc-500">dagen</span>
            <span className="mb-1 ml-3 tabular text-lg text-zinc-400">
              {pad(hours)}:{pad(minutes)}
            </span>
          </div>
        </div>

        <div className="relative h-36 w-36 shrink-0 self-center">
          <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
            <circle cx="64" cy="64" r={R} fill="none" stroke="#1b1b20" strokeWidth="9" />
            <circle
              cx="64"
              cy="64"
              r={R}
              fill="none"
              stroke="#84cc16"
              strokeWidth="9"
              strokeLinecap="round"
              strokeDasharray={C}
              strokeDashoffset={C * (1 - pct / 100)}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="tabular text-2xl font-bold text-zinc-50">{pct}%</span>
            <span className="text-[10.5px] text-zinc-500">van schema</span>
          </div>
        </div>
      </div>

      <div className="mt-6 h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-lime-500 to-sky-400 transition-all duration-700"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-2.5 text-xs text-zinc-500">
        week {completed + 1} van {total} · {days_to_race} dagen te gaan (looptijd tot 09:00)
      </p>
    </div>
  );
}
