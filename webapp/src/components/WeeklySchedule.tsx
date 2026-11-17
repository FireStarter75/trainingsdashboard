import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, ChevronDown, Moon } from 'lucide-react';
import type { State, Week } from '../lib/types';
import { kindStyle } from '../lib/types';
import { loadLocal, markDone } from '../lib/local';

const DAYS = ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo'];
const DAY_FULL = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag'];

const fmtHm = (m: number) => {
  const h = Math.floor(m / 60);
  const r = Math.round(m % 60);
  return h ? `${h}u${String(r).padStart(2, '0')}` : `${r} min`;
};

function currentWeek(state: State): Week | undefined {
  return (
    state.plan.weeks.find((w) => w.start <= state.today && state.today <= w.end) ||
    state.plan.weeks.find((w) => w.start > state.today)
  );
}

/* Interactief weekoverzicht: ma t/m zo, badges per type, afvinken (lokaal),
   dag aanklikken voor de details. */
export function WeeklySchedule({ state }: { state: State }) {
  const [openDay, setOpenDay] = useState<string | null>(state.today);
  const week = currentWeek(state);

  if (!week) return null;

  const byDay = new Map<string, import('../lib/types').Session[]>();
  for (const s of week.sessions) {
    const arr = byDay.get(s.date) || [];
    arr.push(s);
    byDay.set(s.date, arr);
  }
  const days: (string | null)[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(week.start + 'T12:00:00');
    d.setDate(d.getDate() + i);
    days.push(d.toISOString().slice(0, 10));
  }
  const local = loadLocal();

  return (
    <div className="rounded-3xl border border-white/10 bg-card/90 p-6 md:col-span-2">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold tracking-tight text-zinc-100">Deze week</h3>
          <p className="mt-0.5 text-xs text-zinc-500">
            week {week.index} · {week.phase === 'race' ? 'racweek' : `gepland ${fmtHm(week.planned_min)}`}
            {week.deload ? ' · herstelweek' : ''}
            {week.adapted ? ` · bijgesteld ${Math.round((week.adapted.scale - 1) * 100)}%` : ''}
          </p>
        </div>
        <button
          onClick={() => [
            ...byDay.keys(),
          ].forEach((d) => { if (!local.done[d]) { markDone(d); } window.dispatchEvent(new Event('dash-local')); })}
          className="hidden rounded-lg border border-white/10 px-3 py-1.5 text-xs text-zinc-400 hover:bg-white/5"
        >
          Alles afvinken
        </button>
      </div>

      <div className="mt-4 space-y-1.5">
        {days.map((d, i) => {
          if (!d) return null;
          const sessions = byDay.get(d) || [];
          const isToday = d === state.today;
          const past = d < state.today;
          const done = !!local.done[d];
          const open = openDay === d;
          return (
            <div key={d}>
              <button
                onClick={() => sessions.length && setOpenDay(open ? null : d)}
                className={`w-full rounded-xl border px-3 py-2.5 text-left transition-colors ${
                  isToday ? 'border-lime-500/30 bg-lime-500/[0.06]' : 'border-transparent hover:bg-white/[0.04]'
                } ${sessions.length === 0 ? 'opacity-60' : ''}`}
              >
                <div className="flex items-center gap-3">
                  <span className={`w-8 shrink-0 text-xs font-semibold uppercase ${isToday ? 'text-lime-300' : 'text-zinc-500'}`}>
                    {DAYS[i]}
                  </span>
                  {sessions.length === 0 ? (
                    <span className="flex items-center gap-2 text-sm text-zinc-600">
                      <Moon size={14} /> rustdag
                    </span>
                  ) : (
                    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
                      {sessions.map((s) => {
                        const st = kindStyle(s.kind);
                        return (
                          <span key={s.date + s.label} className="flex items-center gap-2 min-w-0">
                            <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[10.5px] font-medium ${st.badge}`}>
                              {st.nl}
                            </span>
                            <span className={`truncate text-sm ${done || past ? 'text-zinc-500' : 'text-zinc-200'}`}>
                              {s.label}
                            </span>
                            <span className="tabular shrink-0 text-xs text-zinc-500">{fmtHm(s.minutes)}</span>
                          </span>
                        );
                      })}
                    </div>
                  )}
                  {sessions.length > 0 && (
                    done ? (
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-lime-500/20 text-lime-400">
                        <Check size={12} strokeWidth={3} />
                      </span>
                    ) : (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          markDone(d);
                          window.dispatchEvent(new Event('dash-local'));
                        }}
                        className="shrink-0 rounded-full border border-white/15 p-1 text-zinc-500 hover:border-lime-500/50 hover:text-lime-400"
                        title="Afvinken"
                      >
                        <Check size={12} strokeWidth={3} />
                      </button>
                    )
                  )}
                  {sessions.length > 0 && (
                    <ChevronDown size={14} className={`shrink-0 text-zinc-600 transition-transform ${open ? 'rotate-180' : ''}`} />
                  )}
                </div>
              </button>
              <AnimatePresence>
                {open && sessions.length > 0 && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                    className="overflow-hidden"
                  >
                    <div className="ml-11 mt-1 space-y-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
                      {sessions.map((s) => (
                        <div key={s.date + s.label}>
                          <p className="text-xs font-medium text-zinc-300">
                            {DAY_FULL[i]} · {s.label}
                          </p>
                          {s.detail && <p className="mt-1 text-xs leading-relaxed text-zinc-500">{s.detail}</p>}
                          {s.note && <p className="mt-1 text-[11px] italic text-zinc-600">{s.note}</p>}
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}
