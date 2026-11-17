import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, X } from 'lucide-react';
import type { State, Session } from '../lib/types';
import { kindStyle } from '../lib/types';
import { logRun } from '../lib/api';
import { loadLocal, markDone, markLogged } from '../lib/local';

function sessionForToday(state: State): Session | null {
  for (const w of state.plan.weeks) {
    const s = w.sessions.find((x) => x.date === state.today);
    if (s) return s;
  }
  return null;
}

const fmtHm = (m: number) => {
  const h = Math.floor(m / 60);
  const r = Math.round(m % 60);
  return h ? `${h}u${String(r).padStart(2, '0')}` : `${r} min`;
};

/* Focus-kaart: de training van vandaag, met afvinkmodal die ook echt logt
   (server-side) én de staat lokaal bewaart. */
export function TodayWorkout({ state, onChanged }: { state: State; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [km, setKm] = useState('');
  const [min, setMin] = useState('');
  const [feel, setFeel] = useState('3');

  const sess = sessionForToday(state);
  const doneKey = state.today;
  const isDone = !!loadLocal().done[doneKey] || (sess ? !!loadLocal().done[sess.date] : false);
  const style = sess ? kindStyle(sess.kind) : null;

  async function submit() {
    if (!sess) return;
    setBusy(true);
    setErr(null);
    try {
      await logRun({
        day: state.today,
        km: km ? Number(km.replace(',', '.')) : null,
        minutes: min ? Number(min.replace(',', '.')) : null,
        feel: Number(feel) || null,
        note: 'gelogd via de nieuwe webapp',
      });
      markLogged(doneKey, { km: km ? Number(km.replace(',', '.')) : null, minutes: min ? Number(min.replace(',', '.')) : null });
      markDone(doneKey);
      setOpen(false);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ambient relative rounded-3xl border border-white/10 bg-card/90 p-6 md:col-span-2">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
            Vandaag ·{' '}
            {new Date(state.today + 'T12:00:00').toLocaleDateString('nl-NL', {
              weekday: 'long',
              day: 'numeric',
              month: 'short',
            })}
          </p>
          {!sess && (
            <>
              <h3 className="mt-2 text-2xl font-bold tracking-tight text-zinc-50">Rustdag</h3>
              <p className="mt-1 text-sm text-zinc-500">Geen training gepland. Blijf goed drinken en slapen.</p>
            </>
          )}
          {sess && (
            <>
              <h3 className={`mt-2 text-2xl font-bold tracking-tight ${isDone ? 'text-lime-400' : 'text-zinc-50'}`}>
                {sess.label}
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-zinc-400">{sess.detail}</p>
            </>
          )}
        </div>
        {sess && style && (
          <span className={`shrink-0 rounded-full border px-3 py-1 text-xs font-medium ${style.badge}`}>
            {style.nl}
          </span>
        )}
      </div>

      {sess && (
        <>
          <div className="mt-5 flex items-center gap-3 text-sm text-zinc-400">
            <span className="tabular">{fmtHm(sess.minutes)}</span>
            <span className="h-1 w-1 rounded-full bg-zinc-700" />
            <span>hartslag {sess.hr ? `${sess.hr[0]}–${sess.hr[1]} bpm` : 'op gevoel'}</span>
          </div>
          {sess.hr && (
            <div className="mt-3 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-white/5">
              <div className={`h-full rounded-full ${style?.bar || 'bg-zinc-500'}`} style={{ width: '100%' }} />
            </div>
          )}
          {sess.note && <p className="mt-4 text-xs italic leading-relaxed text-zinc-500">{sess.note}</p>}

          <div className="mt-6">
            {isDone ? (
              <div className="inline-flex items-center gap-2 rounded-xl border border-lime-500/30 bg-lime-500/10 px-4 py-2.5 text-sm font-semibold text-lime-300">
                <Check size={16} /> Voltooid
              </div>
            ) : (
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => setOpen(true)}
                className="rounded-xl bg-lime-500 px-5 py-2.5 text-sm font-semibold text-zinc-950 shadow-[0_0_24px_-4px_rgba(132,204,22,0.5)] hover:bg-lime-400"
              >
                Training voltooien
              </motion.button>
            )}
          </div>
        </>
      )}

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] flex items-end justify-center bg-black/70 backdrop-blur-sm md:items-center"
            onClick={() => !busy && setOpen(false)}
          >
            <motion.div
              initial={{ y: 60, opacity: 0, scale: 0.98 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ y: 40, opacity: 0 }}
              transition={{ type: 'spring', damping: 26, stiffness: 320 }}
              className="w-full max-w-md rounded-t-3xl border border-white/10 bg-zinc-900 p-6 md:rounded-3xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between">
                <h4 className="font-semibold text-zinc-100">Hoe ging het echt?</h4>
                <button onClick={() => setOpen(false)} className="rounded-lg p-1.5 text-zinc-500 hover:bg-white/5 hover:text-zinc-300">
                  <X size={18} />
                </button>
              </div>
              <p className="mt-1 text-xs text-zinc-500">{sess?.label}</p>
              <div className="mt-5 grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-xs text-zinc-500">Kilometers</span>
                  <input
                    autoFocus
                    inputMode="decimal"
                    value={km}
                    onChange={(e) => setKm(e.target.value)}
                    placeholder={sess ? Math.round(sess.minutes / 6) + '' : '0'}
                    className="tabular mt-1.5 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-zinc-100 outline-none focus:border-lime-500/50"
                  />
                </label>
                <label className="block">
                  <span className="text-xs text-zinc-500">Minuten</span>
                  <input
                    inputMode="numeric"
                    value={min}
                    onChange={(e) => setMin(e.target.value)}
                    placeholder={sess ? String(sess.minutes) : '0'}
                    className="tabular mt-1.5 w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-zinc-100 outline-none focus:border-lime-500/50"
                  />
                </label>
              </div>
              <label className="mt-4 block">
                <span className="text-xs text-zinc-500">Gevoel</span>
                <div className="mt-1.5 grid grid-cols-5 gap-2">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      onClick={() => setFeel(String(n))}
                      className={`tabular rounded-xl border py-2 text-sm font-semibold transition-colors ${
                        String(n) === feel
                          ? 'border-lime-500/50 bg-lime-500/15 text-lime-300'
                          : 'border-white/10 bg-white/5 text-zinc-400 hover:text-zinc-200'
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </label>
              {err && <p className="mt-3 text-xs text-orange-400">{err}</p>}
              <button
                disabled={busy}
                onClick={() => void submit()}
                className="mt-6 w-full rounded-xl bg-lime-500 py-3 text-sm font-semibold text-zinc-950 shadow-[0_0_24px_-4px_rgba(132,204,22,0.5)] hover:bg-lime-400 disabled:opacity-50"
              >
                {busy ? 'Bezig…' : 'Voltooien'}
              </button>
              <p className="mt-3 text-center text-[11px] text-zinc-600">
                Gaat ook in je logboek en bij de coach; je plan zelf verandert niet.
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
