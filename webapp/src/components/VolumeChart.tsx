import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import type { State } from '../lib/types';

/* Wekelijks volume: gepland (uren) tegen gedaan, laatste 6 en eerstvolgende 4 weken.
   De planning is in minuten; km was alleen te raden, en daar doen we niet aan. */
export function VolumeChart({ state }: { state: State }) {
  const now = state.plan.weeks.findIndex((w) => w.start <= state.today && state.today <= w.end);
  const slice = state.plan.weeks.slice(Math.max(0, now - 5), Math.max(0, now - 5) + 10);

  const data = slice.map((w) => {
    const a = state.actuals[w.start];
    const future = w.start > state.today;
    return {
      name: w.start.slice(8) + '/' + w.start.slice(5, 7),
      Gepland: future ? Math.round(w.planned_min) : null,
      Gedaan: a ? Math.round(a.minutes) : null,
      week: w.index,
    };
  });

  return (
    <div className="rounded-3xl border border-white/10 bg-card/90 p-6 md:col-span-2">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold tracking-tight text-zinc-100">Wekelijks volume</h3>
          <p className="mt-0.5 text-xs text-zinc-500">geplande tegen gemaakte minuten per week</p>
        </div>
        <div className="flex items-center gap-4 text-xs text-zinc-500">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-zinc-600" /> gepland</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-lime-500" /> gedaan</span>
        </div>
      </div>
      <div className="mt-4 h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: -22 }} barGap={2}>
            <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="name" tick={{ fill: '#71717a', fontSize: 10.5 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#71717a', fontSize: 10.5 }} axisLine={false} tickLine={false} tickFormatter={(v) => v + 'm'} />
            <Tooltip
              cursor={{ fill: 'rgba(255,255,255,0.04)' }}
              contentStyle={{
                background: '#131316',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 12,
                fontSize: 12,
                color: '#e4e4e7',
              }}
              labelFormatter={(l, p) => `week ${p?.[0]?.payload?.week ?? ''} (vanaf ${l})`}
              formatter={(v: number, name: string) => [v + ' min', name]}
            />
            <Bar dataKey="Gepland" fill="#3f3f46" radius={[6, 6, 0, 0]} maxBarSize={22} />
            <Bar dataKey="Gedaan" fill="#84cc16" radius={[6, 6, 0, 0]} maxBarSize={22} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
