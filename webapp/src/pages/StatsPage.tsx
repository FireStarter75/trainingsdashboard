import { BarChart3, Activity, Flame } from 'lucide-react';
import type { State } from '../lib/types';

const fmtHm = (m: number) => {
  const h = Math.floor(m / 60);
  const r = Math.round(m % 60);
  return h ? `${h}u${String(r).padStart(2, '0')}` : `${r} min`;
};

const paceOf = (m: number, km: number) =>
  km > 0 ? new Date(((m / km) * 60000) || 0).toISOString().substr(14, 5) : '–';

/* Statistieken: vorm, basis en recente runs, rechtstreeks uit /api/state. */
export function StatsPage({ state }: { state: State }) {
  const b = state.baseline;
  const ld = ((state.metrics.load?.value as { data?: { latest?: Record<string, number> } })?.data?.latest) || {};
  const runs = state.runs.slice(0, 12);

  const cards = [
    { icon: Activity, label: 'Vorm (TSB)', value: ld.tsb != null ? Math.round(ld.tsb) : '–', sub: `fitheid ${ld.ctl != null ? Math.round(ld.ctl) : '–'} · moeheid ${ld.atl != null ? Math.round(ld.atl) : '–'}`, tone: (ld.tsb ?? 0) < -20 ? 'text-orange-400' : (ld.tsb ?? 0) < -10 ? 'text-yellow-400' : 'text-lime-400' },
    { icon: BarChart3, label: 'ACWR', value: ld.acwr != null ? ld.acwr.toFixed(2) : '–', sub: ld.acwr != null ? (ld.acwr > 1.3 ? 'snel opgebouwd' : ld.acwr < 0.8 ? 'weinig prikkel' : 'veilige zone') : '—', tone: 'text-zinc-100' },
    { icon: Flame, label: 'KM laatste 90d', value: b.km_90d != null ? b.km_90d.toFixed(1).replace('.', ',') : '–', sub: b.first_run ? `loop sinds ${b.first_run}` : '', tone: 'text-sky-300' },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-3xl border border-white/10 bg-card/90 p-5">
            <div className="flex items-center gap-2 text-zinc-500">
              <c.icon size={15} />
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em]">{c.label}</span>
            </div>
            <p className={`tabular mt-2 text-3xl font-bold tracking-tight ${c.tone}`}>{c.value}</p>
            <p className="mt-1 text-xs text-zinc-500">{c.sub}</p>
          </div>
        ))}
      </div>

      <div className="rounded-3xl border border-white/10 bg-card/90 p-5">
        <h3 className="font-semibold tracking-tight text-zinc-100">Recente runs</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10.5px] uppercase tracking-[0.12em] text-zinc-500">
                <th className="py-2 pr-4 font-medium">Datum</th>
                <th className="py-2 pr-4 font-medium">Ronde</th>
                <th className="py-2 pr-4 text-right font-medium">Km</th>
                <th className="py-2 pr-4 text-right font-medium">Tijd</th>
                <th className="py-2 pr-4 text-right font-medium">Tempo</th>
                <th className="py-2 text-right font-medium">HF</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const km = r.distance_meters / 1000;
                const min = r.duration_seconds / 60;
                return (
                  <tr key={r.id} className="border-t border-white/5 text-zinc-300">
                    <td className="py-2.5 pr-4 tabular">{new Date(r.start_time.replace(' ', 'T')).toLocaleDateString('nl-NL', { day: '2-digit', month: '2-digit' })}</td>
                    <td className="max-w-[220px] truncate py-2.5 pr-4">{r.name}</td>
                    <td className="py-2.5 pr-4 text-right tabular">{km.toFixed(1).replace('.', ',')}</td>
                    <td className="py-2.5 pr-4 text-right tabular">{fmtHm(min)}</td>
                    <td className="py-2.5 pr-4 text-right tabular">{paceOf(min, km)}</td>
                    <td className="py-2.5 text-right tabular">{r.avg_hr_bpm ? Math.round(r.avg_hr_bpm) : '–'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
