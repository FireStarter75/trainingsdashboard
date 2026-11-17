import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import type { State } from '../lib/types';
import { kindStyle } from '../lib/types';

const fmtHm = (m: number) => {
  const h = Math.floor(m / 60);
  const r = Math.round(m % 60);
  return h ? `${h}u${String(r).padStart(2, '0')}` : `${r} min`;
};

const PHASE_NL: Record<string, string> = {
  basis: 'Basis',
  opbouw: 'Opbouw',
  piek: 'Piek',
  taper: 'Taper',
  race: 'Raceweek',
};

/* Het volledige schema: alle weken van het plan, openklapbaar. */
export function PlanPage({ state }: { state: State }) {
  const [open, setOpen] = useState<number | null>(null);
  const today = state.today;

  return (
    <div className="space-y-1.5">
      {state.plan.weeks.map((w) => {
        const isNow = w.start <= today && today <= w.end;
        const past = w.end < today;
        const a = state.actuals[w.start];
        const openRow = open === w.index;
        return (
          <div key={w.start} className={`rounded-2xl border transition-colors ${isNow ? 'border-lime-500/30 bg-lime-500/[0.05]' : 'border-white/10 bg-card/60 hover:border-white/20'} ${past ? 'opacity-60' : ''}`}>
            <button
              onClick={() => setOpen(openRow ? null : w.index)}
              className="flex w-full items-center gap-4 px-4 py-3 text-left sm:px-5"
            >
              <span className={`tabular w-10 text-center text-xs font-bold ${isNow ? 'text-lime-300' : 'text-zinc-500'}`}>
                {w.index}
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-zinc-100">
                  week van {new Date(w.start + 'T12:00:00').toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' })}
                  <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-zinc-400">
                    {PHASE_NL[w.phase] || w.phase}
                  </span>
                  {w.deload && <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-300">herstel</span>}
                  {w.adapted && (
                    <span className="rounded-full border border-orange-500/30 bg-orange-500/10 px-2 py-0.5 text-[10px] text-orange-300">
                      {Math.round((w.adapted.scale - 1) * 100)}%
                    </span>
                  )}
                </p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {w.sessions.length} sessies · {fmtHm(w.planned_min)}
                  {a ? ` · gedaan ${fmtHm(a.minutes)}${a.km ? ` / ${a.km.toFixed(1)} km` : ''}` : ''}
                </p>
              </div>
              <ChevronDown size={16} className={`shrink-0 text-zinc-600 transition-transform ${openRow ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
              {openRow && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.22, ease: 'easeOut' }}
                  className="overflow-hidden"
                >
                  <div className="space-y-2 border-t border-white/5 px-4 py-3 sm:px-5">
                    {w.sessions.map((s) => {
                      const st = kindStyle(s.kind);
                      return (
                        <div key={s.date + s.label} className="rounded-xl bg-white/[0.03] p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`rounded-md border px-2 py-0.5 text-[10.5px] font-medium ${st.badge}`}>{st.nl}</span>
                            <span className="text-sm font-medium text-zinc-100">{s.label}</span>
                            <span className="tabular text-xs text-zinc-500">
                              {new Date(s.date + 'T12:00:00').toLocaleDateString('nl-NL', { weekday: 'short', day: 'numeric' })} · {fmtHm(s.minutes)}
                            </span>
                          </div>
                          {s.detail && <p className="mt-1.5 text-xs leading-relaxed text-zinc-400">{s.detail}</p>}
                          {s.note && <p className="mt-1 text-[11px] italic text-zinc-600">{s.note}</p>}
                        </div>
                      );
                    })}
                    {w.sessions.length === 0 && <p className="text-xs text-zinc-600">rustweek</p>}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
