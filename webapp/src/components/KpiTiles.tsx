import type { State } from '../lib/types';

/* KPI-tegels: totaal gelopen km sinds de planstart, langste duurloop ooit en
   de huidige reeks weken waarin het plan (vrijwel) is gevolgd. */
export function KpiTiles({ state }: { state: State }) {
  const kmTotal = Object.values(state.actuals).reduce((s, a) => s + (a.km || 0), 0);

  // Langste duurloop: langste van de geplande weken tot en met nu...
  const planned = state.plan.weeks
    .filter((w) => w.start <= state.today)
    .reduce((m, w) => Math.max(m, w.long_min), 0);
  // ...maar wat je ECHT liep is minstens zo interessant: neem het EEGTE record.
  const longest = Math.max(state.baseline.all_time_longest_km ?? state.baseline.longest_km ?? 0, 0);

  // Streak: aaneengesloten, afgesloten weken waarin >= 90% van de geplande
  // minuten is gemaakt (telt vanaf vandaag terug).
  const weeks = state.plan.weeks;
  let streak = 0;
  for (let i = weeks.length - 1; i >= 0; i--) {
    const w = weeks[i];
    if (w.end >= state.today) continue;
    const a = state.actuals[w.start];
    const done = a?.minutes ?? 0;
    if (w.planned_min > 0 && done >= 0.9 * w.planned_min) streak++;
    else break;
  }

  const items = [
    { label: 'Totaal gelopen', value: kmTotal ? kmTotal.toFixed(1).replace('.', ',') : '0', unit: 'km', sub: `sinds ${state.plan.weeks[0]?.start ?? 'de start'}` },
    { label: 'Langste duurloop', value: longest ? longest.toFixed(1).replace('.', ',') : '–', unit: 'km', sub: planned ? `in het plan: ${Math.round(planned)} min` : 'ooit gelopen' },
    { label: 'Huidige streak', value: String(streak), unit: streak === 1 ? 'week' : 'weken', sub: '≥ 90% van het plan' },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 md:col-span-2">
      {items.map((it) => (
        <div key={it.label} className="rounded-3xl border border-white/10 bg-card/90 p-5 transition-colors hover:border-white/20">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">{it.label}</p>
          <p className="mt-2 flex items-baseline gap-1.5">
            <span className="tabular text-3xl font-bold tracking-tight text-zinc-50">{it.value}</span>
            <span className="text-sm text-zinc-500">{it.unit}</span>
          </p>
          <p className="mt-1 text-xs text-zinc-500">{it.sub}</p>
        </div>
      ))}
    </div>
  );
}
